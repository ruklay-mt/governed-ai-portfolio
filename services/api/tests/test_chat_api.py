import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app import routes
from app.agent.loop import Event
from app.main import app
from app.ops.guards import Admission
from app.runtime import Runtime
from app.samples.catalogue import CachedAnswer, load_presets, load_samples


class FakeGuard:
    def __init__(self, admission: Admission) -> None:
        self.admission = admission
        self.spent: list[float] = []

    def admit(self, session_id: str, ip: str) -> Admission:
        return self.admission

    def record_spend(self, cost_usd: float) -> None:
        self.spent.append(cost_usd)


def client_with(guard: FakeGuard) -> TestClient:
    runtime = Runtime(deps=cast(Any, None), guard=cast(Any, guard))
    app.dependency_overrides[routes._runtime] = lambda: runtime
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def events(response_text: str) -> list[tuple[str, dict[str, Any]]]:
    parsed = []
    for block in response_text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def chat(client: TestClient, message: str, persona: str = "sales_rep_nz_south") -> Any:
    return client.post(
        "/api/chat", json={"persona": persona, "session_id": "session-123", "message": message}
    )


def test_personas_lists_the_four_demo_users() -> None:
    response = TestClient(app).get("/api/personas")
    assert response.status_code == 200
    assert {p["id"] for p in response.json()} == {
        "sales_rep_nz_south",
        "sales_manager",
        "finance",
        "support",
    }


def test_samples_cover_every_persona() -> None:
    response = TestClient(app).get("/api/samples")
    by_persona: dict[str, int] = {}
    for sample in response.json():
        by_persona[sample["persona"]] = by_persona.get(sample["persona"], 0) + 1
    assert all(count >= 5 for count in by_persona.values())
    assert len(by_persona) == 4


def test_budget_reached_switches_to_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "run_agent", lambda *a: pytest.fail("agent must not run"))
    guard = FakeGuard(Admission(mode="replay", reason="daily budget reached"))
    response = chat(client_with(guard), "Something not in the samples")
    parsed = events(response.text)
    assert parsed[0] == ("mode", {"mode": "replay", "reason": "daily budget reached"})
    assert "paused" in parsed[1][1]["text"]
    assert guard.spent == []


def test_rate_limited_does_not_run_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "run_agent", lambda *a: pytest.fail("agent must not run"))
    guard = FakeGuard(Admission(mode="limited", reason="session limit of 15 live questions"))
    parsed = events(chat(client_with(guard), "Another question").text)
    assert parsed[0][1]["mode"] == "limited"


def test_sample_question_is_served_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = load_samples()[0]
    cached = CachedAnswer(
        sample_id=sample.id, built_at="2026-10-27", answer={"text": "Cached."}, usage={}
    )
    monkeypatch.setattr(routes, "cached_answer", lambda sample_id: cached)
    monkeypatch.setattr(routes, "run_agent", lambda *a: pytest.fail("agent must not run"))
    guard = FakeGuard(Admission(mode="live"))
    parsed = events(chat(client_with(guard), sample.question.upper(), sample.persona).text)
    assert parsed[0][1]["mode"] == "cached"
    assert parsed[1] == ("answer", {"text": "Cached."})


def test_live_answer_streams_and_records_spend(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_agent(*_: Any) -> Iterator[Event]:
        yield Event(type="tool_call", data={"tool": "get_metric", "input": {}})
        yield Event(type="answer", data={"text": "Live."})
        yield Event(type="usage", data={"cost_usd": 0.0123})

    monkeypatch.setattr(routes, "run_agent", fake_agent)
    guard = FakeGuard(Admission(mode="live"))
    response = chat(client_with(guard), "Something not in the samples")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [name for name, _ in events(response.text)] == ["mode", "tool_call", "answer", "usage"]
    assert guard.spent == [0.0123]


def test_unknown_persona_is_rejected() -> None:
    response = chat(client_with(FakeGuard(Admission(mode="live"))), "Hi", persona="admin")
    assert response.status_code == 422


def test_long_message_is_rejected() -> None:
    response = chat(client_with(FakeGuard(Admission(mode="live"))), "x" * 501)
    assert response.status_code == 422


def test_client_ip_uses_first_forwarded_hop() -> None:
    class FakeRequest:
        headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
        client = None

    assert routes.client_ip(cast(Any, FakeRequest())) == "203.0.113.7"


def test_presets_are_the_eval_cases_marked_preset() -> None:
    response = TestClient(app).get("/api/presets")
    presets = response.json()
    assert len(presets) >= 6
    assert all(p["eval_file"].startswith("evals/cases/") for p in presets)
    assert {p["category"] for p in presets} <= {"access_control", "robustness"}


def test_preset_runs_live_when_budget_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = load_presets()[0]

    def fake_agent(*_: Any) -> Iterator[Event]:
        yield Event(type="answer", data={"text": "Live refusal."})
        yield Event(type="usage", data={"cost_usd": 0.01})

    monkeypatch.setattr(routes, "run_agent", fake_agent)
    guard = FakeGuard(Admission(mode="live"))
    parsed = events(chat(client_with(guard), preset.question, preset.persona).text)
    assert parsed[0][1]["mode"] == "live"
    assert guard.spent == [0.01]


def test_preset_replays_cached_answer_when_live_is_paused(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = load_presets()[0]
    cached = CachedAnswer(
        sample_id=preset.id, built_at="2026-10-28", answer={"text": "Refused."}, usage={}
    )
    monkeypatch.setattr(routes, "cached_answer", lambda item_id: cached)
    monkeypatch.setattr(routes, "run_agent", lambda *a: pytest.fail("agent must not run"))
    guard = FakeGuard(Admission(mode="replay", reason="daily budget reached"))
    parsed = events(chat(client_with(guard), preset.question, preset.persona).text)
    assert parsed[0][1]["mode"] == "replay"
    assert parsed[1] == ("answer", {"text": "Refused."})
    assert parsed[2][1]["cost_usd"] == 0.0
