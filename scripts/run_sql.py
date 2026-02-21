"""
Run a SQL file against the configured PostgreSQL database.

Examples:
  python scripts/run_sql.py database/migrations/003_create_app_roles.sql
  ENV_FILE=.env.staging python scripts/run_sql.py database/schema.sql
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent

env_file = os.getenv("ENV_FILE")
if env_file:
    dotenv_path = Path(env_file)
    if not dotenv_path.is_absolute():
        dotenv_path = PROJECT_ROOT / dotenv_path
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    load_dotenv()


DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "care_analytics"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run a SQL file against PostgreSQL")
    parser.add_argument("sql_file", help="Path to SQL file")
    parser.add_argument("--password", "-p", help="Database password override")
    parser.add_argument("--user", help="Database user override")
    parser.add_argument("--dbname", help="Database name override")
    parser.add_argument("--host", help="Database host override")
    parser.add_argument("--port", type=int, help="Database port override")
    parser.add_argument("--sslmode", help="Database SSL mode override")
    return parser.parse_args()


def apply_cli_db_overrides(args):
    if args.password:
        DB_CONFIG["password"] = args.password
    if args.user:
        DB_CONFIG["user"] = args.user
    if args.dbname:
        DB_CONFIG["dbname"] = args.dbname
    if args.host:
        DB_CONFIG["host"] = args.host
    if args.port:
        DB_CONFIG["port"] = args.port
    if args.sslmode:
        DB_CONFIG["sslmode"] = args.sslmode


def main():
    args = parse_args()
    apply_cli_db_overrides(args)

    sql_path = Path(args.sql_file)
    if not sql_path.is_absolute():
        sql_path = PROJECT_ROOT / sql_path

    if not sql_path.exists():
        print(f"❌ SQL file not found: {sql_path}")
        sys.exit(1)

    sql_text = sql_path.read_text(encoding="utf-8")

    print("=" * 72)
    print("Care Analytics - SQL Runner")
    print("=" * 72)
    print(f"File: {sql_path}")
    print(
        f"Database: {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']} "
        f"({DB_CONFIG['user']}, sslmode={DB_CONFIG['sslmode']})"
    )

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql_text)
        conn.commit()
        print("✓ SQL executed successfully")
    except Exception as exc:
        conn.rollback()
        print(f"❌ SQL execution failed: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
