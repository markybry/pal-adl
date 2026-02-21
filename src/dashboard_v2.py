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

def load_environment():
    env_file = os.getenv("ENV_FILE")
    if env_file:
        dotenv_path = Path(env_file)
        if not dotenv_path.is_absolute():
            dotenv_path = PROJECT_ROOT / dotenv_path
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=True)
    else:
        dotenv_path = PROJECT_ROOT / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)


load_environment()

LAYER_1 = "Layer 1 - Executive Grid"
LAYER_2 = "Layer 2 - Client View"
LAYER_3 = "Layer 3 - Resident Deep Dive"
LAYER_OPTIONS = [LAYER_1, LAYER_2, LAYER_3]


def config_value(key: str, default: str) -> str:
    env_value = os.getenv(key)
    if env_value not in (None, ""):
        return env_value
    if key in st.secrets:
        return str(st.secrets[key])
    return default


def get_connection_context() -> dict[str, str]:
    host = config_value("DB_HOST", "localhost")
    is_local_host = host in {"localhost", "127.0.0.1", "::1"}
    sslmode = config_value("DB_SSLMODE", "prefer" if is_local_host else "require")
    env_file = os.getenv("ENV_FILE") or ".env"

    return {
        "env_file": env_file,
        "db_name": config_value("DB_NAME", "care_analytics"),
        "db_host": host,
        "db_port": config_value("DB_PORT", "5432"),
        "sslmode": sslmode,
    }


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
    context = get_connection_context()
    host = context["db_host"]
    is_local_host = host in {"localhost", "127.0.0.1", "::1"}
    sslmode = context["sslmode"]

    connect_kwargs = {
        "dbname": context["db_name"],
        "user": config_value("DB_USER", "postgres"),
        "password": config_value("DB_PASSWORD", "postgres"),
        "host": host,
        "port": int(context["db_port"]),
        "sslmode": sslmode,
    }

    try:
        return psycopg2.connect(**connect_kwargs)
    except psycopg2.OperationalError as exc:
        error_text = str(exc).lower()
        if is_local_host and "server does not support ssl" in error_text and sslmode != "prefer":
            connect_kwargs["sslmode"] = "prefer"
            return psycopg2.connect(**connect_kwargs)
        raise


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


def get_latest_scored_end_date(conn) -> date | None:
    latest_df = pd.read_sql(
        """
        SELECT MAX(end_date_id) AS max_end_date_id
        FROM fact_resident_domain_score
        """,
        conn,
    )
    if latest_df.empty:
        return None

    max_end_date_id = latest_df.iloc[0]["max_end_date_id"]
    if pd.isna(max_end_date_id):
        return None

    return DateHelper.date_id_to_date(int(max_end_date_id))


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
            strokeDash=alt.StrokeDash(
                "risk_level:N",
                title="Risk Line",
                scale=alt.Scale(
                    domain=["RED", "AMBER", "GREEN"],
                    range=[[1, 0], [6, 3], [2, 2]],
                ),
            ),
            tooltip=["full_date:T", "risk_level:N", "resident_count:Q"],
        )
    )
    st.altair_chart(trend_chart, use_container_width=True)


