"""
Dashboard Query Builder
Implements the three-layer query patterns from the system design.

Layer 1: Executive Grid (Client x Domain matrix)
Layer 2: Client View (Resident breakdown)
Layer 3: Resident Deep Dive (Event timeline)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, date


@dataclass
class GridCell:
    """Single cell in executive grid"""
    client_name: str
    domain_name: str
    primary_risk: str  # 'RED', 'AMBER', 'GREEN'
    doc_risk: str      # 'RED', 'AMBER', 'GREEN'
    red_count: int
    amber_count: int
    green_count: int


@dataclass
class ResidentSummary:
    """Resident row in client view"""
    resident_id: int
    resident_name: str
    overall_risk: str
    domain_risks: Dict[str, str]  # domain_name -> risk_level
    alert_summary: str


@dataclass
class EventRecord:
    """Single event in resident timeline"""
    event_timestamp: datetime
    assistance_level: str
    is_refusal: bool
    event_title: str
    event_description: Optional[str]
    staff_name: Optional[str]
    gap_hours: Optional[float]  # Gap to previous event


class DashboardQueries:
    """
    Query builder for dashboard layers
    
    Returns SQL templates with parameter placeholders.
    Actual execution depends on your database library (psycopg2, SQLAlchemy, etc.)
    """
    
    @staticmethod
    def layer1_executive_grid(start_date_id: int, end_date_id: int) -> str:
        """
        Layer 1: Executive Grid Query
        
        Returns client×domain matrix with risk levels.
        Uses pre-aggregated fact_resident_domain_score table.
        
        Args:
            start_date_id: Analysis start date (YYYYMMDD format)
            end_date_id: Analysis end date (YYYYMMDD format)
            
        Returns:
            SQL query string
        """
        return """
        WITH resident_scores AS (
            SELECT 
                c.client_id,
                c.client_name,
                d.domain_name,
                s.crs_level,
                s.dcs_level,
                CASE s.crs_level 
                    WHEN 'RED' THEN 3 
                    WHEN 'AMBER' THEN 2 
                    ELSE 1 
                END AS crs_rank,
                CASE s.dcs_level 
                    WHEN 'RED' THEN 3 
                    WHEN 'AMBER' THEN 2 
                    WHEN 'N/A' THEN 0
                    ELSE 1 
                END AS dcs_rank
            FROM fact_resident_domain_score s
            JOIN dim_resident r ON s.resident_id = r.resident_id
            JOIN dim_client c ON r.client_id = c.client_id
            JOIN dim_domain d ON s.domain_id = d.domain_id
            WHERE s.end_date_id = %(end_date_id)s
              AND s.start_date_id = %(start_date_id)s
              AND r.is_active = TRUE
              AND c.is_active = TRUE
        )
        SELECT 
            client_name,
            domain_name,
            -- Primary indicator: worst CRS in this client-domain
            CASE MAX(crs_rank)
                WHEN 3 THEN 'RED'
                WHEN 2 THEN 'AMBER'
                ELSE 'GREEN'
            END AS primary_risk,
            -- Documentation indicator: worst DCS
            CASE MAX(dcs_rank)
                WHEN 3 THEN 'RED'
                WHEN 2 THEN 'AMBER'
                WHEN 0 THEN 'N/A'
                ELSE 'GREEN'
            END AS doc_risk,
            -- Resident counts at each risk level
            COUNT(*) FILTER (WHERE crs_level = 'RED') AS red_count,
            COUNT(*) FILTER (WHERE crs_level = 'AMBER') AS amber_count,
            COUNT(*) FILTER (WHERE crs_level = 'GREEN') AS green_count
        FROM resident_scores
        GROUP BY client_name, domain_name
        ORDER BY client_name, domain_name;
        """
    
    @staticmethod
    def layer2_client_view(
        client_id: int,
        start_date_id: int,
        end_date_id: int,
        risk_filter: Optional[List[str]] = None
    ) -> str:
        """
        Layer 2: Client Resident Breakdown
        
        Shows all residents in a client with their risk levels and alerts.
        
        Args:
            client_id: Client ID to analyze
            start_date_id: Analysis start date
            end_date_id: Analysis end date
            risk_filter: Optional list of risk levels to filter (e.g., ['RED', 'AMBER'])
        """
        risk_condition = ""
        if risk_filter:
            risk_list = "', '".join(risk_filter)
            risk_condition = f"AND rwr.overall_risk IN ('{risk_list}')"
        
        return f"""
        WITH resident_worst_risk AS (
            SELECT 
                r.resident_id,
                r.resident_name,
                MAX(
                    CASE s.crs_level 
                        WHEN 'RED' THEN 3 
                        WHEN 'AMBER' THEN 2 
                        ELSE 1 
                    END
                ) AS worst_crs_rank,
                CASE 
                    WHEN MAX(CASE s.crs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END) = 3 THEN 'RED'
                    WHEN MAX(CASE s.crs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END) = 2 THEN 'AMBER'
                    ELSE 'GREEN'
                END AS overall_risk
            FROM dim_resident r
            JOIN fact_resident_domain_score s ON r.resident_id = s.resident_id
            WHERE r.client_id = %(client_id)s
              AND s.end_date_id = %(end_date_id)s
              AND s.start_date_id = %(start_date_id)s
              AND r.is_active = TRUE
            GROUP BY r.resident_id, r.resident_name
        )
        SELECT 
            rwr.resident_id,
            rwr.resident_name,
            rwr.overall_risk,
            -- Domain-specific scores (pivoted for common domains)
            MAX(CASE WHEN d.domain_name = 'Washing/Bathing' THEN s.crs_level END) AS washing_risk,
            MAX(CASE WHEN d.domain_name = 'Oral Care' THEN s.crs_level END) AS oral_care_risk,
            MAX(CASE WHEN d.domain_name = 'Dressing/Clothing' THEN s.crs_level END) AS dressing_risk,
            MAX(CASE WHEN d.domain_name = 'Toileting' THEN s.crs_level END) AS toileting_risk,
            MAX(CASE WHEN d.domain_name = 'Grooming' THEN s.crs_level END) AS grooming_risk,
            -- Alert summary: concatenate non-GREEN findings
            STRING_AGG(
                CASE 
                    WHEN s.crs_level IN ('RED', 'AMBER') THEN
                        d.domain_name || ': ' || 
                        CASE 
                            WHEN s.refusal_count > 0 THEN s.refusal_count::TEXT || ' refusals'
                            WHEN s.max_gap_hours IS NOT NULL THEN s.max_gap_hours::TEXT || 'h gap'
                            ELSE 'requires attention'
                        END
                    ELSE NULL
                END,
                '; '
            ) AS alert_summary
        FROM resident_worst_risk rwr
        JOIN fact_resident_domain_score s ON rwr.resident_id = s.resident_id
        JOIN dim_domain d ON s.domain_id = d.domain_id
        WHERE s.end_date_id = %(end_date_id)s
          AND s.start_date_id = %(start_date_id)s
          {risk_condition}
        GROUP BY rwr.resident_id, rwr.resident_name, rwr.overall_risk, rwr.worst_crs_rank
        ORDER BY rwr.worst_crs_rank DESC, rwr.resident_name;
        """
    
    @staticmethod
    def layer2_trend_data(client_id: int, days: int = 30) -> str:
        """
        Layer 2: Trend chart data (risk level counts over time)
        
        Shows how many residents were RED/AMBER/GREEN each day.
        Uses each resident's worst CRS across domains for that day.
        """
        return """
        WITH resident_daily_worst AS (
            SELECT 
                s.resident_id,
                dd.full_date,
                MAX(
                    CASE s.crs_level
                        WHEN 'RED' THEN 3
                        WHEN 'AMBER' THEN 2
                        ELSE 1
                    END
                ) AS worst_rank
            FROM fact_resident_domain_score s
            JOIN dim_resident r ON s.resident_id = r.resident_id
            JOIN dim_date dd ON s.end_date_id = dd.date_id
            WHERE r.client_id = %(client_id)s
              AND dd.full_date >= CURRENT_DATE - %(days)s
              AND r.is_active = TRUE
            GROUP BY s.resident_id, dd.full_date
        )
        SELECT 
            full_date,
            COUNT(*) FILTER (WHERE worst_rank = 3) AS red_count,
            COUNT(*) FILTER (WHERE worst_rank = 2) AS amber_count,
            COUNT(*) FILTER (WHERE worst_rank = 1) AS green_count
        FROM resident_daily_worst
        GROUP BY full_date
        ORDER BY full_date;
        """
    
    @staticmethod
    def layer3_resident_timeline(
        resident_id: int,
        domain_id: int,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> str:
        """
        Layer 3: Resident Event Timeline
        
        Shows all events for a resident in a specific domain with gap detection.
        """
        return """
        WITH events_with_gaps AS (
            SELECT 
                e.event_timestamp,
                e.assistance_level,
                e.is_refusal,
                e.event_title,
                e.event_description,
                s.staff_name,
                LAG(e.event_timestamp) OVER (ORDER BY e.event_timestamp DESC) AS prev_timestamp
            FROM fact_adl_event e
            LEFT JOIN dim_staff s ON e.staff_id = s.staff_id
            WHERE e.resident_id = %(resident_id)s
              AND e.domain_id = %(domain_id)s
              AND e.event_timestamp >= %(start_timestamp)s
              AND e.event_timestamp <= %(end_timestamp)s
            ORDER BY e.event_timestamp DESC
        )
        SELECT 
            event_timestamp,
            assistance_level,
            is_refusal,
            event_title,
            event_description,
            staff_name,
            CASE 
                WHEN prev_timestamp IS NOT NULL THEN
                    EXTRACT(EPOCH FROM (prev_timestamp - event_timestamp)) / 3600.0
                ELSE NULL
            END AS gap_hours
        FROM events_with_gaps
        ORDER BY event_timestamp DESC;
        """
    
    @staticmethod
    def layer3_score_breakdown(
        resident_id: int,
        domain_id: int,
        start_date_id: int,
        end_date_id: int
    ) -> str:
        """
        Layer 3: Get pre-calculated score breakdown
        
        Shows how the score was calculated.
        """
        return """
        SELECT 
            s.crs_level,
            s.crs_total,
            s.crs_refusal_score,
            s.crs_gap_score,
            s.crs_dependency_score,
            s.refusal_count,
            s.max_gap_hours,
            s.dependency_trend,
            s.dcs_level,
            s.dcs_percentage,
            s.actual_entries,
            s.expected_entries,
            d.gap_threshold_amber,
            d.gap_threshold_red,
            d.expected_per_day
        FROM fact_resident_domain_score s
        JOIN dim_domain d ON s.domain_id = d.domain_id
        WHERE s.resident_id = %(resident_id)s
          AND s.domain_id = %(domain_id)s
          AND s.start_date_id = %(start_date_id)s
          AND s.end_date_id = %(end_date_id)s;
        """
    
    @staticmethod
    def layer3_assistance_distribution(
        resident_id: int,
        domain_id: int,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> str:
        """
        Layer 3: Assistance level distribution
        """
        return """
        SELECT 
            assistance_level,
            COUNT(*) AS event_count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS percentage
        FROM fact_adl_event
        WHERE resident_id = %(resident_id)s
          AND domain_id = %(domain_id)s
          AND event_timestamp >= %(start_timestamp)s
          AND event_timestamp <= %(end_timestamp)s
        GROUP BY assistance_level
        ORDER BY 
            CASE assistance_level
                WHEN 'Independent' THEN 1
                WHEN 'Some Assistance' THEN 2
                WHEN 'Full Assistance' THEN 3
                WHEN 'Refused' THEN 4
                ELSE 5
            END;
        """
    
    @staticmethod
    def get_active_residents_by_client(client_id: int) -> str:
        """Get all active residents for a client"""
        return """
        SELECT 
            r.resident_id,
            r.resident_name,
            r.admission_date,
            r.care_level
        FROM dim_resident r
        WHERE r.client_id = %(client_id)s
          AND r.is_active = TRUE
        ORDER BY r.resident_name;
        """
    
    @staticmethod
    def get_all_active_clients() -> str:
        """Get all active clients"""
        return """
        SELECT 
            client_id,
            client_name,
            client_type
        FROM dim_client
        WHERE is_active = TRUE
        ORDER BY client_name;
        """
    
    @staticmethod
    def get_domains() -> str:
        """Get all configured ADL domains"""
        return """
        SELECT 
            domain_id,
            domain_name,
            expected_per_day,
            gap_threshold_amber,
            gap_threshold_red,
            cqc_alignment
        FROM dim_domain
        ORDER BY domain_name;
        """


class DateHelper:
    """Helper functions for date dimension operations"""
    
    @staticmethod
    def date_to_date_id(d: date) -> int:
        """Convert date to YYYYMMDD integer format"""
        return int(d.strftime('%Y%m%d'))
    
    @staticmethod
    def date_id_to_date(date_id: int) -> date:
        """Convert YYYYMMDD integer to date"""
        s = str(date_id)
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    
    @staticmethod
    def get_date_range(end_date: date, days: int) -> tuple:
        """
        Get start_date_id and end_date_id for N-day lookback
        
        Args:
            end_date: End of analysis period
            days: Number of days to look back
            
        Returns:
            (start_date_id, end_date_id) tuple
        """
        from datetime import timedelta
        start_date = end_date - timedelta(days=days-1)  # -1 because end_date is inclusive
        return (DateHelper.date_to_date_id(start_date), DateHelper.date_to_date_id(end_date))


# Example usage with psycopg2
def example_psycopg2_usage():
    """
    Example of how to use these queries with psycopg2
    
    This is illustrative - you'd need actual database connection.
    """
    import psycopg2
    from datetime import date, timedelta
    
    # (Pseudo-code - not runnable without actual DB)
    # conn = psycopg2.connect("dbname=care_analytics user=postgres")
    # cursor = conn.cursor()
    
    # Layer 1: Executive Grid
    end_date = date.today()
    start_date_id, end_date_id = DateHelper.get_date_range(end_date, days=7)
    
    query = DashboardQueries.layer1_executive_grid(start_date_id, end_date_id)
    # cursor.execute(query, {'start_date_id': start_date_id, 'end_date_id': end_date_id})
    # results = cursor.fetchall()
    
    # Layer 2: Client View
    client_id = 1
    query = DashboardQueries.layer2_client_view(client_id, start_date_id, end_date_id)
    # cursor.execute(query, {
    #     'client_id': client_id,
    #     'start_date_id': start_date_id,
    #     'end_date_id': end_date_id
    # })
    
    # Layer 3: Resident Timeline
    from datetime import datetime
    resident_id = 1
    domain_id = 2  # Oral Care
    start_ts = datetime.combine(end_date - timedelta(days=7), datetime.min.time())
    end_ts = datetime.combine(end_date, datetime.max.time())
    
    query = DashboardQueries.layer3_resident_timeline(
        resident_id, domain_id, start_ts, end_ts
    )
    # cursor.execute(query, {
    #     'resident_id': resident_id,
    #     'domain_id': domain_id,
    #     'start_timestamp': start_ts,
    #     'end_timestamp': end_ts
    # })


# Example usage with pandas (for testing)
def example_pandas_usage():
    """
    Example of how to use these queries with pandas.read_sql
    """
    import pandas as pd
    from datetime import date
    
    # (Pseudo-code)
    # from sqlalchemy import create_engine
    # engine = create_engine('postgresql://user:pass@localhost/care_analytics')
    
    # Get executive grid
    end_date = date.today()
    start_date_id, end_date_id = DateHelper.get_date_range(end_date, days=7)
    
    query = DashboardQueries.layer1_executive_grid(start_date_id, end_date_id)
    # df_grid = pd.read_sql(query, engine, params={
    #     'start_date_id': start_date_id,
    #     'end_date_id': end_date_id
    # })
    
    # Pivot for grid display
    # df_pivot = df_grid.pivot(
    #     index='client_name',
    #     columns='domain_name',
    #     values='primary_risk'
    # )
    
    return "See comments for usage pattern"


if __name__ == '__main__':
    # Print example query
    from datetime import date
    
    print("Example Query - Executive Grid")
    print("=" * 80)
    
    today = date.today()
    start_date_id, end_date_id = DateHelper.get_date_range(today, days=7)
    
    print(f"Analysis Period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}")
    print(f"Date IDs: {start_date_id} to {end_date_id}")
    print()
    
    query = DashboardQueries.layer1_executive_grid(start_date_id, end_date_id)
    print(query)
