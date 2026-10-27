"""Eval cases: one YAML entry per question, with every check that must pass (spec §12).

A case passes only when all of its checks pass. Access-control cases usually combine a
refusal check with leakage checks, because "the agent said no" is not enough: the evidence
it returned must not contain the hidden data either.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.personas import PERSONAS

REPO_ROOT = Path(__file__).resolve().parents[4]
EVALS_DIR = REPO_ROOT / "evals"
CASES_DIR = EVALS_DIR / "cases"
CONFIG_FILE = EVALS_DIR / "config.yml"

Category = Literal["metrics", "retrieval", "access_control", "robustness"]
CATEGORIES: tuple[Category, ...] = ("metrics", "retrieval", "access_control", "robustness")
# denied: a tool was denied by the database, SQL guard or semantic layer.
# out_of_scope: the guard stopped the question before the main model ran.
# any: either of those, a model refusal, or an answer that presents no data table.
# none: no denial and not out of scope (the question should simply be answered).
Refusal = Literal["denied", "out_of_scope", "any", "none"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResultMatch(Strict):
    """Compare the answer with a reference query run as the same persona.

    The first `top` rows of the reference (all rows if omitted) are taken, and every value of
    `key` must appear in the answer table (or its text). Numbers match within `tolerance`
    (relative). The SQL may use %(today)s, bound to the date the agent was given.

    Leakage form: `as_persona` runs the reference as a more privileged persona, and
    `absent: true` requires that none of its values appear in the answer.
    """

    sql: str
    key: str
    top: int | None = None
    tolerance: float = 0.01
    as_persona: str | None = None
    absent: bool = False


class OnlyValues(Strict):
    column: str
    values: list[str]


class Expect(Strict):
    table: bool | None = None
    contains: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)  # document ids that must be cited
    no_citations_from: list[str] = Field(default_factory=list)
    refused: Refusal | None = None
    forbidden_columns: list[str] = Field(default_factory=list)
    only_values: OnlyValues | None = None
    tools_used: list[str] = Field(default_factory=list)
    tools_not_used: list[str] = Field(default_factory=list)  # ["*"] = no tool calls at all
    result_match: ResultMatch | None = None
    judge: str | None = None  # rubric for the LLM judge; use only for free-text quality


class EvalCase(Strict):
    id: str
    category: Category
    persona: str
    question: str
    preset: bool = False  # also shown in the "Try to break it" panel (spec §10)
    note: str | None = None  # why this case exists, for reviewers
    expect: Expect

    @model_validator(mode="after")
    def check(self) -> "EvalCase":
        match = self.expect.result_match
        for persona in (self.persona, match.as_persona if match else None):
            if persona is not None and persona not in PERSONAS:
                raise ValueError(f"{self.id}: unknown persona {persona!r}")
        if self.expect == Expect():
            raise ValueError(f"{self.id}: a case needs at least one check")
        return self


class Thresholds(Strict):
    overall: float
    access_control: float


class EvalConfig(Strict):
    thresholds: Thresholds
    max_cost_usd: float


def load_cases(cases_dir: Path = CASES_DIR) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted(cases_dir.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cases += [EvalCase.model_validate(item) for item in data.get("cases", [])]
    ids = [c.id for c in cases]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        raise ValueError(f"duplicate case ids: {', '.join(duplicates)}")
    return cases


@lru_cache
def load_config(path: Path = CONFIG_FILE) -> EvalConfig:
    return EvalConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
