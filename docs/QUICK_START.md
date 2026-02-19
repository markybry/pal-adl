# Quick Start Guide - Care Analytics System

**Goal**: Get from design documents to working system in 1 hour

---

## Step 1: Understand the Design (15 minutes)

### Read These First

1. **[DESIGN_COMPLETE.md](DESIGN_COMPLETE.md)** (5 min)
   - Overview of what was built
   - System architecture
   - Key features

2. **[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) - Section 1 only** (10 min)
   - Scoring Framework
   - CRS and DCS formulas
   - Fixed thresholds

### Key Concepts

- **Care Risk Score (CRS)** = Refusals + Gaps + Dependency (0-10 points)
  - 0-1: GREEN, 2-4: AMBER, 5+: RED

- **Documentation Compliance Score (DCS)** = Actual / Expected × 100
  - 90-100%: GREEN, 60-89%: AMBER, <60%: RED

- **Three Layers**:
  1. Executive Grid (all clients, all domains)
  2. Client View (all residents in one client)
  3. Resident Deep Dive (one resident, one domain)

---

## Step 2: Test the Scoring Engine (15 minutes)

### Run the Tests

```bash
cd c:\Users\marky\code\pal-adl
python tests/test_scoring_engine.py
```

**Expected output**:
```
Ran 31 tests in 0.004s
✅ ALL TESTS PASSED
```

### Understand a Test

Open [test_scoring_engine.py](../tests/test_scoring_engine.py) and find:

```python
def test_amber_scenario(self):
    # 2 refusals = 2 points = AMBER
    events = [...]
    crs = ScoringEngine.calculate_care_risk_score(events, ADL_DOMAINS['Oral Care'])
    self.assertEqual(crs.risk_level, RiskLevel.AMBER)
```

This shows how the scoring engine works.

### Try the Scoring Engine

Create `test_my_data.py`:

```python
from scoring_engine import ScoringEngine, ADLEvent, AssistanceLevel
from datetime import datetime

# Your test events
events = [
    ADLEvent(
        event_timestamp=datetime(2026, 2, 10, 8, 0),
        logged_timestamp=datetime(2026, 2, 10, 8, 0),
        assistance_level=AssistanceLevel.SOME_ASSISTANCE,
        is_refusal=False,
        event_title='Morning oral care'
    ),
    ADLEvent(
        event_timestamp=datetime(2026, 2, 10, 20, 0),
        logged_timestamp=datetime(2026, 2, 10, 20, 0),
        assistance_level=AssistanceLevel.REFUSED,
        is_refusal=True,
        event_title='Evening care - refused'
    ),
]

analysis = ScoringEngine.analyze_resident_domain(
    resident_id='TEST',
    domain_name='Oral Care',
    events=events,
    period_days=7
)

print(f"Overall Risk: {analysis.overall_risk.value}")
print(f"\nCare Risk Score:")
print(analysis.care_risk_score.explanation)
print(f"\nDocumentation Score:")
print(analysis.documentation_score.explanation)
```

Run it:
```bash
python test_my_data.py
```

---

## Step 3: Set Up the Database (15 minutes)

### Install PostgreSQL

**Windows**:
1. Download from https://www.postgresql.org/download/windows/
2. Run installer
3. Note your password

**Mac**:
```bash
brew install postgresql
brew services start postgresql
```

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo service postgresql start
```

### Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# In psql:
CREATE DATABASE care_analytics;
\q
```

### Load Schema

```bash
psql -U postgres -d care_analytics -f database/schema.sql
```

**Expected output**:
```
CREATE TABLE
CREATE TABLE
...
INSERT 0 5  (domains inserted)
...
```

### Load Company Data

Edit `database/seed_company.sql` with your organization info, then run:

```bash
psql -U postgres -d care_analytics -f database/seed_company.sql
```

**Expected output**:
```
INSERT 0 2
 status          | count
-----------------+-------
 Companies Loaded:| 2
...
```

### Enable Idempotent Import (one-time)

```bash
psql -U postgres -d care_analytics -f database/migrations/002_add_event_dedupe_index.sql
```

This ensures re-running the same CSV will not create duplicate events.

### Verify

```bash
psql -U postgres -d care_analytics

# In psql:
\dt  -- List tables
SELECT * FROM dim_domain;  -- Should show 5 ADL domains
SELECT * FROM dim_client;  -- Should show your company/companies
\q
```

---

## Step 4: Import Your Data (15 minutes)

### Configure Database Connection

**Option 1: Use .env file** (recommended)

Copy the example file:
```bash
cp .env.example .env
```

