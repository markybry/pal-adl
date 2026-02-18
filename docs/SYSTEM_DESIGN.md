# Care Analytics System - Complete Design Specification

**System Purpose**: Risk Intelligence & Audit Layer for Care Log Analytics  
**Design Date**: February 16, 2026  
**Architecture**: Star Schema → Scoring Engine → Layered Dashboard

---

## 1. SCORING FRAMEWORK

### 1.1 Care Risk Score (CRS)

**Purpose**: Measure actual care delivery quality and resident wellbeing risk.

#### Formula Components:

```
CRS = RefusalScore + GapScore + DependencyScore

Where each component contributes 0-3 points:
  Total Score:
    0-1   = GREEN  (No concern)
    2-4   = AMBER  (Monitoring required)
    5+    = RED    (Immediate review)
```

#### Component Logic:

**A. Refusal Score** (Domain-agnostic)
```
Refusal Count in Period:
  0-1 refusals  → 0 points
  2-3 refusals  → 2 points  [AMBER threshold]
  4+ refusals   → 3 points  [RED threshold]
```

**Rationale**: Refusals indicate unmet needs, reluctance, or dignity concerns. Fixed thresholds prevent normalization of chronic refusal patterns.

---

**B. Gap Score** (Domain-specific)
```python
# Domain-specific maximum acceptable gaps (hours):
DOMAIN_GAPS = {
    'Washing/Bathing':     {'amber': 24, 'red': 48},
    'Oral Care':           {'amber': 16, 'red': 24},
    'Dressing/Clothing':   {'amber': 24, 'red': 48},
    'Toileting':           {'amber': 12, 'red': 24},
    'Grooming':            {'amber': 48, 'red': 96}
}

Max Gap Score:
  <= amber_threshold     → 0 points
  > amber & <= red       → 2 points  [AMBER]
  > red_threshold        → 3 points  [RED]
```

**Rationale**: Extended gaps may indicate missed care, staff shortages, or risk to resident dignity/health. Thresholds align with care plan expectations.

---

**C. Dependency Score** (Trend detection)
```python
# Assistance Levels (scored 0-2):
assistance_scores = {
    'Independent': 0,
    'Some Assistance': 1,
    'Full Assistance': 2
}

# Compare recent vs baseline (minimum 6 entries over 14 days):
recent_avg = avg(last_3_entries)
baseline_avg = avg(first_3_entries)

Dependency Change:
  recent_avg > baseline_avg + 0.5  → 2 points  [Increasing dependency]
  Otherwise                         → 0 points
```

**Rationale**: Unexpected increases in required assistance may signal health deterioration requiring care plan review.

---

### 1.2 Documentation Compliance Score (DCS)

**Purpose**: Measure recording quality independent of care delivery.

#### Formula:

```
DCS = (Actual_Entries / Expected_Entries) × 100

  90-100%   → GREEN  (Compliant)
  60-89%    → AMBER  (Gaps in recording)
  <60%      → RED    (Non-compliant)
```

#### Expected Entry Calculation:

```python
# Domain-specific expected frequencies (per day):
EXPECTED_FREQUENCIES = {
    'Washing/Bathing':   1.0,   # Once daily
    'Oral Care':         2.0,   # Twice daily
    'Dressing/Clothing': 1.0,   # Once daily
    'Toileting':         4.0,   # Four times daily
    'Grooming':          0.5    # Every other day
}

Expected_Entries = EXPECTED_FREQUENCIES[domain] × analysis_days
```

**Rationale**: Separate documentation compliance from care quality. Missing logs don't mean care wasn't delivered, but create audit risk and poor continuity.

---

### 1.3 Critical Design Principles

#### Fixed Thresholds (No Drift)
- Thresholds are **hardcoded constants**, not percentiles
- GREEN/AMBER/RED boundaries never adjust based on population performance
- Prevents "normalization of deviance" where poor performance becomes acceptable

#### Separation of Concerns
- **CRS**: Care delivery and resident wellbeing
- **DCS**: Record-keeping and audit compliance
- A resident can have GREEN care but RED documentation (or vice versa)

