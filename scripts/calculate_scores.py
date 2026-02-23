"""
Batch score calculation for care analytics star schema.

Populates fact_resident_domain_score for selected lookback windows.
"""

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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

sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard_queries import DateHelper
from src.scoring_engine import ADLEvent, AssistanceLevel, ScoringEngine, is_refusal


DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "care_analytics"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


def parse_periods(raw: str) -> List[int]:
    periods = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value <= 0:
            raise ValueError("All period values must be positive integers")
        periods.append(value)

    if not periods:
        raise ValueError("At least one period is required")

    return sorted(set(periods))


def connect_db():
    return psycopg2.connect(**DB_CONFIG)


def get_active_residents(cursor, client_name: Optional[str] = None) -> List[Tuple[int, str]]:
    if client_name:
        cursor.execute(
            """
            SELECT r.resident_id, r.resident_name
            FROM dim_resident r
            JOIN dim_client c ON r.client_id = c.client_id
            WHERE r.is_active = TRUE
              AND c.is_active = TRUE
              AND c.client_name = %s
            ORDER BY r.resident_name
            """,
            (client_name,),
        )
    else:
        cursor.execute(
            """
            SELECT r.resident_id, r.resident_name
            FROM dim_resident r
            JOIN dim_client c ON r.client_id = c.client_id
            WHERE r.is_active = TRUE
              AND c.is_active = TRUE
            ORDER BY r.resident_name
            """
        )

    return cursor.fetchall()


def get_domains(cursor) -> List[Tuple[int, str]]:
    cursor.execute(
        """
        SELECT domain_id, domain_name
        FROM dim_domain
        ORDER BY domain_name
        """
    )
    return cursor.fetchall()


def build_event_window(end_date: date, period_days: int) -> Tuple[datetime, datetime, int, int]:
    start_date = end_date - timedelta(days=period_days - 1)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt, DateHelper.date_to_date_id(start_date), DateHelper.date_to_date_id(end_date)


def fetch_events(cursor, resident_id: int, domain_id: int, start_dt: datetime, end_dt: datetime):
    cursor.execute(
        """
        SELECT
            event_timestamp,
            logged_timestamp,
            assistance_level,
            is_refusal,
            event_title,
            event_description
        FROM fact_adl_event
        WHERE resident_id = %s
          AND domain_id = %s
          AND event_timestamp >= %s
          AND event_timestamp <= %s
        ORDER BY event_timestamp ASC
        """,
        (resident_id, domain_id, start_dt, end_dt),
    )
    return cursor.fetchall()


def to_adl_events(rows) -> List[ADLEvent]:
    events: List[ADLEvent] = []
    for row in rows:
        description = row[5]
        title = row[4]
        has_text_context = bool((description and str(description).strip()) or (title and str(title).strip()))
        effective_refusal = is_refusal(description, title) if has_text_context else bool(row[3])

        assistance_value = row[2] if row[2] else AssistanceLevel.NOT_SPECIFIED.value
        try:
            assistance_level = AssistanceLevel(assistance_value)
        except ValueError:
            assistance_level = AssistanceLevel.NOT_SPECIFIED

        events.append(
            ADLEvent(
                event_timestamp=row[0],
                logged_timestamp=row[1],
                assistance_level=assistance_level,
                is_refusal=effective_refusal,
                event_title=title,
                event_description=description,
            )
        )
    return events


