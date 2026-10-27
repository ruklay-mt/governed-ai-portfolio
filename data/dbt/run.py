"""Run dbt against Neon (or CI Postgres) using DATABASE_URL, without writing credentials to disk.

python data/dbt/run.py --target dev build
python data/dbt/run.py --target dev source freshness
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PROJECT_DIR = Path(__file__).parent
TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}


def dbt_env(database_url: str) -> dict[str, str]:
    url = urlparse(database_url.strip())
    query = parse_qs(url.query)
    return {
        "DBT_HOST": url.hostname or "localhost",
        "DBT_PORT": str(url.port or 5432),
        "DBT_USER": unquote(url.username or ""),
        "DBT_PASSWORD": unquote(url.password or ""),
        "DBT_DBNAME": url.path.lstrip("/"),
        "DBT_SSLMODE": query.get("sslmode", ["prefer"])[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    parser.add_argument("dbt_args", nargs=argparse.REMAINDER, help="arguments passed to dbt")
    args = parser.parse_args()

    env_var = TARGET_ENV_VARS[args.target]
    database_url = os.environ.get(env_var)
    if not database_url:
        print(f"{env_var} is not set (see .env.example)", file=sys.stderr)
        return 1

    env = {
        **os.environ,
        **dbt_env(database_url),
        "DBT_LOG_PATH": str(PROJECT_DIR / "logs"),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    command = [
        "dbt",
        *args.dbt_args,
        "--project-dir",
        str(PROJECT_DIR),
        "--profiles-dir",
        str(PROJECT_DIR),
    ]
    return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
