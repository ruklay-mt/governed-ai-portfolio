"""The agent loop (spec §8.1): guard -> tool-use loop -> structured answer, as a stream of events.

1. Guard: the small model classifies the question. Out of scope stops here, before the main
   model is called. Suspected injection is flagged in the trace and the loop continues: the
   database, not this classifier, is what keeps data safe.
2. Answer: the main model calls the read-only tools (each running as the caller's persona
   login) at most MAX_TOOL_CALLS times, then calls `final_answer` (strict schema,
   prompts.ANSWER_SCHEMA). The model is told to finish with it; forced tool choice is not
   available on current models, so a plain-text ending is accepted and flagged.
   Structured output (output_config.format) is not used for this: constraining every text
   block to JSON left the model no way to write between tool calls, and it padded with
   no-op calls (`select 1`) instead of answering.
3. Render: answer.assemble_answer builds the card from stored tool results.

`run_agent` yields Events; the API turns them into server-sent events.
"""

import json
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import anthropic
from anthropic.types import Message, MessageParam, ToolParam, ToolResultBlockParam
from pydantic import BaseModel

from app.agent.answer import Answer, ModelAnswer, assemble_answer, evidence
from app.agent.cost import call_cost_usd, usage_details
from app.agent.db import PersonaPools
from app.agent.personas import get_persona
from app.agent.prompts import (
    ANSWER_SCHEMA,
    GUARD_SCHEMA,
    GUARD_SYSTEM,
    OUT_OF_SCOPE_REPLY,
    agent_system_prompt,
)
from app.agent.tools import TOOLS, ToolContext, ToolResult, call_tool
from app.config import Settings
from app.tracing import Span, Tracer

MAX_TOOL_CALLS = 8
MAX_MODEL_CALLS = MAX_TOOL_CALLS + 2  # room for parallel calls and the final answer
MAIN_MAX_TOKENS = 16000
GUARD_MAX_TOKENS = 2000
# Rows sent back to the model per tool result. The full result (up to 1,000 rows) stays on
# the ToolContext for the answer table; the model only needs enough to reason about it.
ROWS_FOR_MODEL = 50

EventType = Literal["trace_id", "step", "tool_call", "tool_result", "answer", "usage", "error"]
GuardCategory = Literal["in_scope", "out_of_scope", "injection_suspected"]


class Event(BaseModel):
    type: EventType
    data: dict[str, Any]


@dataclass
class UsageTotals:
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    started: float = field(default_factory=time.monotonic)

    def add(self, model: str, message: Message) -> float:
        cost = call_cost_usd(model, message.usage)
        details = usage_details(message.usage)
        self.model_calls += 1
        self.input_tokens += details["input"]
        self.output_tokens += details["output"]
        self.cache_read_tokens += details["cache_read"]
        self.cache_write_tokens += details["cache_write"]
        self.cost_usd = round(self.cost_usd + cost, 6)
        return cost

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": round((time.monotonic() - self.started) * 1000),
        }


@dataclass
class AgentDeps:
    client: anthropic.Anthropic
    settings: Settings
    pools: PersonaPools
    embed_query: Callable[[str], list[float]]
    tracer: Tracer


FINAL_ANSWER_TOOL = "final_answer"


def tool_definitions() -> list[ToolParam]:
    tools: list[ToolParam] = [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_model.model_json_schema(),
        }
        for spec in TOOLS.values()
    ]
    tools.append(
        {
            "name": FINAL_ANSWER_TOOL,
            "description": "Give the final answer to the user. Call this exactly once, last.",
            "input_schema": ANSWER_SCHEMA,
            "strict": True,
        }
    )
    return tools


def result_for_model(result: ToolResult) -> str:
    """The tool result as compact JSON for the model (rows capped, chunk text included)."""
    payload: dict[str, Any] = {"result_id": result.result_id, "status": result.status}
    if result.status == "ok":
        payload["columns"] = result.columns
        payload["rows"] = result.rows[:ROWS_FOR_MODEL]
        payload["row_count"] = result.row_count
        if result.row_count > ROWS_FOR_MODEL:
            payload["note"] = f"first {ROWS_FOR_MODEL} of {result.row_count} rows shown"
    if result.assumptions:
        payload["assumptions"] = result.assumptions
    if result.chunks:
        payload["chunks"] = [
            {"chunk_id": c.chunk_id, "document": c.doc_title, "section": c.section,
             "text": c.content}
            for c in result.chunks
        ]  # fmt: skip
    if result.denied_by:
        payload["denied_by"] = result.denied_by
    if result.message:
        payload["message"] = result.message
    return json.dumps(payload, default=str)


