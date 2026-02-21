# Implementation Roadmap

**From Current CSV System → Star Schema Risk Intelligence Platform**

---

## Current State

**Files:**
- `logs.csv` - Raw care log exports
- `weeklyCareLogChecks.py` - Analysis logic
- `dashboard_v2.py` - Streamlit UI

**Architecture:**
- CSV file loaded into pandas DataFrame
- Analysis functions calculate scores on-the-fly
- Dashboard queries DataFrame directly

**Limitations:**
- Single CSV file (no multi-client support)
- No historical trend analysis
- Slow for large datasets
- Limited auditability (calculations not persisted)

---

## Target State

**Database:**
- PostgreSQL star schema
- Multi-client support
- Historical score tracking
- Pre-aggregated scores for performance

**Scoring Engine:**
- Explicit, testable formulas
- Dual scoring (CRS + DCS)
- Fixed thresholds (no drift)

**Dashboard:**
- Three-layer architecture
- Executive grid → Client view → Resident deep dive
- Real-time and pre-calculated modes

---

## Migration Strategy

### Option A: Gradual Migration (Recommended)

**Phase 1: Add Database (Parallel Run)**
1. Set up PostgreSQL database
2. Import logs.csv → fact_adl_event
3. Keep current dashboard running
4. Validate scoring consistency

**Phase 2: New Dashboard Layer 1**
1. Build executive grid using star schema
2. Test with stakeholders
3. Keep Layer 2/3 using old system

**Phase 3: Complete Migration**
1. Build Layer 2 and 3
2. Replace old dashboard
3. Decommission CSV-based system

### Option B: Clean Break

1. Build entire star schema system
2. Test thoroughly in staging
3. Cutover on a specific date
4. Archive old system

**Recommendation**: Option A - reduces risk, allows validation at each step.

---

## Implementation Phases

### Phase 1: Database Setup (Week 1)

**Tasks:**

1. **Install PostgreSQL**
   ```bash
   # Ubuntu/Debian
   sudo apt install postgresql postgresql-contrib
   
   # macOS
   brew install postgresql
   
   # Windows - Download installer from postgresql.org
   ```

2. **Create Database**
   ```bash
   createdb care_analytics
   psql care_analytics < database/schema.sql
   ```

3. **Load Company Data**
   
   Edit `database/seed_company.sql` with your organization info:
   ```sql
   INSERT INTO dim_client (client_name, client_type, address, primary_contact, phone, is_active, contract_start)
   VALUES
       ('Your Care Home Name', 'Care Home', '123 Main St', 'Manager Name', '555-0100', TRUE, '2024-01-01');
   ```
   
   Then run:
   ```bash
   psql care_analytics < database/seed_company.sql
   ```

4. **Verify Schema**
   ```sql
   -- Check tables created
   \dt
   
   -- Check domain data populated
   SELECT * FROM dim_domain;
   
   -- Check your company loaded
   SELECT * FROM dim_client;
   ```

**Deliverables:**
- ✅ Working PostgreSQL database
- ✅ Star schema tables created
- ✅ Dimensions populated
- ✅ Date dimension populated (2020-2030)

---

### Phase 2: ETL Pipeline (Week 1-2)

**Tasks:**

1. **Create ETL Script**

Create `etl_import_logs.py`:

