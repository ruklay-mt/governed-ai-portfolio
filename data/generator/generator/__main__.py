"""Generate Harbourline's synthetic source data into the `raw` schema.

python -m generator                     full rebuild as of today (Neon dev)
python -m generator --append            add today's data (idempotent)
python -m generator --append 2026-10-28 add a given day's data
python -m generator --scale small       about 1/10 of the volume, for CI and tests
"""

import argparse
import os
import sys
import time
from datetime import date

import psycopg

from generator.build import build
from generator.load import full_load, row_counts, upsert

TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}
DEFAULT_SEED = 20231101


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    parser.add_argument("--scale", choices=("full", "small"), default="full")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--append",
        nargs="?",
        const="today",
        metavar="DATE",
        help="upsert data as of DATE (default today) instead of a full rebuild",
    )
    args = parser.parse_args()

    env_var = TARGET_ENV_VARS[args.target]
    database_url = os.environ.get(env_var)
    if not database_url:
        print(f"{env_var} is not set (see .env.example)", file=sys.stderr)
        return 1
    database_url = database_url.strip()

    as_of = date.today() if args.append in (None, "today") else date.fromisoformat(args.append)
    started = time.monotonic()
    data = build(args.seed, args.scale, as_of)
    built = time.monotonic()

    with psycopg.connect(database_url) as conn:
        if args.append is None:
            full_load(conn, data)
            print(f"Full load to {args.target} ({args.scale}) as of {as_of}")
        else:
            written = upsert(conn, data)
            changed = {table: n for table, n in written.items() if n}
            print(
                f"Append to {args.target} ({args.scale}) as of {as_of}: {changed or 'no changes'}"
            )
        counts = row_counts(conn)
    print(f"Generated in {built - started:.1f}s, loaded in {time.monotonic() - built:.1f}s")
    for table, count in counts.items():
        print(f"  raw.{table:<24} {count:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
