import hashlib
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# Ensure project root is on Python path when launched via streamlit run src/dashboard_v2.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard_queries import DashboardQueries, DateHelper

load_dotenv()


def check_password() -> bool:
    def password_entered():
        correct_password_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
        if "password_hash" in st.secrets:
            correct_password_hash = st.secrets["password_hash"]

        entered_hash = hashlib.sha256(st.session_state["password"].encode()).hexdigest()
        st.session_state["password_correct"] = entered_hash == correct_password_hash
        del st.session_state["password"]

    if st.session_state.get("password_correct", False):
        return True

    st.markdown("## 🔐 Care Analytics Executive Dashboard Login")
    st.text_input("Password", type="password", on_change=password_entered, key="password")

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")

    st.caption("Default password: admin123 (change this in production)")
    return False


@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "care_analytics"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
    )


def risk_badge(risk: str) -> str:
    if risk == "RED":
        return "🔴 RED"
    if risk == "AMBER":
        return "🟡 AMBER"
    if risk == "GREEN":
        return "🟢 GREEN"
    return "⚪ N/A"


def cell_display(primary: str, doc: str) -> str:
    base = risk_badge(primary)
    if doc not in (None, "", "N/A") and doc != primary:
        return f"{base} (📄 {risk_badge(doc)})"
    return base


def color_row(series: pd.Series):
    value = str(series.iloc[0])
    if value.startswith("🔴"):
        return ["background-color: #ffebee; color: #b71c1c"]
    if value.startswith("🟡"):
        return ["background-color: #fff8e1; color: #e65100"]
    if value.startswith("🟢"):
        return ["background-color: #e8f5e9; color: #1b5e20"]
    return [""]


