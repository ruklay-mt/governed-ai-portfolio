"""Cost guards (spec §16): per-session and per-IP question limits, and a daily LLM budget.

Counters live in Postgres (ops.rate_limits, ops.daily_spend) because Cloud Run instances come
and go. Only the app_service login writes them; it has no access to business data.

Every failure fails closed: if the guard cannot read or write its counters, the request is
served in replay mode (cached answers only), never as an unmetered live call.
"""

import hashlib
import hmac
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from app.agent.db import persona_url, pool_options
from app.config import Settings

logger = logging.getLogger(__name__)

Mode = Literal["live", "replay", "limited"]


class Admission(BaseModel):
    mode: Mode  # live: run the agent; replay: cached answers only; limited: over a rate limit
    reason: str | None = None
    spent_today_usd: float | None = None


class CostGuard:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: ConnectionPool | None = None
        password = settings.app_service_db_password
        if settings.database_url and password is not None:
            self._key = password.get_secret_value().encode()
            self._pool = ConnectionPool(
                persona_url(settings.database_url, "app_service", password.get_secret_value()),
                max_size=2,
                open=True,
                **pool_options(),
            )

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection]:
        assert self._pool is not None
        with self._pool.connection() as conn, conn.transaction():
            yield conn

    def _ip_key(self, ip: str) -> str:
        # Keyed hash: the raw address is never stored, and the hash cannot be reversed by
        # hashing every IPv4 address without the key.
        return hmac.new(self._key, ip.encode(), hashlib.sha256).hexdigest()

    def admit(self, session_id: str, ip: str) -> Admission:
        if self._pool is None:
            return Admission(mode="replay", reason="cost guard not configured")
        try:
            with self._transaction() as conn:
                row = conn.execute(
                    "select coalesce(sum(spend_usd), 0) from ops.daily_spend"
                    " where spend_date = current_date"
                ).fetchone()
                spent = float(row[0]) if row else 0.0
                if spent >= self._settings.daily_budget_usd:
                    return Admission(
                        mode="replay", reason="daily budget reached", spent_today_usd=spent
                    )
                for scope, key, limit in (
                    ("session", session_id, self._settings.session_question_limit),
                    ("ip", self._ip_key(ip), self._settings.ip_daily_question_limit),
                ):
                    count_row = conn.execute(
                        "insert into ops.rate_limits"
                        " (scope, limit_key, window_date, question_count)"
                        " values (%s, %s, current_date, 1)"
                        " on conflict (scope, limit_key, window_date)"
                        " do update set question_count = ops.rate_limits.question_count + 1"
                        " returning question_count",
                        (scope, key),
                    ).fetchone()
                    if count_row and count_row[0] > limit:
                        return Admission(
                            mode="limited",
                            reason=f"{scope} limit of {limit} live questions reached",
                            spent_today_usd=spent,
                        )
        except psycopg.Error:
            logger.exception("cost guard unavailable; serving replay")
            return Admission(mode="replay", reason="cost guard unavailable")
        return Admission(mode="live", spent_today_usd=spent)

    def record_spend(self, cost_usd: float) -> None:
        if self._pool is None:
            return
        try:
            with self._transaction() as conn:
                conn.execute(
                    "insert into ops.daily_spend (spend_date, spend_usd, live_questions)"
                    " values (current_date, %s, 1)"
                    " on conflict (spend_date) do update set"
                    " spend_usd = ops.daily_spend.spend_usd + excluded.spend_usd,"
                    " live_questions = ops.daily_spend.live_questions + 1,"
                    " updated_at = now()",
                    (cost_usd,),
                )
        except psycopg.Error:
            logger.exception("could not record spend of %s USD", cost_usd)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
