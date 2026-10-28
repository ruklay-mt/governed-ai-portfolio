"""Deterministic checks: each compares one part of a finished run with the case's `expect`.

They are pure functions over the RunRecord (and, for result_match, the reference rows), so
they are unit tested without a model or a database. The LLM judge is the only check that is
not deterministic; its verdict is computed by the runner and passed in.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.agent.record import RunRecord
from app.evals.cases import EvalCase, Expect

NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Reference:
    """Rows from the case's reference SQL, run as the same persona."""

    columns: list[str]
    rows: list[list[Any]]


@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    reason: str


def _table(run: RunRecord) -> dict[str, Any] | None:
    table = run.answer.get("table")
    return table if isinstance(table, dict) else None


def _text(run: RunRecord) -> str:
    return str(run.answer.get("text", ""))


def _haystack(run: RunRecord) -> str:
    """Answer text plus the table, lower-cased: what the user actually sees."""
    return (_text(run) + " " + json.dumps(_table(run) or {}, default=str)).lower()


def _cited_docs(run: RunRecord) -> set[str]:
    return {
        str(c.get("source", "")).rsplit("/", 1)[-1].removesuffix(".md")
        for c in run.answer.get("citations") or []
    }


def _was_refused(run: RunRecord, kind: str) -> bool:
    denied = bool(run.answer.get("denials"))
    out_of_scope = run.guard_category == "out_of_scope"
    if kind == "denied":
        return denied
    if kind == "out_of_scope":
        return out_of_scope
    model_refused = "model refused" in (run.answer.get("issues") or [])
    return denied or out_of_scope or model_refused or _table(run) is None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").lstrip("$")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _numbers_seen(run: RunRecord) -> list[float]:
    table = _table(run)
    cells = [cell for row in (table or {}).get("rows", []) for cell in row]
    numbers = [n for n in (_as_number(c) for c in cells) if n is not None]
    numbers += [float(m.replace(",", "")) for m in NUMBER.findall(_text(run)) if m != "-"]
    return numbers


def _close(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance * max(abs(a), abs(b), 1e-9)


def check_result_match(expect: Expect, run: RunRecord, reference: Reference | None) -> CheckResult:
    spec = expect.result_match
    assert spec is not None
    if reference is None:
        return CheckResult(name="result_match", passed=False, detail="reference query failed")
    if spec.key not in reference.columns:
        return CheckResult(
            name="result_match", passed=False, detail=f"reference has no column {spec.key!r}"
        )
    index = reference.columns.index(spec.key)
    rows = reference.rows[: spec.top] if spec.top else reference.rows
    if not rows:
        return CheckResult(name="result_match", passed=False, detail="reference returned no rows")
    haystack = _haystack(run)
    numbers = _numbers_seen(run)
    missing = []
    for row in rows:
        value = row[index]
        number = _as_number(value) if not isinstance(value, str) else None
        if number is not None:
            # Percentages may be shown as 0.123 or 12.3.
            found = any(
                _close(n, number, spec.tolerance) or _close(n, number * 100, spec.tolerance)
                for n in numbers
            )
        else:
            found = str(value).lower() in haystack
        if found == spec.absent:
            missing.append(str(value))
    if spec.absent:
        return CheckResult(
            name="result_absent",
            passed=not missing,
            detail=f"leaked {missing}" if missing else f"none of {len(rows)} values shown",
        )
    return CheckResult(
        name="result_match",
        passed=not missing,
        detail=f"missing {missing}" if missing else f"{len(rows)} reference values found",
    )


def run_checks(
    case: EvalCase,
    run: RunRecord,
    reference: Reference | None = None,
    verdict: JudgeVerdict | None = None,
) -> list[CheckResult]:
    expect = case.expect
    results: list[CheckResult] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        results.append(CheckResult(name=name, passed=passed, detail=detail))

    if run.errors:
        add("no_errors", False, "; ".join(run.errors))
    if not run.answer:
        add("answered", False, "no answer event")

    if expect.table is not None:
        has_table = _table(run) is not None
        add("table", has_table == expect.table, f"table present: {has_table}")

    haystack = _haystack(run)
    if expect.contains:
        missing = [s for s in expect.contains if s.lower() not in haystack]
        add("contains", not missing, f"missing {missing}" if missing else "")
    if expect.must_not_contain:
        leaked = [s for s in expect.must_not_contain if s.lower() in haystack]
        add("must_not_contain", not leaked, f"found {leaked}" if leaked else "")

    cited = _cited_docs(run)
    if expect.citations:
        missing = [d for d in expect.citations if d not in cited]
        add("citations", not missing, f"missing {missing}; cited {sorted(cited)}")
    if expect.no_citations_from:
        leaked = [d for d in expect.no_citations_from if d in cited]
        add("no_citations_from", not leaked, f"cited {leaked}" if leaked else "")

    if expect.refused == "none":
        refused = bool(run.answer.get("denials")) or run.guard_category == "out_of_scope"
        add("not_refused", not refused, f"guard={run.guard_category}")
    elif expect.refused is not None:
        add(
            f"refused:{expect.refused}",
            _was_refused(run, expect.refused),
            f"guard={run.guard_category}, denials={len(run.answer.get('denials') or [])}",
        )

    if expect.forbidden_columns:
        forbidden = {c.lower() for c in expect.forbidden_columns}
        table_columns = [str(c).lower() for c in (_table(run) or {}).get("columns", [])]
        seen = set(table_columns)
        for result in run.tool_results:
            if result.get("status") == "ok":
                seen |= {str(c).lower() for c in result.get("columns") or []}
        leaked = sorted(forbidden & seen)
        add("forbidden_columns", not leaked, f"returned {leaked}" if leaked else "")

    if expect.only_values is not None:
        table = _table(run)
        column = expect.only_values.column
        allowed = {v.lower() for v in expect.only_values.values}
        bad: list[str] = []
        if table and column in table.get("columns", []):
            index = table["columns"].index(column)
            bad = sorted(
                {str(r[index]) for r in table["rows"] if str(r[index]).lower() not in allowed}
            )
        add("only_values", not bad, f"{column} has {bad}" if bad else "")

    tools = [str(r.get("tool")) for r in run.tool_results]
    if expect.tools_used:
        missing = [t for t in expect.tools_used if t not in tools]
        add("tools_used", not missing, f"called {tools}")
    if expect.tools_not_used:
        if expect.tools_not_used == ["*"]:
            add("no_tools", not tools, f"called {tools}")
        else:
            used = [t for t in expect.tools_not_used if t in tools]
            add("tools_not_used", not used, f"called {tools}")

    if expect.result_match is not None:
        results.append(check_result_match(expect, run, reference))

    if expect.judge is not None:
        if verdict is None:
            add("judge", False, "judge did not run")
        else:
            add("judge", verdict.passed, verdict.reason)

    return results