#### Explicit Over Implicit
- No hidden calculations or "black box" scoring
- Every point in a risk score must be explainable in an audit
- UI must show: "2 points for 3 refusals, 2 points for 18h gap = 4 = AMBER"

---

## 2. LAYERED DASHBOARD ARCHITECTURE

### 2.1 Layer 1 – Executive Grid

**Audience**: Care managers, CQC inspectors, executives  
**Purpose**: Instant overview of risk across all clients and domains

#### Visual Layout:

```
┌─────────────────┬──────────┬───────────┬───────────┬───────────┬──────────┐
│     Client      │ Washing  │ Oral Care │ Dressing  │ Toileting │ Grooming │
├─────────────────┼──────────┼───────────┼───────────┼───────────┼──────────┤
│ Care Home A     │ 🟢 (📄🟡)│ 🟢        │ 🟢        │ 🟡 (📄🟢)│ 🟢       │
│ Care Home B     │ 🔴       │ 🟡        │ 🟢        │ 🟢        │ 🟡       │
│ Home Care East  │ 🟢       │ 🟢        │ 🟡        │ 🟢        │ 🟢       │
└─────────────────┴──────────┴───────────┴───────────┴───────────┴──────────┘

Legend:
  Primary indicator: Care Risk Score (CRS)
  (📄) badge: Documentation risk if different from CRS
```

#### Interaction:
- Click any cell → drill to Layer 2 (Client View)
- Date range selector at top (7/14/30 days)
- Risk filter: Show only RED, AMBER+RED, or All

#### Aggregation Logic:

**Client-Level Score** = Worst resident score in that client-domain

```python
# For each (client, domain):
resident_scores = [
    calculate_crs(resident_id, domain_id, date_range)
    for resident_id in get_residents(client_id)
]

client_domain_score = max(resident_scores, key=lambda x: risk_rank(x))
# risk_rank: RED=3, AMBER=2, GREEN=1
```

**Why "worst wins"**: A single high-risk resident requires attention. Averaging would mask urgent issues.

#### Query Pattern:

```sql
-- Executive Grid (one query, pivot in code)
WITH resident_scores AS (
    SELECT 
        r.client_id,
        r.resident_id,
        r.resident_name,
        d.domain_name,
        -- CRS Components (calculated in subqueries)
        refusal_score + gap_score + dependency_score AS crs_total,
        CASE 
            WHEN refusal_score + gap_score + dependency_score >= 5 THEN 'RED'
            WHEN refusal_score + gap_score + dependency_score >= 2 THEN 'AMBER'
            ELSE 'GREEN'
        END AS crs_level,
        -- DCS
        (actual_entries * 100.0 / expected_entries) AS dcs_pct,
        CASE
            WHEN (actual_entries * 100.0 / expected_entries) < 60 THEN 'RED'
            WHEN (actual_entries * 100.0 / expected_entries) < 90 THEN 'AMBER'
            ELSE 'GREEN'
        END AS dcs_level
    FROM dim_resident r
    CROSS JOIN dim_domain d
    LEFT JOIN fact_resident_domain_score(:start_date, :end_date) scores
        ON r.resident_id = scores.resident_id 
        AND d.domain_id = scores.domain_id
    WHERE r.is_active = TRUE
)
SELECT 
    client_id,
    domain_name,
    -- Worst CRS in this client-domain
    MAX(CASE crs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END) AS crs_rank,
    -- Worst DCS in this client-domain
    MAX(CASE dcs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END) AS dcs_rank,
    -- Count of residents at each level
    COUNT(*) FILTER (WHERE crs_level = 'RED') AS red_count,
    COUNT(*) FILTER (WHERE crs_level = 'AMBER') AS amber_count,
    COUNT(*) FILTER (WHERE crs_level = 'GREEN') AS green_count
FROM resident_scores
GROUP BY client_id, domain_name
ORDER BY client_id, domain_name;
```

---

