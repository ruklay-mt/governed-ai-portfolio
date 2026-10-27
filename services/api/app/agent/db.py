"""Connections for agent tools: one small pool per persona login (ADR 0008, CLAUDE.md rule 2).

Every tool call takes a connection from the caller's own pool and runs inside a transaction.
The login is read-only, owns nothing and cannot change its RLS scope, so whatever SQL runs
here, Postgres decides which rows and columns come back.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import psycopg
from psycopg_pool import ConnectionPool

from app.agent.personas import PERSONAS, Persona
from app.config import Settings

# Each persona login has `connection limit 10`; keep well under it across Cloud Run instances.
POOL_MAX_SIZE = 3
# Also set on the role (ALTER ROLE ... statement_timeout); repeated per transaction as defence
# in depth, since the SQL guard blocks SET but a role default is a soft setting.
STATEMENT_TIMEOUT = "8s"
# Neon can take a few seconds to wake from scale-to-zero.
CONNECT_TIMEOUT_SECONDS = 10
# Neon closes idle connections (and suspends the compute after a few idle minutes). A pool
# that hands out such a connection hangs on a dead socket for minutes, so every connection
# is checked before use and idle ones are dropped well before Neon drops them.
POOL_MAX_IDLE_SECONDS = 60


def pool_options() -> dict[str, Any]:
    """Settings shared by every pool: persona logins and app_service."""
    return {
        "min_size": 0,
        "max_idle": POOL_MAX_IDLE_SECONDS,
        "check": ConnectionPool.check_connection,
        "kwargs": {"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    }


def persona_url(database_url: str, login: str, password: str) -> str:
    """The owner URL with the user and password swapped for a persona login's."""
    url = urlparse(database_url.strip())
    host = url.hostname or "localhost"
    netloc = f"{login}:{quote(password.strip(), safe='')}@{host}" + (
        f":{url.port}" if url.port else ""
    )
    return urlunparse(url._replace(netloc=netloc))


class PersonaPools:
    """Lazily opened connection pools, one per persona login."""

    def __init__(self, settings: Settings) -> None:
        if settings.database_url is None:
            raise RuntimeError("DATABASE_URL is not set")
        self._settings = settings
        self._database_url = settings.database_url
        self._pools: dict[str, ConnectionPool] = {}

    def _pool(self, persona: Persona) -> ConnectionPool:
        pool = self._pools.get(persona.id)
        if pool is None:
            password = persona.password(self._settings)
            if password is None:
                raise RuntimeError(f"no DB password set for persona {persona.id}")
            pool = ConnectionPool(
                persona_url(self._database_url, persona.login, password.get_secret_value()),
                max_size=POOL_MAX_SIZE,
                open=True,
                **pool_options(),
            )
            self._pools[persona.id] = pool
        return pool

    @contextmanager
    def transaction(self, persona_id: str) -> Iterator[psycopg.Connection]:
        """A connection as `persona_id`'s login, inside a transaction that is always ended."""
        persona = PERSONAS[persona_id]
        with self._pool(persona).connection() as conn, conn.transaction():
            conn.execute(f"set local statement_timeout = '{STATEMENT_TIMEOUT}'")
            yield conn

    def close(self) -> None:
        for pool in self._pools.values():
            pool.close()
        self._pools.clear()
