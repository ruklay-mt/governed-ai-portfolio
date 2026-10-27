"""Fixtures for database tests: the owner connection and one connection per persona login."""

import os
from collections.abc import Callable, Iterator
from urllib.parse import quote, urlparse, urlunparse

import psycopg
import pytest

from set_passwords import PERSONA_LOGINS

LOGINS = tuple(PERSONA_LOGINS)


def _persona_url(owner_url: str, login: str) -> str:
    url = urlparse(owner_url.strip())
    password = quote(os.environ[PERSONA_LOGINS[login]].strip(), safe="")
    host = url.hostname or "localhost"
    netloc = f"{login}:{password}@{host}" + (f":{url.port}" if url.port else "")
    return urlunparse(url._replace(netloc=netloc))


@pytest.fixture(scope="session")
def owner_url() -> str:
    if "DATABASE_URL" not in os.environ:
        pytest.skip("needs DATABASE_URL")
    return os.environ["DATABASE_URL"].strip()


@pytest.fixture(scope="session")
def marts_built(owner_url: str) -> None:
    with psycopg.connect(owner_url) as conn:
        row = conn.execute("select to_regclass('marts.fct_sales') is not null").fetchone()
    if not row or not row[0]:
        pytest.skip("marts not built (run make data-generate dbt-build)")


@pytest.fixture
def connect_as(owner_url: str, marts_built: None) -> Iterator[Callable[[str], psycopg.Connection]]:
    """Open an autocommit connection as a persona login, closed when the test ends.

    Per-test connections keep session state (e.g. a set_config spoof) from leaking between
    tests, and stay under each login's connection limit.
    """
    missing = [var for var in PERSONA_LOGINS.values() if not os.environ.get(var)]
    if missing:
        pytest.skip(f"needs persona passwords: {', '.join(missing)}")
    opened: list[psycopg.Connection] = []

    def connect(login: str) -> psycopg.Connection:
        conn = psycopg.connect(_persona_url(owner_url, login), autocommit=True)
        opened.append(conn)
        return conn

    yield connect
    for conn in opened:
        conn.close()
