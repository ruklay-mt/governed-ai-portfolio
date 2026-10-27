"""Record a pipeline run in ops.pipeline_runs, with dbt's pass/fail counts.

Usage: python data/sql/record_run.py --target dev --status success|failure [--run-url URL]
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg

RUN_RESULTS = Path(__file__).parents[1] / "dbt" / "target" / "run_results.json"
TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}


def dbt_counts() -> tuple[int | None, int | None]:
    if not RUN_RESULTS.exists():
        return None, None
    results = json.loads(RUN_RESULTS.read_text())["results"]
    passed = sum(1 for r in results if r["status"] in ("pass", "success"))
    failed = sum(1 for r in results if r["status"] in ("fail", "error"))
    return passed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    parser.add_argument("--status", choices=("success", "failure"), required=True)
    parser.add_argument("--run-url")
    args = parser.parse_args()

    database_url = os.environ.get(TARGET_ENV_VARS[args.target])
    if not database_url:
        print(f"{TARGET_ENV_VARS[args.target]} is not set", file=sys.stderr)
        return 1
    passed, failed = dbt_counts()
    with psycopg.connect(database_url.strip()) as conn:
        conn.execute(
            "insert into ops.pipeline_runs"
            " (target_branch, as_of, status, dbt_passed, dbt_failed, run_url)"
            " values (%s, %s, %s, %s, %s, %s)",
            (args.target, date.today(), args.status, passed, failed, args.run_url),
        )
    print(f"Recorded {args.status} run for {args.target} (dbt passed={passed}, failed={failed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