def render_layer3(conn, start_date_id: int, end_date_id: int):
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

    period_days = int((DateHelper.date_id_to_date(end_date_id) - DateHelper.date_id_to_date(start_date_id)).days + 1)
    selected_end_date = DateHelper.date_id_to_date(end_date_id)
    st.markdown("### Trend")
    st.caption(
        "Each point is the score for that end date using the currently selected lookback window. "
        "This chart does not use event-level filtering."
    )

    trend_df = pd.read_sql(
        """
        SELECT
            dd.full_date,
            s.crs_total,
            s.dcs_percentage,
            s.refusal_count,
            s.max_gap_hours,
            s.actual_entries,
            s.expected_entries
        FROM fact_resident_domain_score s
        JOIN dim_date dd ON dd.date_id = s.end_date_id
        WHERE s.resident_id = %(resident_id)s
          AND s.domain_id = %(domain_id)s
          AND s.start_date_id = to_char(dd.full_date - (%(period_days)s::text || ' day')::interval + interval '1 day', 'YYYYMMDD')::int
          AND dd.full_date <= %(selected_end_date)s
        ORDER BY dd.full_date DESC
        LIMIT 30
        """,
        conn,
        params={
            "resident_id": selected_resident_id,
            "domain_id": selected_domain_id,
            "period_days": period_days,
            "selected_end_date": selected_end_date,
        },
    )

    if trend_df.empty:
        st.info("No recent trend snapshots available for this resident/domain.")
    else:
        trend_df = trend_df.sort_values("full_date")
        trend_df["dcs_capped"] = trend_df["dcs_percentage"].clip(upper=100)
        date_axis_format = "%d %b" if period_days <= 30 else "%b %Y"

        if trend_df["crs_total"].nunique() <= 1 and trend_df["dcs_percentage"].nunique() <= 1:
            st.info(
                "Trend is flat for the selected lookback window: stored CRS and DCS values are unchanged "
                "across these recent snapshots."
            )

        trend_col1, trend_col2 = st.columns(2)

        with trend_col1:
            crs_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("full_date:T", title="Date", axis=alt.Axis(format=date_axis_format, labelAngle=-25)),
                    y=alt.Y("crs_total:Q", title="CRS Points", scale=alt.Scale(domain=[0, 8])),
                    tooltip=["full_date:T", "crs_total:Q", "refusal_count:Q", "max_gap_hours:Q"],
                )
            )
            st.altair_chart(crs_chart, use_container_width=True)

        with trend_col2:
            dcs_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("full_date:T", title="Date", axis=alt.Axis(format=date_axis_format, labelAngle=-25)),
                    y=alt.Y("dcs_capped:Q", title="DCS % (capped at 100)", scale=alt.Scale(domain=[0, 100])),
                    tooltip=["full_date:T", "dcs_percentage:Q", "actual_entries:Q", "expected_entries:Q"],
                )
            )
            st.altair_chart(dcs_chart, use_container_width=True)

        drivers_col1, drivers_col2 = st.columns(2)
        with drivers_col1:
            gap_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("full_date:T", title="Date", axis=alt.Axis(format=date_axis_format, labelAngle=-25)),
                    y=alt.Y("max_gap_hours:Q", title="Max Gap (hours)", scale=alt.Scale(zero=False)),
                    tooltip=["full_date:T", "max_gap_hours:Q"],
                )
            )
            st.altair_chart(gap_chart, use_container_width=True)

        with drivers_col2:
            entries_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("full_date:T", title="Date", axis=alt.Axis(format=date_axis_format, labelAngle=-25)),
                    y=alt.Y("actual_entries:Q", title="Actual Entries", scale=alt.Scale(zero=False)),
                    tooltip=["full_date:T", "actual_entries:Q", "expected_entries:Q"],
                )
            )
            st.altair_chart(entries_chart, use_container_width=True)

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


def main():
    st.set_page_config(page_title="Care Analytics Dashboard", page_icon="🏥", layout="wide")
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] .env-footer-hidden {
            position: fixed;
            bottom: 0.6rem;
            left: 1rem;
            right: 1rem;
            color: var(--secondary-background-color) !important;
            font-size: 0.72rem;
            line-height: 1.25;
            user-select: text;
            z-index: 1000;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not check_password():
        st.stop()

    st.title("🏥 Care Analytics Dashboard")
    initialize_navigation_state()

    if st.sidebar.button("🚪 Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    conn = get_db_connection()
    default_end_date = get_latest_scored_end_date(conn) or date.today()

    st.sidebar.header("Analysis Period")
    end_date = st.sidebar.date_input("End date", default_end_date, key="analysis_end_date")

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

    if layer == LAYER_3:
        period_days = st.sidebar.selectbox(
            "Lookback (days)",
            [7, 14, 30, 365],
            index=get_default_index([7, 14, 30, 365], st.session_state.get("layer3_period_days", 30)),
            key="layer3_period_days",
        )
    else:
        period_days = st.sidebar.selectbox(
            "Lookback (days)",
            [7, 14, 30],
            index=get_default_index([7, 14, 30], st.session_state.get("layer12_period_days", 7)),
            key="layer12_period_days",
        )

    start_date_id, end_date_id = DateHelper.get_date_range(end_date, period_days)

    st.caption(
        f"Analysis period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}"
    )

    if layer == LAYER_1:
        render_layer1(conn, start_date_id, end_date_id)
    elif layer == LAYER_2:
        render_layer2(conn, start_date_id, end_date_id)
    else:
        render_layer3(conn, start_date_id, end_date_id)

    connection_context = get_connection_context()
    st.sidebar.markdown(
        (
            '<div class="env-footer-hidden">'
            f"env: {connection_context['env_file']}<br>"
            f"db: {connection_context['db_name']} @ {connection_context['db_host']}:{connection_context['db_port']}<br>"
            f"ssl: {connection_context['sslmode']}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
