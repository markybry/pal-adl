"""
Backfill score snapshots across a date range.

This script reuses scripts/calculate_scores.py logic and runs score calculation
for each day in the selected range, writing 7/14/30-day snapshots (or custom periods).
"""

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys


# Ensure local imports work when running from project root or scripts folder
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_scores import (
    apply_cli_db_overrides,
    calculate_period_scores,
    connect_db,
    parse_periods,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill resident-domain scores across a date range"
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date in YYYY-MM-DD format (default: end-date - 29 days)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill ending at end-date (default: 30)",
    )
    parser.add_argument(
        "--periods",
        default="7,14,30",
        help="Comma-separated lookback periods in days (default: 7,14,30)",
    )
    parser.add_argument(
        "--client",
        default=None,
        help="Optional client name filter",
    )
    parser.add_argument("--password", "-p", help="Database password override")
    parser.add_argument("--user", help="Database user override")
    parser.add_argument("--dbname", help="Database name override")
    parser.add_argument("--host", help="Database host override")
    parser.add_argument("--port", type=int, help="Database port override")
    return parser.parse_args()


def resolve_date_range(args) -> tuple[date, date]:
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()

    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    else:
        if args.days <= 0:
            raise ValueError("--days must be a positive integer")
        start_date = end_date - timedelta(days=args.days - 1)

    if start_date > end_date:
        raise ValueError("start-date cannot be after end-date")

    return start_date, end_date


def iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def main():
    args = parse_args()
    apply_cli_db_overrides(args)

    periods = parse_periods(args.periods)
    start_date, end_date = resolve_date_range(args)
    total_days = (end_date - start_date).days + 1

    print("=" * 72)
    print("Care Analytics - Score Backfill")
    print("=" * 72)
    print(f"Date Range: {start_date.isoformat()} → {end_date.isoformat()} ({total_days} days)")
    print(f"Periods: {periods}")
    print(f"Client Filter: {args.client if args.client else 'All'}")

    total_written = 0
    total_processed = 0
    total_skipped = 0

    conn = connect_db()
    try:
        for index, snapshot_date in enumerate(iter_dates(start_date, end_date), start=1):
            print("-" * 72)
            print(f"[{index}/{total_days}] Snapshot date: {snapshot_date.isoformat()}")

            for period_days in periods:
                result = calculate_period_scores(conn, snapshot_date, period_days, args.client)
                total_written += result["written"]
                total_processed += result["processed"]
                total_skipped += result["skipped"]
                print(
                    f"  {period_days:>2}d -> written {result['written']}, "
                    f"processed {result['processed']}, skipped {result['skipped']}"
                )
    finally:
        conn.close()

    print("=" * 72)
    print("Backfill Complete")
    print("=" * 72)
    print(f"Total snapshots processed: {total_days}")
    print(f"Total rows processed:      {total_processed}")
    print(f"Total rows written:        {total_written}")
    print(f"Total rows skipped:        {total_skipped}")


if __name__ == "__main__":
    main()
