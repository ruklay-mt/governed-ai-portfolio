"""Database helpers."""

import psycopg

# Neon can take a few seconds to wake from scale-to-zero.
PING_TIMEOUT_SECONDS = 5


def ping(database_url: str) -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with psycopg.connect(database_url, connect_timeout=PING_TIMEOUT_SECONDS) as conn:
            conn.execute("select 1")
    except psycopg.Error:
        return False
    return True