def _text(message: Message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


def classify(
    deps: AgentDeps, question: str, totals: UsageTotals, trace: Span
) -> tuple[GuardCategory, str]:
    model = deps.settings.model_small or ""
    span = trace.child("guard", as_type="guardrail", model=model, input=question)
    message = deps.client.messages.create(
        model=model,
        max_tokens=GUARD_MAX_TOKENS,
        system=GUARD_SYSTEM,
        messages=[{"role": "user", "content": question}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": GUARD_SCHEMA}},
    )
    cost = totals.add(model, message)
    category: GuardCategory = "in_scope"
    reason = "guard reply was not valid JSON; treated as in scope"
    try:
        verdict = json.loads(_text(message))
        category, reason = verdict["category"], verdict["reason"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    span.end(
        output={"category": category, "reason": reason},
        usage_details=usage_details(message.usage),
        cost_details={"total": cost},
    )
    return category, reason


def run_agent(
    deps: AgentDeps, persona_id: str, question: str, today: date | None = None
) -> Iterator[Event]:
    get_persona(persona_id)  # fail fast on an unknown persona, before any model call
    today = today or date.today()
    totals = UsageTotals()
    trace = deps.tracer.trace(
        "chat", input={"question": question}, metadata={"persona": persona_id}
    )
    if trace.trace_id:
        yield Event(type="trace_id", data={"trace_id": trace.trace_id})

    answer: Answer | None = None
    try:
        yield Event(type="step", data={"step": "guard", "label": "Checking the question"})
        category, reason = classify(deps, question, totals, trace)
        yield Event(type="step", data={"step": "guard_result", "category": category})
        if category == "out_of_scope":
            answer = Answer(text=OUT_OF_SCOPE_REPLY, issues=[f"out of scope: {reason}"])
        else:
            answer = yield from _answer(deps, persona_id, question, today, totals, trace)
            if category == "injection_suspected":
                answer.issues.append(f"injection suspected: {reason}")
    except anthropic.APIError as error:
        yield Event(type="error", data={"message": f"model call failed: {error.message}"})
    finally:
        trace.end(
            output=answer.model_dump() if answer else None,
            metadata={"persona": persona_id, "usage": totals.as_dict()},
        )
        deps.tracer.flush()

    if answer is not None:
        yield Event(type="answer", data=answer.model_dump())
    yield Event(type="usage", data=totals.as_dict())


def _answer(
    deps: AgentDeps,
    persona_id: str,
    question: str,
    today: date,
    totals: UsageTotals,
    trace: Span,
) -> Generator[Event, None, Answer]:
    """The tool-use loop. Generator: yields progress events, returns the Answer."""
    model = deps.settings.model_main or ""
    persona = get_persona(persona_id)
    ctx = ToolContext(persona=persona, pools=deps.pools, embed_query=deps.embed_query, today=today)
    system = agent_system_prompt(persona, today)
    tools = tool_definitions()
    messages: list[MessageParam] = [{"role": "user", "content": question}]
    tool_calls = 0
    seen_calls: dict[str, str] = {}  # (tool, input) -> result_id of the first identical call

    for _ in range(MAX_MODEL_CALLS):
        span = trace.child("main", as_type="generation", model=model, input=messages[-1])
        message = deps.client.messages.create(
            model=model,
            max_tokens=MAIN_MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": deps.settings.agent_effort},
        )
        cost = totals.add(model, message)
        span.end(
            output=[block.model_dump() for block in message.content],
            usage_details=usage_details(message.usage),
            cost_details={"total": cost},
            metadata={"stop_reason": message.stop_reason},
        )

        if message.stop_reason == "refusal":
            sql, denials = evidence(ctx.results)
            return Answer(
                text="I can't help with that request.",
                sql=sql,
                denials=denials,
                issues=["model refused"],
            )

        tool_uses = [block for block in message.content if block.type == "tool_use"]
        final = next((t for t in tool_uses if t.name == FINAL_ANSWER_TOOL), None)
        if final is not None:
            yield Event(type="step", data={"step": "answer", "label": "Writing the answer"})
            try:
                model_answer = ModelAnswer.model_validate(final.input)
            except ValueError:
                sql, denials = evidence(ctx.results)
                return Answer(
                    text=_text(message).strip() or "I could not produce an answer.",
                    sql=sql,
                    denials=denials,
                    issues=["final_answer input did not match the schema"],
                )
            return assemble_answer(model_answer, ctx.results)

        if message.stop_reason == "tool_use" and tool_uses:
            messages.append({"role": "assistant", "content": message.content})
            results: list[ToolResultBlockParam] = []
            for tool_use in tool_uses:
                if tool_calls >= MAX_TOOL_CALLS:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": "Tool call limit reached. Answer now with what you have.",
                            "is_error": True,
                        }
                    )
                    continue
                tool_calls += 1
                arguments = dict(tool_use.input) if isinstance(tool_use.input, dict) else {}
                call_key = json.dumps([tool_use.name, arguments], sort_keys=True, default=str)
                if call_key in seen_calls:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Same call as {seen_calls[call_key]}; use that result.",
                            "is_error": True,
                        }
                    )
                    continue
                yield Event(type="tool_call", data={"tool": tool_use.name, "input": arguments})
                tool_span = trace.child(tool_use.name, as_type="tool", input=arguments)
                started = time.monotonic()
                result = call_tool(ctx, tool_use.name, arguments)
                seen_calls[call_key] = result.result_id
                summary = {
                    "result_id": result.result_id,
                    "tool": result.tool,
                    "status": result.status,
                    "row_count": result.row_count,
                    "denied_by": result.denied_by,
                    "message": result.message,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
                tool_span.end(output=summary)
                yield Event(type="tool_result", data=summary)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_for_model(result),
                        "is_error": result.status == "error",
                    }
                )
            messages.append({"role": "user", "content": results})
            continue

        # Ended without final_answer: show the text, flagged, with whatever evidence exists.
        sql, denials = evidence(ctx.results)
        return Answer(
            text=_text(message).strip() or "I could not produce an answer.",
            sql=sql,
            denials=denials,
            issues=[f"ended without final_answer (stop_reason={message.stop_reason})"],
        )

    sql, denials = evidence(ctx.results)
    return Answer(
        text="I could not finish this question within the step limit. Try a narrower question.",
        sql=sql,
        denials=denials,
        issues=["model call limit reached"],
    )
