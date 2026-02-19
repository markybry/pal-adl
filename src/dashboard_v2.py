import hashlib
import os
import sys
from datetime import date
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


def main():
    st.set_page_config(page_title="Care Analytics - Executive Grid", page_icon="🏥", layout="wide")

    if not check_password():
        st.stop()

    st.title("🏥 Care Analytics - Executive Grid")

    if st.sidebar.button("🚪 Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.sidebar.header("Analysis Period")
    period_days = st.sidebar.selectbox("Lookback (days)", [7, 14, 30], index=0)
    end_date = st.sidebar.date_input("End date", date.today())

    start_date_id, end_date_id = DateHelper.get_date_range(end_date, period_days)

    conn = get_db_connection()
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

    st.caption(
        f"Analysis period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}"
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


if __name__ == "__main__":
    main()
