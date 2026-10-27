import os

import psycopg
import pytest

from migrate import migrate, migration_files

EXPECTED_SCHEMAS = {
    "raw",
    "staging",
    "intermediate",
    "marts",
    "retrieval",
    "ops",
    "evals",
    "docflow",
}


def test_migration_files_are_numbered_and_ordered() -> None:
    names = [path.name for path in migration_files()]

    assert names, "no migrations found"
    assert names == sorted(names)
    assert names[0] == "0001_init.sql"


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs DATABASE_URL")
def test_migrate_creates_schemas_and_is_idempotent() -> None:
    database_url = os.environ["DATABASE_URL"]

    migrate(database_url)
    second_run = migrate(database_url)

    assert second_run == []
    with psycopg.connect(database_url) as conn:
        schemas = {
            row[0] for row in conn.execute("select schema_name from information_schema.schemata")
        }
        has_vector = conn.execute(
            "select exists (select 1 from pg_extension where extname = 'vector')"
        ).fetchone()
    assert schemas >= EXPECTED_SCHEMAS
    assert has_vector == (True,)
