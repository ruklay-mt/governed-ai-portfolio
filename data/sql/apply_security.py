"""Apply data/sql/security.sql in one transaction (ADR 0009). Run after every dbt build.

Usage: python data/sql/apply_security.py --target dev|prod
"""

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg

SECURITY_SQL = Path(__file__).parent / "security.sql"
TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}
ATTEMPTS = 3


def apply_security(database_url: str) -> None:
    # Right after a dbt build, autovacuum may be analysing the new tables while this script
    # alters them, and Postgres can resolve that by aborting us with a deadlock. The script is
    # one transaction, so nothing is half-applied and a retry is safe.
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with psycopg.connect(database_url) as conn, conn.transaction():
                conn.execute(SECURITY_SQL.read_bytes())
            return
        except psycopg.errors.DeadlockDetected:
            if attempt == ATTEMPTS:
                raise
            print(f"Deadlock applying security.sql, retrying ({attempt}/{ATTEMPTS})")
            time.sleep(2 * attempt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    args = parser.parse_args()

    env_var = TARGET_ENV_VARS[args.target]
    database_url = os.environ.get(env_var)
    if not database_url:
        print(f"{env_var} is not set (see .env.example)", file=sys.stderr)
        return 1
    apply_security(database_url.strip())
    print(f"Applied marts access policy to {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
