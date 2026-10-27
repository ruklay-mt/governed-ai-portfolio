"""Apply numbered SQL migrations from `migrations/` in order (ADR 0007).

Each file runs in its own transaction and is recorded in `public.schema_migrations`,
so running this twice applies nothing the second time.

Usage: python data/sql/migrate.py --target dev|prod
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}
# Arbitrary constant so two runs against the same database never interleave.
ADVISORY_LOCK_ID = 7_071_001


def migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def migrate(database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations and return the versions that were applied."""
    applied_now: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("select pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        try:
            conn.execute(
                "create table if not exists public.schema_migrations ("
                " version text primary key,"
                " applied_at timestamptz not null default now())"
            )
            already_applied = {
                row[0] for row in conn.execute("select version from public.schema_migrations")
            }
            for path in migration_files(migrations_dir):
                version = path.stem
                if version in already_applied:
                    continue
                with conn.transaction():
                    conn.execute(path.read_bytes())
                    conn.execute(
                        "insert into public.schema_migrations (version) values (%s)", (version,)
                    )
                applied_now.append(version)
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
    return applied_now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    args = parser.parse_args()

    env_var = TARGET_ENV_VARS[args.target]
    database_url = os.environ.get(env_var)
    if not database_url:
        print(f"{env_var} is not set (see .env.example)", file=sys.stderr)
        return 1

    applied = migrate(database_url)
    if applied:
        print(f"Applied to {args.target}: {', '.join(applied)}")
    else:
        print(f"{args.target} is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
