"""Run the agent to completion and keep everything a checker needs (samples and evals).

The chat endpoint streams events to the browser; offline runners want the whole run as one
record instead: the answer card, usage, every tool result summary and the guard's verdict.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.agent.loop import AgentDeps, run_agent


class RunRecord(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    guard_category: str | None = None
    errors: list[str] = Field(default_factory=list)
    trace_id: str | None = None

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("cost_usd", 0.0))

    @property
    def tools(self) -> list[str]:
        return [f"{r['tool']}:{r['status']}" for r in self.tool_results]


def collect_run(
    deps: AgentDeps,
    persona_id: str,
    question: str,
    today: date | None = None,
    trace_metadata: dict[str, str] | None = None,
) -> RunRecord:
    record = RunRecord()
    for event in run_agent(deps, persona_id, question, today, trace_metadata):
        if event.type == "answer":
            record.answer = event.data
        elif event.type == "usage":
            record.usage = event.data
        elif event.type == "tool_result":
            record.tool_results.append(event.data)
        elif event.type == "trace_id":
            record.trace_id = str(event.data["trace_id"])
        elif event.type == "step" and event.data.get("step") == "guard_result":
            record.guard_category = str(event.data["category"])
        elif event.type == "error":
            record.errors.append(str(event.data["message"]))
    return record