```python
import pandas as pd
import psycopg2
from datetime import datetime

def import_csv_to_star_schema(csv_path, conn):
    """Import logs.csv into star schema"""
    
    # Load CSV
    df = pd.read_csv(csv_path)
    df['Time logged'] = pd.to_datetime(df['Time logged'], format='%d/%m/%Y %H:%M:%S')
    
    cursor = conn.cursor()
    
    # Map ADL items to domains
    domain_mapping = {
        'Getting Washed': 'Washing/Bathing',
        'Oral Hygiene': 'Oral Care',
        'Getting Dressed': 'Dressing/Clothing',
        'Toileting': 'Toileting',
        'Shaving': 'Grooming',
        'Hair Care': 'Grooming'
    }
    
    # Get dimension IDs
    cursor.execute("SELECT resident_id, resident_name FROM dim_resident")
    resident_map = {name: id for id, name in cursor.fetchall()}
    
    cursor.execute("SELECT domain_id, domain_name FROM dim_domain")
    domain_map = {name: id for id, name in cursor.fetchall()}
    
    # Import each row
    imported = 0
    for _, row in df.iterrows():
        domain_name = domain_mapping.get(row['Item'])
        if not domain_name:
            continue
        
        resident_id = resident_map.get(row['Resident'])
        domain_id = domain_map.get(domain_name)
        
        if not resident_id or not domain_id:
            continue
        
        # Detect assistance level and refusal
        from src.scoring_engine import parse_assistance_level, is_refusal
        
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
        cursor.execute("""
            INSERT INTO fact_adl_event (
                resident_id, domain_id, date_id,
                event_timestamp, logged_timestamp,
                assistance_level, is_refusal,
                event_title, event_description,
                source_system
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CSV Import'
            )
            ON CONFLICT DO NOTHING
        """, (
            resident_id,
            domain_id,
            date_id,
            row['Time logged'],
            row['Time logged'],  # Assume same as event time
            assistance.value,
            refusal,
            row.get('Title'),
            row.get('Description'),
            'CSV Import'
        ))
        
        imported += 1
        if imported % 100 == 0:
            print(f"Imported {imported} events...")
            conn.commit()
    
    conn.commit()
    print(f"Import complete: {imported} events")
    
    return imported

# Usage:
# conn = psycopg2.connect("dbname=care_analytics user=postgres")
# import_csv_to_star_schema('logs.csv', conn)
```

2. **Run Import**
   ```python
   python etl_import_logs.py
   ```

3. **Validate Import**
   ```sql
   -- Check event count
   SELECT COUNT(*) FROM fact_adl_event;
   
   -- Check date range
   SELECT MIN(event_timestamp), MAX(event_timestamp)
   FROM fact_adl_event;
   
   -- Check distribution by domain
   SELECT d.domain_name, COUNT(*) AS event_count
   FROM fact_adl_event e
   JOIN dim_domain d ON e.domain_id = d.domain_id
   GROUP BY d.domain_name
   ORDER BY event_count DESC;
   ```

**Deliverables:**
- ✅ ETL script that converts CSV → star schema
- ✅ All historical data imported
- ✅ Data validation passed

---

### Phase 3: Scoring Engine Integration (Week 2)

**Tasks:**

1. **Create Score Calculator Script**

Create `calculate_scores.py`:

```python
"""
Batch score calculation - populates fact_resident_domain_score
"""

import psycopg2
from datetime import date, timedelta
from src.scoring_engine import ScoringEngine, ADLEvent, AssistanceLevel, ADL_DOMAINS
from src.dashboard_queries import DateHelper

def calculate_and_store_scores(conn, end_date: date, period_days: int):
    """Calculate scores for all residents and store in DB"""
    
    cursor = conn.cursor()
    start_date = end_date - timedelta(days=period_days-1)
    start_date_id = DateHelper.date_to_date_id(start_date)
    end_date_id = DateHelper.date_to_date_id(end_date)
    
    # Get all active residents
    cursor.execute("""
        SELECT resident_id, resident_name
        FROM dim_resident
        WHERE is_active = TRUE
    """)
    residents = cursor.fetchall()
    
    # Get all domains
    cursor.execute("SELECT domain_id, domain_name FROM dim_domain")
    domains = cursor.fetchall()
    
    total_scores = 0
    
    for resident_id, resident_name in residents:
        for domain_id, domain_name in domains:
            # Fetch events for this resident-domain-period
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
                  AND event_timestamp BETWEEN %s AND %s
                ORDER BY event_timestamp
            """, (resident_id, domain_id, start_date, end_date))
            
            rows = cursor.fetchall()
            if not rows:
                continue  # No events for this combination
            
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
                period_days=period_days
            )
            
            # Store scores
            cursor.execute("""
                INSERT INTO fact_resident_domain_score (
                    resident_id, domain_id,
                    start_date_id, end_date_id,
                    crs_level, crs_total,
                    crs_refusal_score, crs_gap_score, crs_dependency_score,
                    refusal_count, max_gap_hours, dependency_trend,
                    dcs_level, dcs_percentage,
                    actual_entries, expected_entries
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                    dcs_level = EXCLUDED.dcs_level,
                    dcs_percentage = EXCLUDED.dcs_percentage,
                    actual_entries = EXCLUDED.actual_entries,
                    expected_entries = EXCLUDED.expected_entries,
                    calculated_at = NOW()
            """, (
                resident_id, domain_id,
                start_date_id, end_date_id,
                analysis.care_risk_score.risk_level.value,
                analysis.care_risk_score.total_points,
                analysis.care_risk_score.components[0].points,  # refusal
                analysis.care_risk_score.components[1].points,  # gap
                analysis.care_risk_score.components[2].points,  # dependency
                analysis.refusal_count,
                analysis.max_gap_hours,
                None,  # dependency_trend text description
                analysis.documentation_score.risk_level.value,
                analysis.documentation_score.compliance_percentage,
                analysis.total_events,
                analysis.documentation_score.expected_entries
            ))
            
            total_scores += 1
    
    conn.commit()
    print(f"Calculated and stored {total_scores} scores")
    return total_scores

# Usage:
# conn = psycopg2.connect("dbname=care_analytics user=postgres")
# calculate_and_store_scores(conn, date.today(), period_days=7)
```