Edit `.env` with your password:
```env
DB_NAME=care_analytics
DB_USER=postgres
DB_PASSWORD=your_actual_password
DB_HOST=localhost
DB_PORT=5432
```

**Option 2: Pass password on command line**

Use `--password` flag (see examples below)

### Run the Import

Test with first 100 rows:
```bash
python scripts/import_csv_to_db.py logs.csv --client "Your Care Home" --limit 100
```

Import all data:
```bash
python scripts/import_csv_to_db.py logs.csv --client "Your Care Home"
```

**Expected output**:
```
============================================================
Care Analytics - CSV Import Tool
============================================================
✓ Loaded 5000 rows from logs.csv

🔌 Connecting to database: care_analytics
✓ Connected

📋 Setting up client: Your Care Home
✓ Found 5 domains in database
✓ Found 45 unique residents in CSV
✓ Created/verified 45 residents

📥 Importing first 100 events...
  ✓ Imported 100 events...

============================================================
✅ Import complete!
   Imported: 100 events
   Skipped:  0 events
   Errors:   0 events
============================================================
```

### CSV Requirements

Your CSV should have these columns:
- `Time logged` - Event timestamp
- `Resident` - Resident name
- `Item` - Domain type (e.g., "Getting Washed", "Oral Hygiene")
- `Title` - Event title
- `Description` - Event description
- `Staff` (optional) - Staff member name

**Note**: See [scripts/README.md](../scripts/README.md) for full documentation and options.

---

## Step 5: Calculate Scores (10 minutes)

Use the built-in batch script:

```bash
python scripts/calculate_scores.py --periods 7,14,30
```

Optional examples:

```bash
# Calculate only 7-day scores
python scripts/calculate_scores.py --periods 7

# Calculate for one client
python scripts/calculate_scores.py --periods 7,14,30 --client "Your Care Home"

# Backfill for a specific date
python scripts/calculate_scores.py --periods 7,14,30 --end-date 2026-02-19
```

Run it:
```bash
python scripts/calculate_scores.py --periods 7,14,30
```

**Expected output**:
```
Care Analytics - Score Calculation
Calculating 7-day scores...
✓ Written 120 scores (processed 150, skipped 30)
...
Score Calculation Complete
```

---

## Step 6: Launch Dashboard v2 (5 minutes)

Run the database-backed dashboard:

```bash
streamlit run src/dashboard_v2.py
```

What you should see:
- Client × Domain executive grid
- Primary risk as traffic lights (CRS)
- Documentation mismatch badge when DCS differs
- 7/14/30/365-day period selector
- Click-through drilldown flow (Layer 1 → Layer 2 → Layer 3)
- CSV exports on each layer

How to navigate:
1. Start in Layer 1 and choose a client/domain in the Drill-down section.
2. Open Layer 2, then pick a resident/domain and open Layer 3.
3. Use back buttons to return to prior layers.

If no data appears, calculate scores first with:

```bash
python scripts/calculate_scores.py --periods 7,14,30
```

---

## What You've Accomplished

In 1 hour, you have:

✅ **Understood the design**
- Dual scoring system (CRS + DCS)
- Three-layer dashboard architecture
- Fixed thresholds

✅ **Tested the scoring engine**
- Ran 31 unit tests
- Understood how scoring works
- Tested with sample data

✅ **Set up the database**
- PostgreSQL installed
- Star schema created
- Dimensions populated

✅ **Imported data**
- CSV → PostgreSQL
- 100 events loaded
- Validated import

✅ **Calculated scores**
- Ran scoring engine
- Stored results in database
- Verified calculations

---

## Next Steps

### Today
1. Import all historical data (not just 100 events)
2. Calculate scores for all periods (7, 14, 30 days)
3. Review scores with care managers

### This Week
1. Build dashboard prototype (Layer 1)
2. Test executive grid with stakeholders
3. Plan dashboard rollout

### Next Week
1. Complete all dashboard layers
2. Set up automated nightly scoring
3. Train users

### This Month
1. Go live with new system
2. Run parallel with old system for validation
3. Decommission old system

---

## Troubleshooting

**PostgreSQL connection error**:
- Check password in connection strings
- Verify PostgreSQL is running: `pg_ctl status`

**Import errors**:
- Check CSV column names match code
- Verify date format: `%d/%m/%Y %H:%M:%S`
- Check logs.csv exists

**Scoring errors**:
- Ensure events exist in database
- Check domain_name matches exactly
- Verify date range has data

**Need help?**:
- See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)
- Review [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md)
- Check test examples in [test_scoring_engine.py](../tests/test_scoring_engine.py)

---

**Ready for the full implementation?** Follow [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for the complete 5-week plan.
