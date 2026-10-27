"""LLM-as-judge for free-text quality, used only where a deterministic check cannot decide.

The small model grades the answer against the case's rubric and returns pass/fail with a
reason. It sees the question, the answer text and the cited passages' titles, never the
persona's raw data, and its cost is counted in the eval run like any other call.
"""

import json
from typing import Any

import anthropic

from app.agent.cost import call_cost_usd
from app.evals.checks import JudgeVerdict

JUDGE_MAX_TOKENS = 1000

JUDGE_SYSTEM = """\
You grade answers from an internal data assistant against a rubric written by its developer.
Pass the answer only if it meets every point of the rubric. Judge only what the rubric asks;
do not penalise style or length unless the rubric does. Reply with your verdict and a
one-sentence reason."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"passed": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["passed", "reason"],
    "additionalProperties": False,
}


def judge(
    client: anthropic.Anthropic, model: str, question: str, answer: dict[str, Any], rubric: str
) -> tuple[JudgeVerdict, float]:
    """The verdict and the cost of the call in USD."""
    citations = [f"{c.get('doc_title')} - {c.get('section')}" for c in answer.get("citations", [])]
    prompt = (
        f"Question:\n{question}\n\nAnswer:\n{answer.get('text', '')}\n\n"
        f"Cited passages: {json.dumps(citations)}\n\nRubric:\n{rubric}"
    )
    message = client.messages.create(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    cost = call_cost_usd(model, message.usage)
    text = "".join(block.text for block in message.content if block.type == "text")
    try:
        data = json.loads(text)
        return JudgeVerdict(passed=bool(data["passed"]), reason=str(data["reason"])), cost
    except (json.JSONDecodeError, KeyError, TypeError):
        return JudgeVerdict(passed=False, reason="judge reply was not valid JSON"), cost