def upsert_score(
    cursor,
    resident_id: int,
    domain_id: int,
    start_date_id: int,
    end_date_id: int,
    analysis,
):
    cursor.execute(
        """
        INSERT INTO fact_resident_domain_score (
            resident_id,
            domain_id,
            start_date_id,
            end_date_id,
            crs_level,
            crs_total,
            crs_refusal_score,
            crs_gap_score,
            crs_dependency_score,
            refusal_count,
            max_gap_hours,
            dependency_trend,
            dcs_level,
            dcs_percentage,
            actual_entries,
            expected_entries
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (resident_id, domain_id, start_date_id, end_date_id)
        DO UPDATE SET
            crs_level = EXCLUDED.crs_level,
            crs_total = EXCLUDED.crs_total,
            crs_refusal_score = EXCLUDED.crs_refusal_score,
            crs_gap_score = EXCLUDED.crs_gap_score,
            crs_dependency_score = EXCLUDED.crs_dependency_score,
            refusal_count = EXCLUDED.refusal_count,
            max_gap_hours = EXCLUDED.max_gap_hours,
            dependency_trend = EXCLUDED.dependency_trend,
            dcs_level = EXCLUDED.dcs_level,
            dcs_percentage = EXCLUDED.dcs_percentage,
            actual_entries = EXCLUDED.actual_entries,
            expected_entries = EXCLUDED.expected_entries,
            calculated_at = NOW()
        """,
        (
            resident_id,
            domain_id,
            start_date_id,
            end_date_id,
            analysis.care_risk_score.risk_level.value,
            analysis.care_risk_score.total_points,
            analysis.care_risk_score.components[0].points,
            analysis.care_risk_score.components[1].points,
            analysis.care_risk_score.components[2].points,
            analysis.refusal_count,
            analysis.max_gap_hours,
            None,
            analysis.documentation_score.risk_level.value,
            round(analysis.documentation_score.compliance_percentage, 2),
            analysis.total_events,
            round(analysis.documentation_score.expected_entries, 2),
        ),
    )


def calculate_period_scores(conn, end_date: date, period_days: int, client_name: Optional[str] = None) -> Dict[str, int]:
    cursor = conn.cursor()
    residents = get_active_residents(cursor, client_name)
    domains = get_domains(cursor)
    start_dt, end_dt, start_date_id, end_date_id = build_event_window(end_date, period_days)

    combinations_processed = 0
    scores_written = 0
    combinations_skipped = 0

    for resident_id, resident_name in residents:
        for domain_id, domain_name in domains:
            combinations_processed += 1
            rows = fetch_events(cursor, resident_id, domain_id, start_dt, end_dt)
            if not rows:
                combinations_skipped += 1
                continue

            events = to_adl_events(rows)
            analysis = ScoringEngine.analyze_resident_domain(
                resident_id=str(resident_id),
                domain_name=domain_name,
                events=events,
                period_days=period_days,
            )
            upsert_score(cursor, resident_id, domain_id, start_date_id, end_date_id, analysis)
            scores_written += 1

    conn.commit()
    cursor.close()

    return {
        "period_days": period_days,
        "start_date_id": start_date_id,
        "end_date_id": end_date_id,
        "residents": len(residents),
        "domains": len(domains),
        "processed": combinations_processed,
        "written": scores_written,
        "skipped": combinations_skipped,
    }


def print_summary(results: List[Dict[str, int]], end_date: date, client_name: Optional[str]):
    print("\n" + "=" * 72)
    print("Score Calculation Complete")
    print("=" * 72)
    print(f"End Date: {end_date.isoformat()}")
    print(f"Client Scope: {client_name if client_name else 'All active clients'}")

    for result in results:
        print("-" * 72)
        print(f"Period: {result['period_days']} days ({result['start_date_id']} → {result['end_date_id']})")
        print(f"Residents: {result['residents']} | Domains: {result['domains']}")
        print(f"Processed combinations: {result['processed']}")
        print(f"Scores written:         {result['written']}")
        print(f"Combinations skipped:   {result['skipped']}")

    print("=" * 72)


def parse_args():
    parser = argparse.ArgumentParser(description="Calculate and store resident-domain scores")
    parser.add_argument(
        "--periods",
        default="7,14,30",
        help="Comma-separated lookback periods in days (default: 7,14,30)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date in YYYY-MM-DD format (default: today)",
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

    periods = parse_periods(args.periods)
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()

    print("=" * 72)
    print("Care Analytics - Score Calculation")
    print("=" * 72)
    print(f"Database: {DB_CONFIG['dbname']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']} ({DB_CONFIG['user']})")
    print(f"Periods: {periods}")
    print(f"End Date: {end_date.isoformat()}")
    print(f"Client Filter: {args.client if args.client else 'All'}")

    conn = connect_db()
    try:
        results = []
        for period_days in periods:
            print(f"\nCalculating {period_days}-day scores...")
            result = calculate_period_scores(conn, end_date, period_days, args.client)
            results.append(result)
            print(
                f"  ✓ Written {result['written']} scores "
                f"(processed {result['processed']}, skipped {result['skipped']})"
            )
    finally:
        conn.close()

    print_summary(results, end_date, args.client)


if __name__ == "__main__":
    main()
