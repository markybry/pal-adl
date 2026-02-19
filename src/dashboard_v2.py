import hashlib
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

import altair as alt
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

LAYER_1 = "Layer 1 - Executive Grid"
LAYER_2 = "Layer 2 - Client View"
LAYER_3 = "Layer 3 - Resident Deep Dive"
LAYER_OPTIONS = [LAYER_1, LAYER_2, LAYER_3]


def get_default_index(options, preferred_value):
    if preferred_value in options:
        return options.index(preferred_value)
    return 0


def initialize_navigation_state():
    st.session_state.setdefault("active_layer", LAYER_1)
    st.session_state.setdefault("active_layer_selector", LAYER_1)
    st.session_state.setdefault("pending_layer", None)
    st.session_state.setdefault("selected_client_id", None)
    st.session_state.setdefault("selected_client_name", None)
    st.session_state.setdefault("selected_resident_id", None)
    st.session_state.setdefault("selected_resident_name", None)
    st.session_state.setdefault("selected_domain_id", None)
    st.session_state.setdefault("selected_domain_name", None)


def open_layer2(client_id: int, client_name: str, domain_name: str | None = None):
    st.session_state["selected_client_id"] = int(client_id)
    st.session_state["selected_client_name"] = client_name
    if domain_name:
        st.session_state["selected_domain_name"] = domain_name
    st.session_state["active_layer"] = LAYER_2
    st.session_state["pending_layer"] = LAYER_2
    st.rerun()


