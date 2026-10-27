"""Checkers and the gate, on hand-built runs (no model, no database)."""

from typing import Any

from app.agent.record import RunRecord
from app.evals.cases import EvalCase, EvalConfig
from app.evals.checks import JudgeVerdict, Reference, run_checks
from app.evals.report import CaseResult, gate, score

CONFIG = EvalConfig.model_validate(
    {"thresholds": {"overall": 0.85, "access_control": 1.0}, "max_cost_usd": 1.0}
)


def case(expect: dict[str, Any], persona: str = "sales_rep_nz_south") -> EvalCase:
    return EvalCase.model_validate(
        {"id": "t", "category": "metrics", "persona": persona, "question": "q", "expect": expect}
    )


def run(
    text: str = "Answer.",
    table: dict[str, Any] | None = None,
    citations: list[str] | None = None,
    denials: int = 0,
    guard: str = "in_scope",
    tools: list[dict[str, Any]] | None = None,
) -> RunRecord:
    return RunRecord(
        answer={
            "text": text,
            "table": table,
            "citations": [{"source": f"data/documents/{d}.md"} for d in citations or []],
            "denials": [{"tool": "get_metric"}] * denials,
            "issues": [],
        },
        guard_category=guard,
        tool_results=tools or [],
    )


def failed(results: list[Any]) -> list[str]:
    return [r.name for r in results if not r.passed]


TOP = {"columns": ["customer_name", "revenue"], "rows": [["Acme Ltd", 1200.5], ["Kiwi Co", 900]]}


def test_contains_and_table_pass() -> None:
    assert failed(run_checks(case({"table": True, "contains": ["acme"]}), run(table=TOP))) == []


def test_missing_table_fails() -> None:
    assert failed(run_checks(case({"table": True}), run())) == ["table"]


def test_result_match_finds_strings_and_numbers() -> None:
    ref = Reference(columns=["customer_name"], rows=[["Acme Ltd"], ["Kiwi Co"]])
    expect = {"result_match": {"sql": "select 1", "key": "customer_name"}}
    assert failed(run_checks(case(expect), run(table=TOP), ref)) == []

    ref = Reference(columns=["revenue"], rows=[[1200.4]])
    expect = {"result_match": {"sql": "select 1", "key": "revenue"}}
    assert failed(run_checks(case(expect), run(table=TOP), ref)) == []


def test_result_match_reads_numbers_from_text() -> None:
    ref = Reference(columns=["breach_rate"], rows=[[80.0]])
    expect = {"result_match": {"sql": "select 1", "key": "breach_rate"}}
    assert failed(run_checks(case(expect), run(text="The breach rate was 80%."), ref)) == []


def test_result_match_top_n_and_missing_value() -> None:
    ref = Reference(columns=["customer_name"], rows=[["Acme Ltd"], ["Other Ltd"]])
    expect = {"result_match": {"sql": "select 1", "key": "customer_name", "top": 1}}
    assert failed(run_checks(case(expect), run(table=TOP), ref)) == []
    expect["result_match"]["top"] = 2
    assert failed(run_checks(case(expect), run(table=TOP), ref)) == ["result_match"]


def test_result_match_fails_without_reference_rows() -> None:
    expect = {"result_match": {"sql": "select 1", "key": "x"}}
    assert failed(run_checks(case(expect), run(table=TOP), None)) == ["result_match"]
    empty = Reference(columns=["x"], rows=[])
    assert failed(run_checks(case(expect), run(table=TOP), empty)) == ["result_match"]


def test_absent_detects_leaked_values() -> None:
    expect = {
        "result_match": {"sql": "s", "key": "revenue", "absent": True, "as_persona": "finance"}
    }
    leaked = Reference(columns=["revenue"], rows=[[900.0]])
    assert failed(run_checks(case(expect), run(table=TOP), leaked)) == ["result_absent"]
    hidden = Reference(columns=["revenue"], rows=[[5_000_000.0]])
    assert failed(run_checks(case(expect), run(table=TOP), hidden)) == []


