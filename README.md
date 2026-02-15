# CQC ADL Audit Dashboard

Interactive Streamlit dashboard for analyzing weekly care log data aligned with CQC expectations.

## 🔐 Security

**Password Protected** - Dashboard requires authentication to access sensitive resident data.

- **Default password:** `admin123` (⚠️ Change immediately!)
- See [PASSWORD_SETUP.md](PASSWORD_SETUP.md) for configuration

## Features

- 📊 **Interactive Filters**: Select date ranges, ADL domains, and risk levels
- 🎯 **Risk-Based Overview**: Immediate visual summary of RED/AMBER/GREEN assessments
- 📋 **Domain Analysis**: Deep dive into each ADL category
- 👤 **Resident Tabs**: Individual resident views with detailed metrics
- 📈 **Visual Analytics**: Charts showing assistance level breakdowns
- 🔍 **Dual Risk Scoring**: Separate views for care delivery vs documentation compliance

## Running the Dashboard

### Command Line
```bash
streamlit run dashboard.py
```

### What to Expect
The dashboard will open in your default browser at `http://localhost:8501`

## Dashboard Sections

### Sidebar Filters
- **Analysis Period**: Adjust from 1-30 days
- **ADL Domains**: Select which domains to analyze
- **Risk Level**: Filter by RED/AMBER/GREEN
- **Thresholds**: View current CQC-aligned risk criteria

### Main View
- **Overall Summary**: Total counts by risk level
- **Domain Sections**: Each ADL domain with:
  - Expected frequencies and gap thresholds
  - Resident tabs with expandable details
  - Care delivery risk assessment
  - Documentation compliance check
  - Assistance level breakdowns (chart + table)

## Risk Thresholds (Consistent & Defensible)

**Refusals:**
- 2+ = AMBER (monitoring required)
- 4+ = RED (immediate review)

**Documentation:**
- <60% = AMBER (monitoring required)
- <40% = RED (critical gap)

**Time Gaps:** Domain-specific thresholds documented in code

## Technical Notes

- Built with Streamlit for Python
- Imports analysis functions from `weeklyCareLogChecks.py`
- Uses the same data source (`logs.csv`)
- All CQC alignment logic remains consistent with CLI version