def open_layer3(resident_id: int, resident_name: str, domain_name: str | None = None):
    st.session_state["selected_resident_id"] = int(resident_id)
    st.session_state["selected_resident_name"] = resident_name
    if domain_name:
        st.session_state["selected_domain_name"] = domain_name
    st.session_state["active_layer"] = LAYER_3
    st.session_state["pending_layer"] = LAYER_3
    st.rerun()


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

    st.download_button(
        "⬇️ Export Layer 1 CSV",
        data=df[["client_name", "domain_name", "primary_risk", "doc_risk", "red_count", "amber_count", "green_count"]].to_csv(index=False),
        file_name=f"layer1_executive_grid_{start_date_id}_{end_date_id}.csv",
        mime="text/csv",
        key="layer1_export_csv",
    )

    st.markdown("### Drill-down")
    client_lookup_df = pd.read_sql(
        """
        SELECT client_id, client_name
        FROM dim_client
        WHERE is_active = TRUE
        ORDER BY client_name
        """,
        conn,
    )
    domain_lookup_df = pd.read_sql(DashboardQueries.get_domains(), conn)

    available_clients = sorted(df["client_name"].dropna().unique().tolist())
    available_domains = sorted(df["domain_name"].dropna().unique().tolist())

    if available_clients and available_domains:
        preferred_client = st.session_state.get("selected_client_name")
        preferred_domain = st.session_state.get("selected_domain_name")
        pick_col1, pick_col2, pick_col3 = st.columns([2, 2, 1])
        with pick_col1:
            nav_client_name = st.selectbox(
                "Client",
                options=available_clients,
                index=get_default_index(available_clients, preferred_client),
                key="layer1_nav_client",
            )
        with pick_col2:
            nav_domain_name = st.selectbox(
                "Domain",
                options=available_domains,
                index=get_default_index(available_domains, preferred_domain),
                key="layer1_nav_domain",
            )
        with pick_col3:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Open Layer 2", key="layer1_open_layer2"):
                selected_client = client_lookup_df.loc[
                    client_lookup_df["client_name"] == nav_client_name,
                    ["client_id", "client_name"],
                ]
                if selected_client.empty:
                    st.error("Selected client was not found in database lookup.")
                else:
                    selected_row = selected_client.iloc[0]
                    open_layer2(int(selected_row["client_id"]), selected_row["client_name"], nav_domain_name)

    total_cells = len(df)
    red_count = int((df["primary_risk"] == "RED").sum())
    amber_count = int((df["primary_risk"] == "AMBER").sum())
    green_count = int((df["primary_risk"] == "GREEN").sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("🔴 RED", red_count, f"{(red_count / total_cells) * 100:.0f}%")
    col2.metric("🟡 AMBER", amber_count, f"{(amber_count / total_cells) * 100:.0f}%")
    col3.metric("🟢 GREEN", green_count, f"{(green_count / total_cells) * 100:.0f}%")


def render_layer2(conn, start_date_id: int, end_date_id: int):
    if st.button("← Back to Executive Grid", key="layer2_back_layer1"):
        st.session_state["active_layer"] = LAYER_1
        st.session_state["pending_layer"] = LAYER_1
        st.rerun()

    clients_df = get_scored_clients(conn, start_date_id, end_date_id)

    if clients_df.empty:
        st.warning(
            "No clients have scores for this period. "
            "Run scripts/calculate_scores.py for this end date and period first."
        )
        return

    client_options = clients_df.set_index("client_name")["client_id"].to_dict()
    client_names = list(client_options.keys())
    preferred_client_name = st.session_state.get("selected_client_name")
    selected_client_name = st.sidebar.selectbox(
        "Client",
        client_names,
        index=get_default_index(client_names, preferred_client_name),
        key="layer2_client",
    )
    selected_client_id = int(client_options[selected_client_name])

    st.session_state["selected_client_id"] = selected_client_id
    st.session_state["selected_client_name"] = selected_client_name

    risk_scope = st.sidebar.selectbox(
        "Risk filter",
        ["All", "AMBER+RED", "RED only"],
        index=0,
        key="layer2_risk_filter",
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

        st.download_button(
            "⬇️ Export Layer 2 Residents CSV",
            data=resident_df.to_csv(index=False),
            file_name=f"layer2_residents_client_{selected_client_id}_{start_date_id}_{end_date_id}.csv",
            mime="text/csv",
            key="layer2_export_residents_csv",
        )

        st.markdown("### Drill-down")
        resident_options = resident_df.set_index("resident_name")["resident_id"].to_dict()
        resident_names = list(resident_options.keys())
        preferred_resident_name = st.session_state.get("selected_resident_name")

        domains_df = pd.read_sql(DashboardQueries.get_domains(), conn)
        domain_names = domains_df["domain_name"].tolist()
        preferred_domain_name = st.session_state.get("selected_domain_name")

        nav_col1, nav_col2, nav_col3 = st.columns([2, 2, 1])
        with nav_col1:
            selected_resident_name = st.selectbox(
                "Resident",
                options=resident_names,
                index=get_default_index(resident_names, preferred_resident_name),
                key="layer2_nav_resident",
            )
        with nav_col2:
            selected_domain_name = st.selectbox(
                "Domain",
                options=domain_names,
                index=get_default_index(domain_names, preferred_domain_name),
                key="layer2_nav_domain",
            )
        with nav_col3:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Open Layer 3", key="layer2_open_layer3"):
                open_layer3(
                    int(resident_options[selected_resident_name]),
                    selected_resident_name,
                    selected_domain_name,
                )

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

    trend_long = trend_df.melt(
        id_vars=["full_date"],
        value_vars=["red_count", "amber_count", "green_count"],
        var_name="risk_level",
        value_name="resident_count",
    )
    trend_long["risk_level"] = trend_long["risk_level"].map(
        {
            "red_count": "RED",
            "amber_count": "AMBER",
            "green_count": "GREEN",
        }
    )

    trend_chart = (
        alt.Chart(trend_long)
        .mark_line(point=True)
        .encode(
            x=alt.X("full_date:T", title="Date"),
            y=alt.Y("resident_count:Q", title="Residents"),
            color=alt.Color(
                "risk_level:N",
                title="Risk",
                scale=alt.Scale(
                    domain=["RED", "AMBER", "GREEN"],
                    range=["#d32f2f", "#f9a825", "#2e7d32"],
                ),
            ),
            tooltip=["full_date:T", "risk_level:N", "resident_count:Q"],
        )
    )
    st.altair_chart(trend_chart, use_container_width=True)
    st.download_button(
        "⬇️ Export Trend CSV",
        data=trend_df.to_csv(index=False),
        file_name=f"layer2_trend_client_{selected_client_id}.csv",
        mime="text/csv",
        key="layer2_export_trend_csv",
    )


def render_layer3(conn, start_date_id: int, end_date_id: int):
    if st.button("← Back to Client View", key="layer3_back_layer2"):
        st.session_state["active_layer"] = LAYER_2
        st.session_state["pending_layer"] = LAYER_2
        st.rerun()

    clients_df = get_scored_clients(conn, start_date_id, end_date_id)
    if clients_df.empty:
        st.warning(
            "No clients have scores for this period. "
            "Run scripts/calculate_scores.py for this end date and period first."
        )
        return

    client_options = clients_df.set_index("client_name")["client_id"].to_dict()
    client_names = list(client_options.keys())
    preferred_client_name = st.session_state.get("selected_client_name")
    selected_client_name = st.sidebar.selectbox(
        "Client",
        client_names,
        index=get_default_index(client_names, preferred_client_name),
        key="layer3_client",
    )
    selected_client_id = int(client_options[selected_client_name])
    st.session_state["selected_client_id"] = selected_client_id
    st.session_state["selected_client_name"] = selected_client_name

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
    resident_names = list(resident_options.keys())
    preferred_resident_name = st.session_state.get("selected_resident_name")
    selected_resident_name = st.sidebar.selectbox(
        "Resident",
        resident_names,
        index=get_default_index(resident_names, preferred_resident_name),
        key="layer3_resident",
    )
    selected_resident_id = int(resident_options[selected_resident_name])
    st.session_state["selected_resident_id"] = selected_resident_id
    st.session_state["selected_resident_name"] = selected_resident_name

    domains_df = pd.read_sql(DashboardQueries.get_domains(), conn)
    domain_options = domains_df.set_index("domain_name")["domain_id"].to_dict()
    domain_names = list(domain_options.keys())
    preferred_domain_name = st.session_state.get("selected_domain_name")
    selected_domain_name = st.sidebar.selectbox(
        "Domain",
        domain_names,
        index=get_default_index(domain_names, preferred_domain_name),
        key="layer3_domain",
    )
    selected_domain_id = int(domain_options[selected_domain_name])
    st.session_state["selected_domain_id"] = selected_domain_id
    st.session_state["selected_domain_name"] = selected_domain_name

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

    st.download_button(
        "⬇️ Export Score Breakdown CSV",
        data=score_df.to_csv(index=False),
        file_name=(
            f"layer3_score_breakdown_resident_{selected_resident_id}_"
            f"domain_{selected_domain_id}_{start_date_id}_{end_date_id}.csv"
        ),
        mime="text/csv",
        key="layer3_export_score_csv",
    )

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
        st.download_button(
            "⬇️ Export Timeline CSV",
            data=timeline_df.to_csv(index=False),
            file_name=(
                f"layer3_timeline_resident_{selected_resident_id}_"
                f"domain_{selected_domain_id}_{start_date_id}_{end_date_id}.csv"
            ),
            mime="text/csv",
            key="layer3_export_timeline_csv",
        )

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

    assist_chart = (
        alt.Chart(assist_df)
        .mark_bar()
        .encode(
            x=alt.X("assistance_level:N", title="Assistance"),
            y=alt.Y("event_count:Q", title="Events"),
            tooltip=["assistance_level:N", "event_count:Q", "percentage:Q"],
        )
    )
    st.altair_chart(assist_chart, use_container_width=True)
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
    st.download_button(
        "⬇️ Export Assistance Distribution CSV",
        data=assist_df.to_csv(index=False),
        file_name=(
            f"layer3_assistance_resident_{selected_resident_id}_"
            f"domain_{selected_domain_id}_{start_date_id}_{end_date_id}.csv"
        ),
        mime="text/csv",
        key="layer3_export_assistance_csv",
    )


def main():
    st.set_page_config(page_title="Care Analytics Dashboard", page_icon="🏥", layout="wide")

    if not check_password():
        st.stop()

    st.title("🏥 Care Analytics Dashboard")
    initialize_navigation_state()

    if st.sidebar.button("🚪 Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.sidebar.header("Analysis Period")
    period_days = st.sidebar.selectbox("Lookback (days)", [7, 14, 30, 365], index=0)
    end_date = st.sidebar.date_input("End date", date.today())

    pending_layer = st.session_state.get("pending_layer")
    if pending_layer in LAYER_OPTIONS:
        st.session_state["active_layer"] = pending_layer
        st.session_state["active_layer_selector"] = pending_layer
        st.session_state["pending_layer"] = None

    layer = st.sidebar.selectbox(
        "Layer",
        LAYER_OPTIONS,
        index=get_default_index(LAYER_OPTIONS, st.session_state.get("active_layer", LAYER_1)),
        key="active_layer_selector",
    )
    st.session_state["active_layer"] = st.session_state.get("active_layer_selector", layer)

    start_date_id, end_date_id = DateHelper.get_date_range(end_date, period_days)

    conn = get_db_connection()
    st.caption(
        f"Analysis period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}"
    )

    if layer == LAYER_1:
        render_layer1(conn, start_date_id, end_date_id)
    elif layer == LAYER_2:
        render_layer2(conn, start_date_id, end_date_id)
    else:
        render_layer3(conn, start_date_id, end_date_id)


if __name__ == "__main__":
    main()