def test_refusal_kinds() -> None:
    assert failed(run_checks(case({"refused": "denied"}), run(denials=1))) == []
    assert failed(run_checks(case({"refused": "denied"}), run())) == ["refused:denied"]
    assert failed(run_checks(case({"refused": "out_of_scope"}), run(guard="out_of_scope"))) == []
    # "any": no data presented counts as declining.
    assert failed(run_checks(case({"refused": "any"}), run())) == []
    assert failed(run_checks(case({"refused": "any"}), run(table=TOP))) == ["refused:any"]
    assert failed(run_checks(case({"refused": "none"}), run(denials=1))) == ["not_refused"]


def test_forbidden_columns_checks_tool_results_too() -> None:
    expect = {"forbidden_columns": ["margin_nzd"]}
    tools = [{"tool": "run_sql", "status": "ok", "columns": ["order_number", "margin_nzd"]}]
    assert failed(run_checks(case(expect), run(tools=tools))) == ["forbidden_columns"]
    denied = [{"tool": "run_sql", "status": "denied", "columns": []}]
    assert failed(run_checks(case(expect), run(tools=denied))) == []


def test_only_values() -> None:
    table = {"columns": ["region", "revenue"], "rows": [["NZ-SOUTH", 1], ["AU-EAST", 2]]}
    expect = {"only_values": {"column": "region", "values": ["NZ-SOUTH"]}}
    assert failed(run_checks(case(expect), run(table=table))) == ["only_values"]


def test_citations() -> None:
    expect = {"citations": ["returns-policy"], "no_citations_from": ["credit-terms"]}
    assert failed(run_checks(case(expect), run(citations=["returns-policy"]))) == []
    bad = run(citations=["credit-terms"])
    assert failed(run_checks(case(expect), bad)) == ["citations", "no_citations_from"]


def test_tools() -> None:
    tools = [{"tool": "get_metric", "status": "ok"}]
    assert failed(run_checks(case({"tools_not_used": ["*"]}), run(tools=tools))) == ["no_tools"]
    assert failed(run_checks(case({"tools_used": ["search_documents"]}), run(tools=tools))) == [
        "tools_used"
    ]


def test_judge_and_errors() -> None:
    expect = {"judge": "rubric"}
    assert failed(run_checks(case(expect), run())) == ["judge"]
    assert failed(run_checks(case(expect), run(), verdict=JudgeVerdict(True, "ok"))) == []
    broken = RunRecord(errors=["model call failed"])
    assert "no_errors" in failed(run_checks(case({"table": False}), broken))


def result(category: str, passed: bool) -> CaseResult:
    return CaseResult(
        case_id=f"{category}-{passed}",
        category=category,
        persona="finance",
        question="q",
        passed=passed,
        checks=[],
    )


def test_gate_requires_every_access_control_case() -> None:
    results = [result("metrics", True)] * 19 + [result("access_control", False)]
    passed, reasons = gate(results, CONFIG)
    assert not passed
    assert reasons == ["access_control 0% < 100%"]


def test_gate_overall_threshold() -> None:
    ok = [result("metrics", True)] * 17 + [result("metrics", False)] * 3
    assert gate(ok, CONFIG) == (True, [])
    low = [result("metrics", True)] * 16 + [result("metrics", False)] * 4
    assert gate(low, CONFIG)[0] is False


def test_gate_fails_when_aborted_or_empty() -> None:
    assert gate([result("metrics", True)], CONFIG, aborted="cost")[0] is False
    assert gate([], CONFIG)[0] is False


def test_score_by_category() -> None:
    results = [result("metrics", True), result("access_control", False)]
    scores = score(results)
    assert scores["metrics"].pass_rate == 1.0
    assert scores["access_control"].pass_rate == 0.0
