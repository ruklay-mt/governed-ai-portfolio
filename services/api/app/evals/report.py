"""Scores, the merge gate and the run report (JSON for machines, Markdown for people)."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.evals.cases import CATEGORIES, EvalConfig
from app.evals.checks import CheckResult


class CaseResult(BaseModel):
    case_id: str
    attempt: int = 1
    category: str
    persona: str
    question: str
    preset: bool = False
    passed: bool
    checks: list[CheckResult]
    answer: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int | None = None
    cost_usd: float = 0.0
    trace_id: str | None = None


class CategoryScore(BaseModel):
    total: int
    passed: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class RunSummary(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    git_sha: str | None
    trigger: str
    model_main: str
    model_small: str
    total: int
    passed: int
    pass_rate: float
    by_category: dict[str, CategoryScore]
    cost_usd: float
    gate_passed: bool
    gate_reasons: list[str]
    aborted: str | None = None


def score(results: list[CaseResult]) -> dict[str, CategoryScore]:
    by_category: dict[str, CategoryScore] = {}
    for category in CATEGORIES:
        in_category = [r for r in results if r.category == category]
        if in_category:
            by_category[category] = CategoryScore(
                total=len(in_category), passed=sum(r.passed for r in in_category)
            )
    return by_category


def gate(
    results: list[CaseResult], config: EvalConfig, aborted: str | None = None
) -> tuple[bool, list[str]]:
    """Whether the run may merge, and why not. Thresholds are never lowered to pass."""
    reasons: list[str] = []
    if aborted:
        reasons.append(f"run aborted: {aborted}")
    if not results:
        reasons.append("no cases ran")
        return False, reasons
    overall = sum(r.passed for r in results) / len(results)
    if overall < config.thresholds.overall:
        reasons.append(f"overall {overall:.0%} < {config.thresholds.overall:.0%}")
    access = score(results).get("access_control")
    if access is not None and access.pass_rate < config.thresholds.access_control:
        reasons.append(
            f"access_control {access.pass_rate:.0%} < {config.thresholds.access_control:.0%}"
        )
    return not reasons, reasons


def to_markdown(summary: RunSummary, results: list[CaseResult]) -> str:
    verdict = "PASSED" if summary.gate_passed else "FAILED"
    lines = [
        f"## Eval gate {verdict}: {summary.passed}/{summary.total} ({summary.pass_rate:.0%})",
        "",
        f"Run `{summary.run_id}` · {summary.model_main} + {summary.model_small} · "
        f"cost ${summary.cost_usd:.4f} · commit `{(summary.git_sha or 'local')[:8]}`",
        "",
    ]
    lines += [f"- {reason}" for reason in summary.gate_reasons]
    lines += ["", "| Category | Passed | Rate |", "|---|---|---|"]
    for category, s in summary.by_category.items():
        lines.append(f"| {category} | {s.passed}/{s.total} | {s.pass_rate:.0%} |")
    failed = [r for r in results if not r.passed]
    if failed:
        lines += ["", "### Failing cases", ""]
        for r in failed:
            lines.append(f"**{r.case_id}** ({r.category}, {r.persona}): {r.question}")
            lines += [f"- `{c.name}`: {c.detail}" for c in r.checks if not c.passed]
            lines.append(f"- answer: {str(r.answer.get('text', ''))[:300]}")
            lines.append(f"- tools: {', '.join(r.tools) or '-'} · trace: {r.trace_id or '-'}")
            lines += [
                f"- {t.get('tool')} {t.get('status')}: {t.get('message')}"
                for t in r.tool_results
                if t.get("status") != "ok" and t.get("message")
            ]
            lines.append("")
    return "\n".join(lines) + "\n"


def write_report(summary: RunSummary, results: list[CaseResult], reports_dir: Path) -> Path:
    """Write <stamp>.json and <stamp>.md; returns the Markdown path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary.started_at.replace(":", "").replace("-", "")[:15]
    base = reports_dir / f"{stamp}-{summary.run_id[:8]}"
    payload = {
        "summary": summary.model_dump()
        | {
            "by_category": {
                k: v.model_dump() | {"pass_rate": v.pass_rate}
                for k, v in summary.by_category.items()
            }
        },
        "results": [r.model_dump() for r in results],
    }
    base.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    markdown = base.with_suffix(".md")
    markdown.write_text(to_markdown(summary, results), encoding="utf-8")
    return markdown
