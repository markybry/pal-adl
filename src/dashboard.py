import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import hashlib

# Page config
st.set_page_config(
    page_title="CQC ADL Audit Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Password protection
def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Default password hash (password: "admin123")
        # Generate your own: hashlib.sha256("your_password".encode()).hexdigest()
        correct_password_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
        
        # Check if password from secrets exists, otherwise use default
        if "password_hash" in st.secrets:
            correct_password_hash = st.secrets["password_hash"]
        
        entered_hash = hashlib.sha256(st.session_state["password"].encode()).hexdigest()
        
        if entered_hash == correct_password_hash:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # Return True if password is validated
    if st.session_state.get("password_correct", False):
        return True

    # Show login screen
    st.markdown("## 🔐 CQC ADL Audit Dashboard Login")
    st.markdown("This dashboard contains sensitive resident data. Please authenticate to continue.")
    
    st.text_input(
        "Password", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")
    
    st.markdown("---")
    st.caption("Default password: `admin123` (Change this in production!)")
    
    return False

# Check password before loading anything else
if not check_password():
    st.stop()

# Import the analysis functions AFTER authentication
from src.weeklyCareLogChecks import (
    df, ADL_DOMAINS, REFUSAL_THRESHOLDS, DOCUMENTATION_THRESHOLDS,
    analyze_adl_domain
)

# Custom CSS for better styling
st.markdown("""
<style>
    .risk-red { 
        background-color: #ffebee; 
        padding: 10px; 
        border-left: 5px solid #f44336;
        margin: 10px 0;
    }
    .risk-amber { 
        background-color: #fff3e0; 
        padding: 10px; 
        border-left: 5px solid #ff9800;
        margin: 10px 0;
    }
    .risk-green { 
        background-color: #e8f5e9; 
        padding: 10px; 
        border-left: 5px solid #4caf50;
        margin: 10px 0;
    }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🏥 CQC-Aligned ADL Domain Analysis Dashboard")

# Sidebar filters
st.sidebar.header("⚙️ Filters")

# Logout button at top of sidebar
if st.sidebar.button("🚪 Logout"):
    st.session_state["password_correct"] = False
    st.rerun()

# Date range selector
end_date = df['Time logged'].max()
start_date = end_date - timedelta(days=7)

days = st.sidebar.slider(
    "Analysis Period (days)",
    min_value=1,
    max_value=30,
    value=7,
    help="Select how many days to analyze"
)

# Recalculate dates
start_date = end_date - timedelta(days=days)

st.sidebar.markdown(f"**Analysis Period:**  \n{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")

# Domain filter
selected_domains = st.sidebar.multiselect(
    "Select ADL Domains",
    options=list(ADL_DOMAINS.keys()),
    default=list(ADL_DOMAINS.keys()),
    help="Filter by specific ADL domains"
)

# Risk level filter
risk_filter = st.sidebar.multiselect(
    "Filter by Risk Level",
    options=["RED", "AMBER", "GREEN"],
    default=["RED", "AMBER", "GREEN"],
    help="Show only selected risk levels"
)

# Display thresholds
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Risk Thresholds")
st.sidebar.markdown(f"""
**Refusals:**
- 🟢 <{REFUSAL_THRESHOLDS['amber']} = Normal
- 🟡 {REFUSAL_THRESHOLDS['amber']}+ = Monitoring
- 🔴 {REFUSAL_THRESHOLDS['red']}+ = Immediate Review

**Documentation:**
- 🟢 ≥{DOCUMENTATION_THRESHOLDS['amber']*100:.0f}% = Complete
- 🟡 {DOCUMENTATION_THRESHOLDS['red']*100:.0f}%-{DOCUMENTATION_THRESHOLDS['amber']*100:.0f}% = Monitoring
- 🔴 <{DOCUMENTATION_THRESHOLDS['red']*100:.0f}% = Critical
""")

# Main dashboard
st.markdown("---")

# Overall summary metrics
st.header("📈 Overall Summary")

# Collect all results across domains
all_results = {}
for domain_name, domain_config in ADL_DOMAINS.items():
    if domain_name in selected_domains:
        results = analyze_adl_domain(domain_name, domain_config, days)
        if results:
            all_results[domain_name] = results

# Count risk levels
red_count = 0
amber_count = 0
green_count = 0

for domain_results in all_results.values():
    for metrics in domain_results.values():
        if metrics['overall_risk'] == 'RED':
            red_count += 1
        elif metrics['overall_risk'] == 'AMBER':
            amber_count += 1
        else:
            green_count += 1

# Display metrics in columns
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("🔴 RED Risk", red_count, help="Immediate review required")
with col2:
    st.metric("🟡 AMBER Risk", amber_count, help="Monitoring required")
with col3:
    st.metric("🟢 GREEN Risk", green_count, help="No concerns")
with col4:
    total = red_count + amber_count + green_count
    st.metric("Total Assessments", total)

st.markdown("---")

# Domain-by-domain analysis
for domain_name, domain_config in ADL_DOMAINS.items():
    if domain_name not in selected_domains:
        continue
    
    st.header(f"📋 {domain_name.upper()}")
    
    # Domain info
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Expected Frequency:** {domain_config['expected_per_day']} per day")
    with col2:
        st.markdown(f"**Gap Thresholds:** {domain_config['max_gap_amber']}h (AMBER), {domain_config['max_gap_red']}h (RED)")
    
    results = analyze_adl_domain(domain_name, domain_config, days)
    
    if not results:
        st.info(f"No data available for {domain_name} in the analysis period.")
        continue
    
    # Filter by risk level
    filtered_results = {
        resident: metrics 
        for resident, metrics in results.items() 
        if metrics['overall_risk'] in risk_filter
    }
    
    if not filtered_results:
        st.info(f"No residents match the selected risk filters for {domain_name}.")
        continue
    
    # Create tabs for each resident
    resident_tabs = st.tabs(list(filtered_results.keys()))
    
    for tab, (resident, metrics) in zip(resident_tabs, filtered_results.items()):
        with tab:
            # Overall risk banner
            risk_class = f"risk-{metrics['overall_risk'].lower()}"
            risk_emoji = "🔴" if metrics['overall_risk'] == 'RED' else ("🟡" if metrics['overall_risk'] == 'AMBER' else "🟢")
            
            st.markdown(f"""
            <div class="{risk_class}">
                <h3>{risk_emoji} Overall Risk: {metrics['overall_risk']}</h3>
                <p><strong>Entries:</strong> {metrics['total_entries']} / {metrics['expected_entries']:.0f} expected</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Two columns for care risk and documentation
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🏥 Care Delivery Risk")
                care_emoji = "🔴" if metrics['care_risk'] == 'RED' else ("🟡" if metrics['care_risk'] == 'AMBER' else "🟢")
                st.markdown(f"**Level:** {care_emoji} {metrics['care_risk']} (Score: {metrics['care_score']})")
                
                if metrics['refusal_count'] > 0:
                    st.warning(f"⚠️ **Refusals:** {metrics['refusal_count']}")
                
                if metrics['max_gap_hours']:
                    st.info(f"⏱️ **Max Gap:** {metrics['max_gap_hours']:.1f} hours")
                
                if metrics['dependency_changed']:
                    st.error("📈 **Dependency Trend:** Increasing")
                
                if metrics['care_findings']:
                    st.markdown("**Findings:**")
                    for finding in metrics['care_findings']:
                        st.markdown(f"• {finding}")
            
            with col2:
                st.subheader("📝 Documentation Compliance")
                doc_emoji = "🔴" if metrics['doc_risk'] == 'RED' else ("🟡" if metrics['doc_risk'] == 'AMBER' else "🟢")
                st.markdown(f"**Level:** {doc_emoji} {metrics['doc_risk']} (Score: {metrics['doc_score']})")
                
                if metrics['doc_findings']:
                    for finding in metrics['doc_findings']:
                        st.markdown(f"• {finding}")
            
            # Assistance level breakdown
            st.subheader("📊 Assistance Level Breakdown")
            assistance_df = pd.DataFrame(
                list(metrics['assistance_breakdown'].items()),
                columns=['Assistance Level', 'Count']
            )
            assistance_df = assistance_df.sort_values('Count', ascending=False)
            
            # Display as bar chart
            st.bar_chart(assistance_df.set_index('Assistance Level'))
            
            # Display as table
            st.dataframe(assistance_df, width='stretch', hide_index=True)
    
    st.markdown("---")

# Footer
st.markdown("---")
st.caption("CQC-Aligned ADL Domain Analysis | Generated with Streamlit")