2. **Run Score Calculation**
   ```python
   python calculate_scores.py
   ```

3. **Validate Scores**
   ```sql
   -- Check scores calculated
   SELECT COUNT(*) FROM fact_resident_domain_score;
   
   -- Check risk distribution
   SELECT 
       crs_level,
       COUNT(*) AS count,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
   FROM fact_resident_domain_score
   GROUP BY crs_level;
   
   -- Compare with old system (manual check)
   SELECT * FROM v_latest_scores LIMIT 10;
   ```

**Deliverables:**
- ✅ Score calculation script working
- ✅ Scores match old system (±10% expected due to formula refinements)
- ✅ fact_resident_domain_score populated

---

### Phase 4: Dashboard Layer 1 (Week 3)

**Tasks:**

1. **Create New Dashboard File**

Create `dashboard_v2.py`:

```python
import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta
from dashboard_queries import DashboardQueries, DateHelper

# Database connection
@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        dbname="care_analytics",
        user="postgres",
        password="your_password",
        host="localhost"
    )

st.set_page_config(page_title="Care Analytics - Executive View", layout="wide")

# Date range selector
st.sidebar.header("Analysis Period")
period_days = st.sidebar.selectbox("Period", [7, 14, 30], index=0)
end_date = st.sidebar.date_input("End Date", date.today())

start_date_id, end_date_id = DateHelper.get_date_range(end_date, period_days)

# Query executive grid
conn = get_db_connection()
query = DashboardQueries.layer1_executive_grid(start_date_id, end_date_id)
df = pd.read_sql(query, conn, params={
    'start_date_id': start_date_id,
    'end_date_id': end_date_id
})

# Display grid
st.title("🏥 Care Analytics - Executive Grid")
st.caption(f"Analysis Period: {DateHelper.date_id_to_date(start_date_id)} to {DateHelper.date_id_to_date(end_date_id)}")

# Pivot for grid display
df_pivot = df.pivot(
    index='client_name',
    columns='domain_name',
    values='primary_risk'
)

# Apply color styling
def color_risk(val):
    if val == 'RED':
        return 'background-color: #ffcdd2; color: #b71c1c'
    elif val == 'AMBER':
        return 'background-color: #ffe0b2; color: #e65100'
    elif val == 'GREEN':
        return 'background-color: #c8e6c9; color: #2e7d32'
    return ''

st.dataframe(
    df_pivot.style.applymap(color_risk),
    use_container_width=True
)

# Summary stats
st.subheader("Summary")
total_cells = len(df)
red_count = (df['primary_risk'] == 'RED').sum()
amber_count = (df['primary_risk'] == 'AMBER').sum()
green_count = (df['primary_risk'] == 'GREEN').sum()

col1, col2, col3 = st.columns(3)
col1.metric("🔴 RED", red_count, f"{red_count/total_cells*100:.0f}%")
col2.metric("🟡 AMBER", amber_count, f"{amber_count/total_cells*100:.0f}%")
col3.metric("🟢 GREEN", green_count, f"{green_count/total_cells*100:.0f}%")
```

2. **Test Dashboard**
   ```bash
   streamlit run dashboard_v2.py
   ```

**Deliverables:**
- ✅ Executive grid displays correctly
- ✅ Traffic light colors work
- ✅ Date range filter works
- ✅ Performance acceptable (<1s load time)

---

### Phase 5: Dashboard Layers 2 & 3 (Week 3-4)

**Tasks:**

1. **Add Client View to Dashboard**
   - Resident breakdown table
   - Alert summaries
   - Trend chart

2. **Add Resident Deep Dive**
   - Event timeline
   - Score breakdown with explanation
   - Assistance distribution chart