### 2.2 Layer 2 – Client View

**Audience**: Care home managers, clinical leads  
**Purpose**: Understand which residents drive risk and identify trends

#### Visual Layout:

```
### Care Home A - Last 7 Days

Residents at Risk:
┌────────────────┬──────────┬──────────┬────────────┬────────────────────┐
│ Resident       │ Washing  │ Toileting│ Grooming   │ Alerts             │
├────────────────┼──────────┼──────────┼────────────┼────────────────────┤
│ Alice Johnson  │ 🟢       │ 🟡       │ 🟢         │ Toileting: 18h gap │
│ Bob Smith      │ 🔴       │ 🟢       │ 🟡         │ 4 refusals washing │
│ Carol White    │ 🟢       │ 🟢       │ 🟢         │ —                  │
└────────────────┴──────────┴──────────┴────────────┴────────────────────┘

Trend Chart:
[Line graph showing RED/AMBER/GREEN counts over last 30 days]
```

#### Alerts Propagation Logic:

```python
# Generate resident-level alert summary
def generate_alerts(resident_id, date_range):
    alerts = []
    
    for domain in ADL_DOMAINS:
        crs, crs_reasons = calculate_crs(resident_id, domain, date_range)
        
        if crs in ['RED', 'AMBER']:
            # Extract most critical reason
            top_reason = max(crs_reasons, key=lambda x: x['points'])
            alerts.append({
                'domain': domain,
                'risk': crs,
                'reason': top_reason['description']
            })
    
    return alerts
```

**Alert Examples**:
- "4 refusals in Oral Care (RED)"
- "Gap of 27 hours in Toileting (AMBER)"
- "Dependency increasing in Dressing (AMBER)"

#### Default Metrics:
- Resident count by risk level
- Domain breakdown (which domains have most issues)
- Trend: Risk level counts over last 30 days
- Top 5 residents by CRS (sum across domains)

#### Drill-Down:
- Click resident row → Layer 3 (Resident Deep Dive)
- Date range selector (sync with Layer 1)
- Domain filter (show only selected domains)

---

### 2.3 Layer 3 – Resident Deep Dive

**Audience**: Care coordinators, reviewing specific cases  
**Purpose**: Audit-ready evidence for risk classification

#### Visual Layout:

```
### Alice Johnson - Toileting Analysis (Last 7 Days)

Overall Score: 🟡 AMBER (4 points)
├─ Refusals: 3 → 2 points
├─ Max Gap: 18 hours → 2 points
└─ Dependency: No change → 0 points

Documentation: 🟢 GREEN (6 entries / 4.0 expected = 100%)

───────────────────────────────────────────────────────────
Event Timeline (Most Recent First):

2026-02-16 14:30 | Some Assistance  | Normal toileting routine
2026-02-16 08:15 | Some Assistance  | Morning toileting
2026-02-15 20:45 | REFUSED          | Declined assistance
2026-02-15 14:00 | Full Assistance  | Required full support
2026-02-15 02:45 | [18 HOUR GAP]
2026-02-14 08:30 | Some Assistance  | Managed with prompting
───────────────────────────────────────────────────────────

Assistance Distribution:
  Independent:      0 (0%)
  Some Assistance:  3 (50%)
  Full Assistance:  1 (17%)
  Refused:          2 (33%)

Staff Context (Optional Feature):
  Most entries by: Sarah Jones (4), Michael Lee (2)
```

#### Scoring Consistency:

The UI **must** show the calculation explicitly:

```
How this score was calculated:
  ✓ 3 refusals recorded → 2 points (threshold: 2-3 refusals)
  ✓ Maximum gap 18h → 2 points (threshold: >12h for Toileting)
  ✓ No dependency trend → 0 points
  ─────────────────────────
  Total: 4 points = AMBER
```

#### Audit Defensibility:

**What makes this defensible:**
1. **Transparent Calculation**: Every point traces to a specific log entry or gap
2. **Fixed Thresholds**: Rules don't change based on performance
3. **Timestamp Evidence**: All times shown in UTC+0 or care home local time (documented)
4. **Separation**: Care risk vs documentation risk kept distinct
5. **Exportable**: Can generate PDF report with same information

