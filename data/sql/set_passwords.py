"""Set the persona logins' passwords from environment variables (ADR 0008).

The password is hashed (SCRAM) on this machine and only the hash is sent to the server, so
plain text never reaches server logs. Values are never printed.

Usage: python data/sql/set_passwords.py --target dev|prod
"""

import argparse
import os
import sys

import psycopg
from psycopg import sql

TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}
PERSONA_LOGINS = {
    "agent_sales_rep_nz_south": "AGENT_DB_PASSWORD_SALES_REP_NZ_SOUTH",
    "agent_sales_manager": "AGENT_DB_PASSWORD_SALES_MANAGER",
    "agent_finance": "AGENT_DB_PASSWORD_FINANCE",
    "agent_support": "AGENT_DB_PASSWORD_SUPPORT",
}


def set_passwords(database_url: str, passwords: dict[str, str]) -> None:
    with psycopg.connect(database_url) as conn, conn.transaction():
        for login, password in passwords.items():
            hashed = conn.pgconn.encrypt_password(
                password.encode(), login.encode(), b"scram-sha-256"
            )
            conn.execute(
                sql.SQL("alter role {} password {}").format(
                    sql.Identifier(login), sql.Literal(hashed.decode())
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    args = parser.parse_args()

    database_url = os.environ.get(TARGET_ENV_VARS[args.target])
    missing = [var for var in PERSONA_LOGINS.values() if not os.environ.get(var)]
    if not database_url or missing:
        needed = ([TARGET_ENV_VARS[args.target]] if not database_url else []) + missing
        print(f"Not set: {', '.join(needed)} (see .env.example)", file=sys.stderr)
        return 1

    passwords = {login: os.environ[var].strip() for login, var in PERSONA_LOGINS.items()}
    set_passwords(database_url.strip(), passwords)
    print(f"Set passwords for {len(passwords)} persona logins on {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