3. **Add Navigation**
   - Click grid cell → Client view
   - Click resident → Deep dive
   - Breadcrumb navigation

**Deliverables:**
- ✅ All three layers functional
- ✅ Drill-down navigation works
- ✅ Score explanations visible
- ✅ Export functionality

---

### Phase 6: Automated Scoring (Week 4)

**Tasks:**

1. **Create Scheduled Job**

Create `nightly_score_update.sh`:

```bash
#!/bin/bash
# Run nightly at 2 AM

cd /path/to/care-analytics
source venv/bin/activate

# Calculate scores for yesterday (7, 14, 30 day windows)
python -c "
from calculate_scores import calculate_and_store_scores
import psycopg2
from datetime import date

conn = psycopg2.connect('dbname=care_analytics user=postgres')

for period in [7, 14, 30]:
    calculate_and_store_scores(conn, date.today(), period)
    
conn.close()
"

echo "Score update complete: $(date)"
```

2. **Add to Cron (Linux/Mac)**
   ```bash
   crontab -e
   # Add line:
   0 2 * * * /path/to/nightly_score_update.sh >> /var/log/care_analytics_scoring.log 2>&1
   ```

3. **Or Windows Task Scheduler**
   - Create task that runs `python calculate_scores.py` daily at 2 AM

**Deliverables:**
- ✅ Nightly scoring automated
- ✅ Logs created for monitoring
- ✅ Email alerts on failure (optional)

---

### Phase 7: Testing & Validation (Week 4-5)

**Test Cases:**

1. **Data Integrity**
   - No duplicate events
   - All residents have scores
   - Date ranges consistent

2. **Scoring Accuracy**
   - Manual calculation matches system (spot check 10 residents)
   - Threshold boundaries work correctly (test edge cases)
   - Score explanations match actual calculation

3. **Performance**
   - Layer 1 loads in <1s for 1000 residents
   - Layer 2 loads in <2s
   - Layer 3 loads in <1s

4. **Audit Defense**
   - Print sample audit report
   - Verify score traceability to raw events
   - Check threshold documentation

**Deliverables:**
- ✅ All test cases pass
- ✅ Performance benchmarks met
- ✅ Sample audit report generated

---

### Phase 8: Go-Live (Week 5)

**Tasks:**

1. **Stakeholder Training**
   - Demo all three dashboard layers
   - Explain scoring logic
   - Walkthrough drill-down navigation

2. **Cutover**
   - Switch URL from old dashboard to new
   - Keep old system running for 1 week (parallel)

3. **Monitor**
   - Check for errors first week
   - Gather user feedback
   - Adjust UI based on feedback

**Deliverables:**
- ✅ Users trained
- ✅ System live
- ✅ Old system archived

---

## Maintenance Plan

### Daily
- Automated score calculation (2 AM)
- Check log files for errors

### Weekly
- Review RED alerts with care managers
- Update resident admissions/discharges
- Check database size/performance

### Monthly
- Review and validate thresholds
- Generate audit reports
- Database backup

### Quarterly
- Full audit with sample residents
- Performance optimization review
- User feedback survey

---

## Rollback Plan

If critical issues arise:

1. **Immediate**: Switch back to old dashboard URL
2. **Database**: No changes needed (star schema remains)
3. **Investigate**: Review logs, identify issue
4. **Fix**: Deploy patch
5. **Retry**: Switch back to new system

---

## Success Criteria

### Technical
- ✅ All events imported successfully
- ✅ Scores calculated for all active residents
- ✅ Dashboard loads in <2s
- ✅ Zero data loss vs old system

### Business
- ✅ CQC inspectors can use reports
- ✅ Care managers use daily for risk tracking
- ✅ Audit trails defensible
- ✅ Multi-client support working

### Audit
- ✅ Score calculation fully documented
- ✅ Thresholds justified and recorded
- ✅ Every score traceable to raw events
- ✅ Historical changes tracked

---

## Next Steps

**Immediate (Next 24 hours):**
1. Review system design with team
2. Set up PostgreSQL database
3. Run initial schema creation

**This Week:**
1. Import historical CSV data
2. Validate scores match current system
3. Build Layer 1 dashboard prototype

**Next Week:**
1. Complete all dashboard layers
2. User acceptance testing
3. Schedule go-live date

**This Month:**
1. Full system live
2. Automated scoring running
3. Old system decommissioned

---

**Questions?** Review [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for detailed specifications.
