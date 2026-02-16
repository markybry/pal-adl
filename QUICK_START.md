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
python test_scoring_engine.py
```

**Expected output**:
```
Ran 31 tests in 0.004s
✅ ALL TESTS PASSED
```

### Understand a Test

Open [test_scoring_engine.py](test_scoring_engine.py) and find:

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
psql -U postgres -d care_analytics -f schema.sql
```

**Expected output**:
```
CREATE TABLE
CREATE TABLE
...
INSERT 0 5  (domains inserted)
...
```

### Verify

```bash
psql -U postgres -d care_analytics

# In psql:
\dt  -- List tables
SELECT * FROM dim_domain;  -- Should show 5 ADL domains
\q
```

---

## Step 4: Import Your Data (15 minutes)

### Create ETL Script

Create `quick_import.py`:

```python
import pandas as pd
import psycopg2
from datetime import datetime
from scoring_engine import parse_assistance_level, is_refusal

# Connect to database
conn = psycopg2.connect(
    dbname='care_analytics',
    user='postgres',
    password='your_password',  # Change this!
    host='localhost'
)
cursor = conn.cursor()

# Insert a test client
cursor.execute("""
    INSERT INTO dim_client (client_name, client_type)
    VALUES ('Test Care Home', 'Care Home')
    RETURNING client_id
""")
client_id = cursor.fetchone()[0]
conn.commit()

# Insert a test resident
cursor.execute("""
    INSERT INTO dim_resident (resident_name, client_id, admission_date)
    VALUES ('Test Resident', %s, CURRENT_DATE)
    RETURNING resident_id
""", (client_id,))
resident_id = cursor.fetchone()[0]
conn.commit()

# Load your CSV (adjust path and column names as needed)
df = pd.read_csv('logs.csv')
df['Time logged'] = pd.to_datetime(df['Time logged'], format='%d/%m/%Y %H:%M:%S')

# Domain mapping
domain_map = {
    'Getting Washed': 'Washing/Bathing',
    'Oral Hygiene': 'Oral Care',
    'Getting Dressed': 'Dressing/Clothing',
    'Toileting': 'Toileting',
    'Shaving': 'Grooming',
    'Hair Care': 'Grooming'
}

# Get domain IDs
cursor.execute("SELECT domain_id, domain_name FROM dim_domain")
domains = {name: id for id, name in cursor.fetchall()}

# Import first 100 events (for testing)
for idx, row in df.head(100).iterrows():
    domain_name = domain_map.get(row['Item'])
    if not domain_name:
        continue
    
    domain_id = domains.get(domain_name)
    if not domain_id:
        continue
    
    # Parse assistance and refusal
    assistance = parse_assistance_level(
        str(row.get('Description', '')),
        str(row.get('Title', ''))
    )
    refusal = is_refusal(
        str(row.get('Description', '')),
        str(row.get('Title', ''))
    )
    
    # Get date_id
    event_date = row['Time logged'].date()
    date_id = int(event_date.strftime('%Y%m%d'))
    
    # Insert event
    try:
        cursor.execute("""
            INSERT INTO fact_adl_event (
                resident_id, domain_id, date_id,
                event_timestamp, logged_timestamp,
                assistance_level, is_refusal,
                event_title, event_description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            resident_id,
            domain_id,
            date_id,
            row['Time logged'],
            row['Time logged'],
            assistance.value,
            refusal,
            row.get('Title'),
            row.get('Description')
        ))
    except Exception as e:
        print(f"Error importing row {idx}: {e}")
        continue

conn.commit()

# Check what was imported
cursor.execute("SELECT COUNT(*) FROM fact_adl_event")
count = cursor.fetchone()[0]
print(f"✅ Imported {count} events")

cursor.close()
conn.close()
```

Run it:
```bash
python quick_import.py
```

**Expected output**:
```
✅ Imported 100 events
```

---

## Step 5: Calculate Scores (10 minutes)

### Create Score Calculator

Create `quick_score.py`:

```python
import psycopg2
from datetime import date, timedelta
from scoring_engine import ScoringEngine, ADLEvent, AssistanceLevel
from dashboard_queries import DateHelper

conn = psycopg2.connect(
    dbname='care_analytics',
    user='postgres',
    password='your_password',
    host='localhost'
)
cursor = conn.cursor()

# Get date range
end_date = date.today()
start_date = end_date - timedelta(days=6)  # 7 days
start_date_id = DateHelper.date_to_date_id(start_date)
end_date_id = DateHelper.date_to_date_id(end_date)

# Get all residents
cursor.execute("SELECT resident_id, resident_name FROM dim_resident WHERE is_active = TRUE")
residents = cursor.fetchall()

# Get all domains
cursor.execute("SELECT domain_id, domain_name FROM dim_domain")
domains = cursor.fetchall()

scores_calculated = 0

for resident_id, resident_name in residents:
    for domain_id, domain_name in domains:
        # Fetch events
        cursor.execute("""
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
            ORDER BY event_timestamp
        """, (resident_id, domain_id, start_date, end_date))
        
        rows = cursor.fetchall()
        if not rows:
            continue
        
        # Convert to ADLEvent objects
        events = [
            ADLEvent(
                event_timestamp=row[0],
                logged_timestamp=row[1],
                assistance_level=AssistanceLevel(row[2]),
                is_refusal=row[3],
                event_title=row[4],
                event_description=row[5]
            )
            for row in rows
        ]
        
        # Calculate scores
        analysis = ScoringEngine.analyze_resident_domain(
            resident_id=str(resident_id),
            domain_name=domain_name,
            events=events,
            period_days=7
        )
        
        # Store score
        cursor.execute("""
            INSERT INTO fact_resident_domain_score (
                resident_id, domain_id,
                start_date_id, end_date_id,
                crs_level, crs_total,
                crs_refusal_score, crs_gap_score, crs_dependency_score,
                refusal_count, max_gap_hours,
                dcs_level, dcs_percentage,
                actual_entries, expected_entries
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (resident_id, domain_id, start_date_id, end_date_id)
            DO NOTHING
        """, (
            resident_id, domain_id,
            start_date_id, end_date_id,
            analysis.care_risk_score.risk_level.value,
            analysis.care_risk_score.total_points,
            analysis.care_risk_score.components[0].points,
            analysis.care_risk_score.components[1].points,
            analysis.care_risk_score.components[2].points,
            analysis.refusal_count,
            analysis.max_gap_hours,
            analysis.documentation_score.risk_level.value,
            analysis.documentation_score.compliance_percentage,
            analysis.total_events,
            analysis.documentation_score.expected_entries
        ))
        
        scores_calculated += 1
        print(f"✓ {resident_name} - {domain_name}: {analysis.overall_risk.value}")

conn.commit()
print(f"\n✅ Calculated {scores_calculated} scores")

cursor.close()
conn.close()
```

Run it:
```bash
python quick_score.py
```

**Expected output**:
```
✓ Test Resident - Oral Care: GREEN
✓ Test Resident - Toileting: AMBER
...
✅ Calculated 5 scores
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
- Check test examples in [test_scoring_engine.py](test_scoring_engine.py)

---

**Ready for the full implementation?** Follow [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for the complete 5-week plan.