**What auditors need to see:**
- "Why is this AMBER?" → Show calculation
- "Where are the refusals?" → Link to timestamped logs
- "What's the gap?" → Show timestamps of consecutive entries
- "Is this consistent?" → Show same logic applied to all residents

---

### 2.4 Query Optimization Strategy

#### Layer 1 (Executive Grid)
- **Pre-aggregated**: Calculate scores nightly, store in `fact_client_domain_scores`
- **Query time**: ~50ms for 50 clients × 5 domains
- **Refresh**: Real-time mode recalculates on demand (2-3 seconds)

#### Layer 2 (Client View)
- **Partial pre-aggregation**: Resident-domain scores cached daily
- **Query time**: ~200ms for client with 30 residents
- **Refresh**: Click "refresh" recalculates selected client

#### Layer 3 (Resident Deep Dive)
- **Always fresh**: Query fact table directly (indexed on resident_id + timestamp)
- **Query time**: ~50ms for single resident-domain
- **No caching**: Ensure most recent logs are visible

---

## 3. STAR SCHEMA DESIGN

### 3.1 Fact Table: `fact_adl_event`

**Purpose**: Immutable record of every ADL care event

```sql
CREATE TABLE fact_adl_event (
    event_id            BIGSERIAL PRIMARY KEY,
    
    -- Foreign Keys
    resident_id         INTEGER NOT NULL REFERENCES dim_resident(resident_id),
    domain_id           INTEGER NOT NULL REFERENCES dim_domain(domain_id),
    staff_id            INTEGER REFERENCES dim_staff(staff_id),
    date_id             INTEGER NOT NULL REFERENCES dim_date(date_id),
    
    -- Time
    event_timestamp     TIMESTAMP WITH TIME ZONE NOT NULL,
    logged_timestamp    TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Event Details
    assistance_level    VARCHAR(20),  -- 'Independent', 'Some Assistance', 'Full Assistance'
    is_refusal          BOOLEAN NOT NULL DEFAULT FALSE,
    event_title         VARCHAR(255),
    event_description   TEXT,
    
    -- Metadata
    source_system       VARCHAR(50),  -- e.g., 'PersonCentred', 'Excel Import'
    import_batch_id     VARCHAR(50),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_assistance CHECK (
        assistance_level IN ('Independent', 'Some Assistance', 'Full Assistance', 'Refused', 'Not Specified')
    )
);

-- Indexes for query performance
CREATE INDEX idx_fact_adl_resident_time 
    ON fact_adl_event(resident_id, event_timestamp DESC);

CREATE INDEX idx_fact_adl_domain_time 
    ON fact_adl_event(domain_id, event_timestamp DESC);

CREATE INDEX idx_fact_adl_client_coverage 
    ON fact_adl_event(resident_id, domain_id, date_id);

CREATE INDEX idx_fact_adl_refusals 
    ON fact_adl_event(resident_id, domain_id) 
    WHERE is_refusal = TRUE;
```

**Design Notes**:
- `event_timestamp`: When care occurred
- `logged_timestamp`: When it was recorded (for late entry detection)
- `date_id`: Foreign key enables fast date filtering without timestamp functions
- Partial index on refusals enables fast "refusal count" queries

---

### 3.2 Dimension: `dim_resident`

```sql
CREATE TABLE dim_resident (
    resident_id         SERIAL PRIMARY KEY,
    resident_name       VARCHAR(255) NOT NULL,
    client_id           INTEGER NOT NULL REFERENCES dim_client(client_id),
    
    -- Status
    admission_date      DATE NOT NULL,
    discharge_date      DATE,
    is_active           BOOLEAN GENERATED ALWAYS AS (discharge_date IS NULL) STORED,
    
    -- Demographics (for future analytics)
    date_of_birth       DATE,
    care_level          VARCHAR(50),
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_resident_client ON dim_resident(client_id);
CREATE INDEX idx_resident_active ON dim_resident(is_active) WHERE is_active = TRUE;
```

