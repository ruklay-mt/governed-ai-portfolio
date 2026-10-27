"""Cost guards against a real database, as the app_service login (spec §16).

Covers the phase criterion "exceeding the budget switches to replay mode". Skipped without a
database or APP_SERVICE_DB_PASSWORD (CI sets a throwaway one; locally run `make db-users`).
"""

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from app.config import Settings
from app.ops.guards import CostGuard


@pytest.fixture
def make_guard() -> Iterator[type[CostGuard]]:
    base = Settings()
    if base.database_url is None or base.app_service_db_password is None:
        pytest.skip("needs DATABASE_URL and APP_SERVICE_DB_PASSWORD")
    with psycopg.connect(base.database_url) as conn:
        row = conn.execute("select to_regclass('ops.daily_spend') is not null").fetchone()
    if not row or not row[0]:
        pytest.skip("ops tables missing (run make db-migrate)")
    guards: list[CostGuard] = []

    class TrackedGuard(CostGuard):
        def __init__(self, settings: Settings) -> None:
            super().__init__(settings)
            guards.append(self)

    yield TrackedGuard
    for guard in guards:
        guard.close()


def test_budget_reached_means_replay(make_guard: type[CostGuard]) -> None:
    guard = make_guard(Settings(daily_budget_usd=0.0))
    admission = guard.admit(f"s-{uuid.uuid4()}", "198.51.100.1")
    assert admission.mode == "replay"
    assert admission.reason == "daily budget reached"


def test_session_limit(make_guard: type[CostGuard]) -> None:
    guard = make_guard(Settings(daily_budget_usd=1000.0, session_question_limit=2))
    session = f"s-{uuid.uuid4()}"
    ip = f"198.51.100.{uuid.uuid4().int % 250}"
    modes = [guard.admit(session, ip).mode for _ in range(3)]
    assert modes == ["live", "live", "limited"]


def test_ip_limit_spans_sessions(make_guard: type[CostGuard]) -> None:
    guard = make_guard(Settings(daily_budget_usd=1000.0, ip_daily_question_limit=1))
    ip = f"203.0.113.{uuid.uuid4().int % 250}-{uuid.uuid4()}"
    assert guard.admit(f"s-{uuid.uuid4()}", ip).mode == "live"
    assert guard.admit(f"s-{uuid.uuid4()}", ip).mode == "limited"


def test_recorded_spend_counts_against_budget(make_guard: type[CostGuard]) -> None:
    probe = make_guard(Settings(daily_budget_usd=1000.0))
    spent = probe.admit(f"s-{uuid.uuid4()}", f"probe-{uuid.uuid4()}").spent_today_usd or 0.0
    probe.record_spend(0.000001)
    guard = make_guard(Settings(daily_budget_usd=spent + 0.0000005))
    assert guard.admit(f"s-{uuid.uuid4()}", f"probe-{uuid.uuid4()}").mode == "replay"


def test_no_app_service_password_fails_closed() -> None:
    guard = CostGuard(Settings(app_service_db_password=None))
    assert guard.admit("session-1", "198.51.100.9").mode == "replay"
