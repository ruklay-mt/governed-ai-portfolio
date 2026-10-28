"""The golden set itself: it loads, it is the size the spec asks for, and its SQL is sane."""

import pytest

from app.agent.sql_guard import guard_sql
from app.evals.cases import EvalCase, load_cases, load_config


def test_cases_load_with_unique_ids() -> None:
    cases = load_cases()
    assert len({c.id for c in cases}) == len(cases)


def test_golden_set_covers_every_category() -> None:
    counts: dict[str, int] = {}
    for case in load_cases():
        counts[case.category] = counts.get(case.category, 0) + 1
    # spec §12 [MVP]: ~10 metrics, 6 retrieval, 10 access control, 4 robustness.
    assert counts["metrics"] >= 10
    assert counts["retrieval"] >= 6
    assert counts["access_control"] >= 10
    assert counts["robustness"] >= 4


def test_presets_are_attack_cases() -> None:
    presets = [c for c in load_cases() if c.preset]
    assert presets
    assert {c.category for c in presets} <= {"access_control", "robustness"}


@pytest.mark.parametrize(
    "case", [c for c in load_cases() if c.expect.result_match], ids=lambda c: c.id
)
def test_reference_sql_passes_the_sql_guard(case: EvalCase) -> None:
    # Reference queries are trusted, but holding them to the agent's own rules keeps them
    # read-only and limited to the marts the agent can see.
    assert case.expect.result_match is not None
    guard_sql(case.expect.result_match.sql.replace("%(today)s", "'2026-10-28'"))


def test_thresholds_match_the_spec() -> None:
    thresholds = load_config().thresholds
    assert thresholds.access_control == 1.0
    assert thresholds.overall >= 0.85


def test_case_without_checks_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one check"):
        EvalCase.model_validate(
            {"id": "x", "category": "metrics", "persona": "finance", "question": "q", "expect": {}}
        )


def test_unknown_persona_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown persona"):
        EvalCase.model_validate(
            {
                "id": "x",
                "category": "metrics",
                "persona": "ceo",
                "question": "q",
                "expect": {"table": True},
            }
        )