---

### 3.3 Dimension: `dim_client`

```sql
CREATE TABLE dim_client (
    client_id           SERIAL PRIMARY KEY,
    client_name         VARCHAR(255) NOT NULL UNIQUE,
    client_type         VARCHAR(50),  -- 'Care Home', 'Home Care', 'Domiciliary'
    
    -- Contact
    address             TEXT,
    primary_contact     VARCHAR(255),
    phone               VARCHAR(50),
    
    -- Status
    is_active           BOOLEAN DEFAULT TRUE,
    contract_start      DATE,
    contract_end        DATE,
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

### 3.4 Dimension: `dim_domain`

```sql
CREATE TABLE dim_domain (
    domain_id           SERIAL PRIMARY KEY,
    domain_name         VARCHAR(100) NOT NULL UNIQUE,
    domain_category     VARCHAR(50),  -- 'Personal Care', 'Nutrition', 'Mobility'
    
    -- Scoring Configuration (stored in DB for auditability)
    expected_per_day    DECIMAL(4,2) NOT NULL,
    gap_threshold_amber INTEGER NOT NULL,  -- hours
    gap_threshold_red   INTEGER NOT NULL,  -- hours
    
    -- Descriptive
    description         TEXT,
    cqc_alignment       TEXT,  -- Which CQC standard this relates to
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert standard ADL domains
INSERT INTO dim_domain (domain_name, domain_category, expected_per_day, gap_threshold_amber, gap_threshold_red, cqc_alignment)
VALUES
    ('Washing/Bathing', 'Personal Care', 1.0, 24, 48, 'Safe, Effective, Caring'),
    ('Oral Care', 'Personal Care', 2.0, 16, 24, 'Safe, Caring'),
    ('Dressing/Clothing', 'Personal Care', 1.0, 24, 48, 'Caring, Responsive'),
    ('Toileting', 'Personal Care', 4.0, 12, 24, 'Safe, Caring, Responsive'),
    ('Grooming', 'Personal Care', 0.5, 48, 96, 'Caring');
```

**Design Note**: Storing thresholds in the database creates an audit trail. Changes to thresholds are versioned.

---

### 3.5 Dimension: `dim_staff`

```sql
CREATE TABLE dim_staff (
    staff_id            SERIAL PRIMARY KEY,
    staff_name          VARCHAR(255) NOT NULL,
    client_id           INTEGER REFERENCES dim_client(client_id),
    
    -- Employment
    role                VARCHAR(100),
    hire_date           DATE,
    termination_date    DATE,
    is_active           BOOLEAN GENERATED ALWAYS AS (termination_date IS NULL) STORED,
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_staff_client ON dim_staff(client_id);
CREATE INDEX idx_staff_active ON dim_staff(is_active) WHERE is_active = TRUE;
```

---

### 3.6 Dimension: `dim_date`

**Purpose**: Enable fast date-range queries without timestamp arithmetic

```sql
CREATE TABLE dim_date (
    date_id             INTEGER PRIMARY KEY,  -- YYYYMMDD format (e.g., 20260216)
    full_date           DATE NOT NULL UNIQUE,
    
    -- Date Components
    year                SMALLINT NOT NULL,
    quarter             SMALLINT NOT NULL,
    month               SMALLINT NOT NULL,
    week                SMALLINT NOT NULL,
    day_of_month        SMALLINT NOT NULL,
    day_of_week         SMALLINT NOT NULL,  -- 0=Sunday
    day_name            VARCHAR(10),
    
    -- Business Logic
    is_weekend          BOOLEAN NOT NULL,
    is_holiday          BOOLEAN DEFAULT FALSE,
    
    -- Relative
    days_from_today     INTEGER
);

-- Populate for 10 years
-- (Run script to insert dates from 2020-01-01 to 2030-12-31)
```

**Usage**: Joins like `WHERE date_id BETWEEN 20260209 AND 20260216` are blazing fast.

---

### 3.7 Aggregate Table: `fact_resident_domain_score`

**Purpose**: Pre-calculated scores for dashboard performance

```sql
CREATE TABLE fact_resident_domain_score (
    score_id            BIGSERIAL PRIMARY KEY,
    
    -- Dimension Keys
    resident_id         INTEGER NOT NULL REFERENCES dim_resident(resident_id),
    domain_id           INTEGER NOT NULL REFERENCES dim_domain(domain_id),
    start_date_id       INTEGER NOT NULL REFERENCES dim_date(date_id),
    end_date_id         INTEGER NOT NULL REFERENCES dim_date(date_id),
    
    -- Care Risk Score (CRS)
    crs_level           VARCHAR(10) NOT NULL,  -- 'RED', 'AMBER', 'GREEN'
    crs_total           SMALLINT NOT NULL,
    crs_refusal_score   SMALLINT NOT NULL,
    crs_gap_score       SMALLINT NOT NULL,
    crs_dependency_score SMALLINT NOT NULL,
    
    -- CRS Supporting Data
    refusal_count       SMALLINT,
    max_gap_hours       DECIMAL(6,2),
    dependency_trend    VARCHAR(20),
    
    -- Documentation Compliance Score (DCS)
    dcs_level           VARCHAR(10) NOT NULL,
    dcs_percentage      DECIMAL(5,2),
    actual_entries      INTEGER,
    expected_entries    DECIMAL(6,2),
    
    -- Metadata
    calculated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT chk_crs_level CHECK (crs_level IN ('RED', 'AMBER', 'GREEN')),
    CONSTRAINT chk_dcs_level CHECK (dcs_level IN ('RED', 'AMBER', 'GREEN', 'N/A')),
    CONSTRAINT uq_score_period UNIQUE (resident_id, domain_id, start_date_id, end_date_id)
);

CREATE INDEX idx_score_client_lookup 
    ON fact_resident_domain_score(resident_id, domain_id, end_date_id);

CREATE INDEX idx_score_risk_filter 
    ON fact_resident_domain_score(crs_level, dcs_level);
```

**Refresh Strategy**:
- Nightly batch: Calculate for all residents, last 7/14/30 days
- On-demand: Recalculate for specific client on dashboard load (optional)

---

### 3.8 Schema Relationships

```
                    ┌─────────────┐
                    │ dim_client  │
                    └──────┬──────┘
                           │
                 ┌─────────┴─────────┐
                 │                   │
          ┌──────▼─────┐      ┌──────▼──────┐
          │dim_resident│      │  dim_staff  │
          └──────┬─────┘      └──────┬──────┘
                 │                   │
                 │    ┌─────────┐    │
                 ├────►dim_domain◄───┤
                 │    └─────────┘    │
                 │                   │
                 │    ┌─────────┐    │
                 └────►dim_date ◄────┘
                      └────┬────┘
                           │
                    ┌──────▼──────────┐
                    │ fact_adl_event  │◄──── Raw events (immutable)
                    └─────────────────┘
                           │
                    ┌──────▼──────────────────┐
                    │fact_resident_domain_score│◄──── Aggregates (refreshed)
                    └─────────────────────────┘
```

---

### 3.9 Query Strategy per Layer

#### Layer 1 - Executive Grid Query
```sql
-- Fast query using pre-aggregated scores
SELECT 
    c.client_name,
    d.domain_name,
    MAX(CASE s.crs_level 
        WHEN 'RED' THEN 3 
        WHEN 'AMBER' THEN 2 
        ELSE 1 
    END) AS crs_rank,
    MAX(CASE s.dcs_level 
        WHEN 'RED' THEN 3 
        WHEN 'AMBER' THEN 2 
        ELSE 1 
    END) AS dcs_rank,
    COUNT(*) FILTER (WHERE s.crs_level = 'RED') AS crs_red_count,
    COUNT(*) FILTER (WHERE s.crs_level = 'AMBER') AS crs_amber_count
FROM fact_resident_domain_score s
JOIN dim_resident r ON s.resident_id = r.resident_id
JOIN dim_client c ON r.client_id = c.client_id
JOIN dim_domain d ON s.domain_id = d.domain_id
WHERE s.end_date_id = :today_date_id
  AND s.start_date_id = :start_date_id
  AND r.is_active = TRUE
GROUP BY c.client_name, d.domain_name
ORDER BY c.client_name, d.domain_name;
```

**Expected Performance**: <100ms for 1000 residents

---

#### Layer 2 - Client Resident Breakdown
```sql
-- Residents with their worst domain risk
WITH resident_worst_risk AS (
    SELECT 
        r.resident_id,
        r.resident_name,
        MAX(CASE s.crs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END) AS worst_crs_rank
    FROM dim_resident r
    JOIN fact_resident_domain_score s ON r.resident_id = s.resident_id
    WHERE r.client_id = :client_id
      AND s.end_date_id = :end_date_id
      AND s.start_date_id = :start_date_id
    GROUP BY r.resident_id, r.resident_name
)
SELECT 
    rwr.resident_name,
    CASE rwr.worst_crs_rank WHEN 3 THEN 'RED' WHEN 2 THEN 'AMBER' ELSE 'GREEN' END AS overall_risk,
    -- Domain-specific scores (pivoted)
    MAX(CASE WHEN d.domain_name = 'Washing/Bathing' THEN s.crs_level END) AS washing_risk,
    MAX(CASE WHEN d.domain_name = 'Toileting' THEN s.crs_level END) AS toileting_risk,
    -- Alert summary
    STRING_AGG(
        CASE 
            WHEN s.crs_level IN ('RED', 'AMBER') 
            THEN d.domain_name || ': ' || 
                 COALESCE(s.refusal_count::TEXT || ' refusals', '') ||
                 COALESCE(s.max_gap_hours::TEXT || 'h gap', '')
        END, 
        '; '
    ) AS alerts
FROM resident_worst_risk rwr
JOIN fact_resident_domain_score s ON rwr.resident_id = s.resident_id
JOIN dim_domain d ON s.domain_id = d.domain_id
WHERE s.end_date_id = :end_date_id
  AND s.start_date_id = :start_date_id
GROUP BY rwr.resident_id, rwr.resident_name, rwr.worst_crs_rank
ORDER BY rwr.worst_crs_rank DESC, rwr.resident_name;
```

**Expected Performance**: <200ms for 100 residents

---

#### Layer 3 - Resident Deep Dive Timeline
```sql
-- Event timeline with gap detection
WITH events AS (
    SELECT 
        e.event_timestamp,
        e.assistance_level,
        e.is_refusal,
        e.event_title,
        e.event_description,
        LAG(e.event_timestamp) OVER (ORDER BY e.event_timestamp DESC) AS prev_timestamp,
        s.staff_name
    FROM fact_adl_event e
    LEFT JOIN dim_staff s ON e.staff_id = s.staff_id
    WHERE e.resident_id = :resident_id
      AND e.domain_id = :domain_id
      AND e.event_timestamp >= :start_timestamp
      AND e.event_timestamp <= :end_timestamp
    ORDER BY e.event_timestamp DESC
)
SELECT 
    event_timestamp,
    assistance_level,
    is_refusal,
    event_title,
    CASE 
        WHEN prev_timestamp IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (prev_timestamp - event_timestamp))/3600
    END AS gap_hours,
    staff_name
FROM events;
```

**Expected Performance**: <50ms per resident-domain

---

### 3.10 Indexing Strategy

**Critical Indexes** (create immediately):
1. `fact_adl_event(resident_id, event_timestamp DESC)` - Timeline queries
2. `fact_adl_event(domain_id, event_timestamp DESC)` - Domain rollups
3. `fact_resident_domain_score(resident_id, domain_id, end_date_id)` - Dashboard queries

**Conditional Indexes** (add if dataset grows >100k events):
4. `fact_adl_event(client_id, date_id)` - Client-level aggregations (requires denormalization)
5. Partial index on refusals (already included above)

**Avoid**:
- Indexes on `event_description` (too large, use FTS if needed)
- Indexes on calculated fields (materialize in aggregate table instead)

---

### 3.11 Scaling Considerations

#### Current Scale (< 100 residents)
- Single PostgreSQL instance
- Scores calculated on-demand acceptable
- No partitioning needed

#### Medium Scale (100-1000 residents, 2M events/year)
- **Partitioning**: Partition `fact_adl_event` by month (`PARTITION BY RANGE (event_timestamp)`)
- **Aggregate tables**: Mandatory, refresh nightly
- **Query timeout**: 5s for Layer 1, 10s for Layer 2

#### Large Scale (1000+ residents, 10M+ events/year)
- **Read replicas**: Serve dashboards from replica
- **Columnar storage**: Consider TimescaleDB or ClickHouse for fact table
- **Materialized views**: Layer 1 grid as materialized view, refresh every 5 minutes
- **Archive strategy**: Move events >2 years old to cold storage

---

## 4. IMPLEMENTATION CHECKLIST

### Phase 1: Database
- [ ] Create star schema tables
- [ ] Insert dimension data (domains, clients, residents)
- [ ] Create indexes
- [ ] Write ETL script to import logs.csv → fact_adl_event
- [ ] Test query performance on sample data

### Phase 2: Scoring Engine
- [ ] Implement `calculate_crs()` function
- [ ] Implement `calculate_dcs()` function
- [ ] Create nightly batch job to populate `fact_resident_domain_score`
- [ ] Write unit tests for scoring formulas
- [ ] Validate scores against manual audit sample

### Phase 3: Dashboard Layer 1 (Executive Grid)
- [ ] Build grid query
- [ ] Implement traffic light UI
- [ ] Add date range filter
- [ ] Add drill-down to Layer 2
- [ ] Test with 50+ clients

### Phase 4: Dashboard Layer 2 (Client View)
- [ ] Build resident breakdown query
- [ ] Implement alert propagation
- [ ] Add trend chart (30-day history)
- [ ] Add drill-down to Layer 3

### Phase 5: Dashboard Layer 3 (Resident Deep Dive)
- [ ] Build event timeline query
- [ ] Display score calculation explicitly
- [ ] Show assistance distribution chart
- [ ] Add export to PDF function

### Phase 6: Audit & Documentation
- [ ] Generate sample audit report
- [ ] Document threshold rationale
- [ ] Create CQC alignment mapping
- [ ] Write SQL query examples for common audits

---

## 5. AUDIT DEFENSIBILITY CHECKLIST

When CQC or auditors ask questions, you must be able to demonstrate:

✅ **Transparent Calculations**
- "Show me why this resident is RED" → Score breakdown with formula
- "What thresholds are used?" → Fixed values in `dim_domain` table with change log

✅ **Data Provenance**
- "Where did this score come from?" → Drill to raw events in `fact_adl_event`
- "When was this calculated?" → `calculated_at` timestamp in score table

✅ **Consistency**
- "Is this applied fairly?" → Same logic for all residents (show SQL query)
- "Has this changed over time?" → Version control on scoring functions

✅ **Evidence**
- "Prove there was a 4-day gap" → Show consecutive event timestamps
- "How many refusals?" → Count `WHERE is_refusal = TRUE`

✅ **Separation of Concerns**
- "Is this a care issue or documentation issue?" → Show CRS and DCS separately

---

## 6. NEXT STEPS

1. **Review this design** with care managers and clinical leads
2. **Validate thresholds** against care plans and CQC standards
3. **Build database** using schema definitions above
4. **Implement scoring** in Python (separate module from dashboard)
5. **Build dashboard layers** incrementally (1 → 2 → 3)
6. **Test with auditors** before going live

---

**Document Version**: 1.0  
**Last Updated**: February 16, 2026  
**Author**: System Design Specification  
**Status**: Ready for Implementation
