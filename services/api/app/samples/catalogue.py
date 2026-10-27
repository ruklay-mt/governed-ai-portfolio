"""Sample questions and their precomputed answers (spec §16).

Sample questions are always served from answers/<id>.json when the file exists: they are the
first thing a visitor clicks, so they should be instant and free. Outside the samples, the
cached answers also back replay mode when the daily budget is spent.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

SAMPLES_FILE = Path(__file__).parent / "samples.yml"
ANSWERS_DIR = Path(__file__).parent / "answers"


class Expectation(BaseModel):
    table: bool = False
    citations: bool = False
    denied: bool = False
    contains: list[str] = Field(default_factory=list)


class Sample(BaseModel):
    id: str
    persona: str
    question: str
    expect: Expectation = Field(default_factory=Expectation)


class CachedAnswer(BaseModel):
    """What samples-build stores: the answer card, its usage and when it was built."""

    sample_id: str
    built_at: str
    answer: dict[str, Any]
    usage: dict[str, Any]


def _normalise(text: str) -> str:
    return " ".join(text.lower().split()).rstrip("?.! ")


@lru_cache
def load_samples(path: Path = SAMPLES_FILE) -> tuple[Sample, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(Sample.model_validate(item) for item in data["samples"])


def find_sample(persona_id: str, question: str) -> Sample | None:
    wanted = _normalise(question)
    for sample in load_samples():
        if sample.persona == persona_id and _normalise(sample.question) == wanted:
            return sample
    return None


def cached_answer(sample_id: str, answers_dir: Path = ANSWERS_DIR) -> CachedAnswer | None:
    path = answers_dir / f"{sample_id}.json"
    if not path.exists():
        return None
    return CachedAnswer.model_validate(json.loads(path.read_text(encoding="utf-8")))


def check_expectations(sample: Sample, answer: dict[str, Any]) -> list[str]:
    """Problems with an answer against the sample's expectations; empty means it passed."""
    problems: list[str] = []
    expect = sample.expect
    if expect.table and not answer.get("table"):
        problems.append("expected a table")
    if expect.citations and not answer.get("citations"):
        problems.append("expected citations")
    if expect.denied and not answer.get("denials"):
        problems.append("expected a denial")
    if not expect.denied and answer.get("denials"):
        problems.append("unexpected denial")
    haystack = (answer.get("text", "") + " " + json.dumps(answer.get("table") or {})).lower()
    problems += [f"missing {s!r}" for s in expect.contains if s.lower() not in haystack]
    return problems