def get_scored_clients(conn, start_date_id: int, end_date_id: int) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT DISTINCT
            c.client_id,
            c.client_name
        FROM fact_resident_domain_score s
        JOIN dim_resident r ON s.resident_id = r.resident_id
        JOIN dim_client c ON r.client_id = c.client_id
        WHERE s.start_date_id = %(start_date_id)s
          AND s.end_date_id = %(end_date_id)s
          AND r.is_active = TRUE
          AND c.is_active = TRUE
        ORDER BY c.client_name
        """,
        conn,
        params={"start_date_id": start_date_id, "end_date_id": end_date_id},
    )


def risk_rank(risk: str) -> int:
    if risk == "RED":
        return 3
    if risk == "AMBER":
        return 2
    if risk == "GREEN":
        return 1
    return 0


def overall_risk(crs_level: str, dcs_level: str) -> str:
    return crs_level if risk_rank(crs_level) >= risk_rank(dcs_level) else dcs_level


def render_layer1(conn, start_date_id: int, end_date_id: int):
    query = DashboardQueries.layer1_executive_grid(start_date_id, end_date_id)
    df = pd.read_sql(
        query,
        conn,
        params={"start_date_id": start_date_id, "end_date_id": end_date_id},
    )

    if df.empty:
        st.warning("No pre-calculated scores found for this period. Run scripts/calculate_scores.py first.")
        return

    df["display"] = df.apply(lambda row: cell_display(row["primary_risk"], row["doc_risk"]), axis=1)

    pivot = (
        df.pivot(index="client_name", columns="domain_name", values="display")
        .sort_index()
        .fillna("⚪ N/A")
    )

    styled = pivot.style.applymap(lambda _: "")
    for column in pivot.columns:
        styled = styled.apply(color_row, subset=[column], axis=1)

    st.dataframe(styled, use_container_width=True)

    total_cells = len(df)
    red_count = int((df["primary_risk"] == "RED").sum())
    amber_count = int((df["primary_risk"] == "AMBER").sum())
    green_count = int((df["primary_risk"] == "GREEN").sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("🔴 RED", red_count, f"{(red_count / total_cells) * 100:.0f}%")
    col2.metric("🟡 AMBER", amber_count, f"{(amber_count / total_cells) * 100:.0f}%")
    col3.metric("🟢 GREEN", green_count, f"{(green_count / total_cells) * 100:.0f}%")


def render_layer2(conn, start_date_id: int, end_date_id: int):
    clients_df = get_scored_clients(conn, start_date_id, end_date_id)

    if clients_df.empty:
        st.warning(
            "No clients have scores for this period. "
            "Run scripts/calculate_scores.py for this end date and period first."
        )
        return

    client_options = clients_df.set_index("client_name")["client_id"].to_dict()
    selected_client_name = st.sidebar.selectbox("Client", list(client_options.keys()))
    selected_client_id = int(client_options[selected_client_name])

    risk_scope = st.sidebar.selectbox(
        "Risk filter",
        ["All", "AMBER+RED", "RED only"],
        index=0,
    )

    if risk_scope == "RED only":
        risk_filter = ["RED"]
    elif risk_scope == "AMBER+RED":
        risk_filter = ["AMBER", "RED"]
    else:
        risk_filter = None

    st.subheader(f"Client View: {selected_client_name}")

    resident_query = DashboardQueries.layer2_client_view(
        selected_client_id,
        start_date_id,
        end_date_id,
        risk_filter=risk_filter,
    )

    resident_df = pd.read_sql(
        resident_query,
        conn,
        params={
            "client_id": selected_client_id,
            "start_date_id": start_date_id,
            "end_date_id": end_date_id,
        },
    )

    if resident_df.empty:
        if risk_filter is not None:
            unfiltered_query = DashboardQueries.layer2_client_view(
                selected_client_id,
                start_date_id,
                end_date_id,
                risk_filter=None,
            )
            unfiltered_df = pd.read_sql(
                unfiltered_query,
                conn,
                params={
                    "client_id": selected_client_id,
                    "start_date_id": start_date_id,
                    "end_date_id": end_date_id,
                },
            )
            if not unfiltered_df.empty:
                st.info("No residents match the current risk filter. Try setting filter to 'All'.")
            else:
                st.info("No resident scores found for this client and period.")
        else:
            st.info("No resident scores found for this client and period.")
    else:
        risk_counts = resident_df["overall_risk"].value_counts()
        col1, col2, col3 = st.columns(3)
        col1.metric("🔴 RED Residents", int(risk_counts.get("RED", 0)))
        col2.metric("🟡 AMBER Residents", int(risk_counts.get("AMBER", 0)))
        col3.metric("🟢 GREEN Residents", int(risk_counts.get("GREEN", 0)))

        display_cols = [
            "resident_name",
            "overall_risk",
            "washing_risk",
            "oral_care_risk",
            "dressing_risk",
            "toileting_risk",
            "grooming_risk",
            "alert_summary",
        ]

        display_df = resident_df[display_cols].rename(
            columns={
                "resident_name": "Resident",
                "overall_risk": "Overall",
                "washing_risk": "Washing",
                "oral_care_risk": "Oral Care",
                "dressing_risk": "Dressing",
                "toileting_risk": "Toileting",
                "grooming_risk": "Grooming",
                "alert_summary": "Alerts",
            }
        )

        for column in ["Overall", "Washing", "Oral Care", "Dressing", "Toileting", "Grooming"]:
            display_df[column] = display_df[column].map(risk_badge)

        st.dataframe(display_df, use_container_width=True)

    st.markdown("### 30-Day Risk Trend")
    trend_query = DashboardQueries.layer2_trend_data(selected_client_id, days=30)
    trend_df = pd.read_sql(
        trend_query,
        conn,
        params={"client_id": selected_client_id, "days": 30},
    )

    if trend_df.empty:
        st.info("No trend data available.")
        return

    trend_plot = trend_df.set_index("full_date")[["red_count", "amber_count", "green_count"]]
    st.line_chart(trend_plot)


def render_layer3(conn, start_date_id: int, end_date_id: int):
    clients_df = get_scored_clients(conn, start_date_id, end_date_id)
    if clients_df.empty:
        st.warning(
            "No clients have scores for this period. "
            "Run scripts/calculate_scores.py for this end date and period first."
        )
        return

    client_options = clients_df.set_index("client_name")["client_id"].to_dict()
    selected_client_name = st.sidebar.selectbox("Client", list(client_options.keys()), key="layer3_client")
    selected_client_id = int(client_options[selected_client_name])

    residents_df = pd.read_sql(
        """
        SELECT DISTINCT
            r.resident_id,
            r.resident_name
        FROM fact_resident_domain_score s
        JOIN dim_resident r ON s.resident_id = r.resident_id
        WHERE r.client_id = %(client_id)s
          AND r.is_active = TRUE
          AND s.start_date_id = %(start_date_id)s
          AND s.end_date_id = %(end_date_id)s
        ORDER BY r.resident_name
        """,
        conn,
        params={
            "client_id": selected_client_id,
            "start_date_id": start_date_id,
            "end_date_id": end_date_id,
        },
    )

    if residents_df.empty:
        st.info("No resident scores found for this client and period.")
        return

    resident_options = residents_df.set_index("resident_name")["resident_id"].to_dict()
    selected_resident_name = st.sidebar.selectbox(
        "Resident",
        list(resident_options.keys()),
        key="layer3_resident",
    )
    selected_resident_id = int(resident_options[selected_resident_name])

    domains_df = pd.read_sql(DashboardQueries.get_domains(), conn)
    domain_options = domains_df.set_index("domain_name")["domain_id"].to_dict()
    selected_domain_name = st.sidebar.selectbox(
        "Domain",
        list(domain_options.keys()),
        key="layer3_domain",
    )
    selected_domain_id = int(domain_options[selected_domain_name])

    st.subheader(
        f"Resident Deep Dive: {selected_resident_name} · {selected_domain_name} ({selected_client_name})"
    )

    score_query = DashboardQueries.layer3_score_breakdown(
        selected_resident_id,
        selected_domain_id,
        start_date_id,
        end_date_id,
    )
    score_df = pd.read_sql(
        score_query,
        conn,
        params={
            "resident_id": selected_resident_id,
            "domain_id": selected_domain_id,
            "start_date_id": start_date_id,
            "end_date_id": end_date_id,
        },
    )

    if score_df.empty:
        st.info("No score breakdown found for this resident/domain in the selected period.")
        return

    score = score_df.iloc[0]
    combined_risk = overall_risk(score["crs_level"], score["dcs_level"])

    top1, top2, top3 = st.columns(3)
    top1.metric("Overall", risk_badge(combined_risk))
    top2.metric("Care Risk (CRS)", f"{risk_badge(score['crs_level'])} · {int(score['crs_total'])} pts")
    top3.metric("Documentation (DCS)", f"{risk_badge(score['dcs_level'])} · {float(score['dcs_percentage']):.0f}%")

    st.markdown("### Score Breakdown")
    detail1, detail2 = st.columns(2)
    with detail1:
        st.write(f"Refusal score: {int(score['crs_refusal_score'])} points")
        st.write(f"Gap score: {int(score['crs_gap_score'])} points")
        st.write(f"Dependency score: {int(score['crs_dependency_score'])} points")
        st.write(f"Refusal count: {int(score['refusal_count']) if pd.notna(score['refusal_count']) else 0}")
        st.write(f"Max gap hours: {float(score['max_gap_hours']):.1f}" if pd.notna(score['max_gap_hours']) else "Max gap hours: N/A")
    with detail2:
        st.write(f"Actual entries: {int(score['actual_entries']) if pd.notna(score['actual_entries']) else 0}")
        st.write(f"Expected entries: {float(score['expected_entries']):.1f}" if pd.notna(score['expected_entries']) else "Expected entries: N/A")
        st.write(
            f"Domain thresholds: amber {int(score['gap_threshold_amber'])}h, red {int(score['gap_threshold_red'])}h"
        )
        st.write(
            f"Expected/day: {float(score['expected_per_day']):.1f}" if pd.notna(score['expected_per_day']) else "Expected/day: N/A"
        )

    start_date = DateHelper.date_id_to_date(start_date_id)
    end_date = DateHelper.date_id_to_date(end_date_id)
    start_ts = datetime.combine(start_date, time.min)
    end_ts = datetime.combine(end_date, time.max)

    st.markdown("### Event Timeline")
    timeline_query = DashboardQueries.layer3_resident_timeline(
        selected_resident_id,
        selected_domain_id,
        start_ts,
        end_ts,
    )
    timeline_df = pd.read_sql(
        timeline_query,
        conn,
        params={
            "resident_id": selected_resident_id,
            "domain_id": selected_domain_id,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
        },
    )

    if timeline_df.empty:
        st.info("No events found for this resident/domain in the selected period.")
    else:
        timeline_df = timeline_df.rename(
            columns={
                "event_timestamp": "Event Time",
                "assistance_level": "Assistance",
                "is_refusal": "Refusal",
                "event_title": "Title",
                "event_description": "Description",
                "staff_name": "Staff",
                "gap_hours": "Gap (hours)",
            }
        )
        if "Gap (hours)" in timeline_df.columns:
            timeline_df["Gap (hours)"] = timeline_df["Gap (hours)"].apply(
                lambda val: round(float(val), 1) if pd.notna(val) else None
            )
        st.dataframe(timeline_df, use_container_width=True)

    st.markdown("### Assistance Distribution")
    assist_query = DashboardQueries.layer3_assistance_distribution(
        selected_resident_id,
        selected_domain_id,
        start_ts,
        end_ts,
    )
    assist_df = pd.read_sql(
        assist_query,
        conn,
        params={
            "resident_id": selected_resident_id,
            "domain_id": selected_domain_id,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
        },
    )

    if assist_df.empty:
        st.info("No assistance distribution data available.")
        return

    chart_df = assist_df.set_index("assistance_level")["event_count"]
    st.bar_chart(chart_df)
    st.dataframe(
        assist_df.rename(
            columns={
                "assistance_level": "Assistance",
                "event_count": "Events",
                "percentage": "Percent",
            }
        ),
        use_container_width=True,
    )


def main():
    st.set_page_config(page_title="Care Analytics Dashboard", page_icon="🏥", layout="wide")

    if not check_password():
        st.stop()

    st.title("🏥 Care Analytics Dashboard")

    if st.sidebar.button("🚪 Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.sidebar.header("Analysis Period")
    period_days = st.sidebar.selectbox("Lookback (days)", [7, 14, 30], index=0)
    end_date = st.sidebar.date_input("End date", date.today())
    layer = st.sidebar.selectbox(
        "Layer",
        [
            "Layer 1 - Executive Grid",
            "Layer 2 - Client View",
            "Layer 3 - Resident Deep Dive",
        ],
        index=0,
    )

    start_date_id, end_date_id = DateHelper.get_date_range(end_date, period_days)

    conn = get_db_connection()
    st.caption(
        f"Analysis period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}"
    )

    if layer.startswith("Layer 1"):
        render_layer1(conn, start_date_id, end_date_id)
    elif layer.startswith("Layer 2"):
        render_layer2(conn, start_date_id, end_date_id)
    else:
        render_layer3(conn, start_date_id, end_date_id)


if __name__ == "__main__":
    main()
