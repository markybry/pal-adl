-- Care Analytics System - Star Schema DDL
-- PostgreSQL 14+
-- Created: February 16, 2026

-- =============================================================================
-- DIMENSION TABLES
-- =============================================================================

-- Client Dimension
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

COMMENT ON TABLE dim_client IS 'Care organizations (homes, agencies) using the system';

-- Resident Dimension
CREATE TABLE dim_resident (
    resident_id         SERIAL PRIMARY KEY,
    resident_name       VARCHAR(255) NOT NULL,
    client_id           INTEGER NOT NULL REFERENCES dim_client(client_id),
    
    -- Status
    admission_date      DATE NOT NULL,
    discharge_date      DATE,
    is_active           BOOLEAN GENERATED ALWAYS AS (discharge_date IS NULL) STORED,
    
    -- Demographics
    date_of_birth       DATE,
    care_level          VARCHAR(50),
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_resident_client ON dim_resident(client_id);
CREATE INDEX idx_resident_active ON dim_resident(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE dim_resident IS 'Individuals receiving care';

-- Domain Dimension
CREATE TABLE dim_domain (
    domain_id           SERIAL PRIMARY KEY,
    domain_name         VARCHAR(100) NOT NULL UNIQUE,
    domain_category     VARCHAR(50),  -- 'Personal Care', 'Nutrition', 'Mobility'
    
    -- Scoring Configuration
    expected_per_day    DECIMAL(4,2) NOT NULL,
    gap_threshold_amber INTEGER NOT NULL,  -- hours
    gap_threshold_red   INTEGER NOT NULL,  -- hours
    
    -- Descriptive
    description         TEXT,
    cqc_alignment       TEXT,
    
    -- Audit
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE dim_domain IS 'ADL domains with scoring configuration';
COMMENT ON COLUMN dim_domain.expected_per_day IS 'Expected care events per day (e.g., 2.0 for twice daily)';
COMMENT ON COLUMN dim_domain.gap_threshold_amber IS 'Maximum hours between events before AMBER alert';
COMMENT ON COLUMN dim_domain.gap_threshold_red IS 'Maximum hours between events before RED alert';

-- Staff Dimension
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

COMMENT ON TABLE dim_staff IS 'Care staff members';

-- Date Dimension
CREATE TABLE dim_date (
    date_id             INTEGER PRIMARY KEY,  -- YYYYMMDD format
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
    is_holiday          BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE dim_date IS 'Date dimension for fast date-range queries';
COMMENT ON COLUMN dim_date.date_id IS 'Integer YYYYMMDD format for efficient joins';

-- =============================================================================
-- FACT TABLES
-- =============================================================================

-- ADL Event Fact Table
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
    assistance_level    VARCHAR(20),
    is_refusal          BOOLEAN NOT NULL DEFAULT FALSE,
    event_title         VARCHAR(255),
    event_description   TEXT,
    
    -- Metadata
    source_system       VARCHAR(50),
    import_batch_id     VARCHAR(50),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_assistance CHECK (
        assistance_level IN ('Independent', 'Some Assistance', 'Full Assistance', 'Refused', 'Not Specified')
    )
);

-- Critical Indexes for Performance
CREATE INDEX idx_fact_adl_resident_time 
    ON fact_adl_event(resident_id, event_timestamp DESC);

CREATE INDEX idx_fact_adl_domain_time 
    ON fact_adl_event(domain_id, event_timestamp DESC);

CREATE INDEX idx_fact_adl_client_coverage 
    ON fact_adl_event(resident_id, domain_id, date_id);

CREATE INDEX idx_fact_adl_refusals 
    ON fact_adl_event(resident_id, domain_id) 
    WHERE is_refusal = TRUE;

COMMENT ON TABLE fact_adl_event IS 'Immutable record of every ADL care event';
COMMENT ON COLUMN fact_adl_event.event_timestamp IS 'When care was delivered';
COMMENT ON COLUMN fact_adl_event.logged_timestamp IS 'When event was recorded (for late entry detection)';

-- Resident-Domain Score Aggregate Table
CREATE TABLE fact_resident_domain_score (
    score_id            BIGSERIAL PRIMARY KEY,
    
    -- Dimension Keys
    resident_id         INTEGER NOT NULL REFERENCES dim_resident(resident_id),
    domain_id           INTEGER NOT NULL REFERENCES dim_domain(domain_id),
    start_date_id       INTEGER NOT NULL REFERENCES dim_date(date_id),
    end_date_id         INTEGER NOT NULL REFERENCES dim_date(date_id),
    
    -- Care Risk Score (CRS)
    crs_level           VARCHAR(10) NOT NULL,
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

COMMENT ON TABLE fact_resident_domain_score IS 'Pre-calculated risk scores for dashboard performance';

-- =============================================================================
-- REFERENCE DATA
-- =============================================================================

-- Insert Standard ADL Domains
INSERT INTO dim_domain (domain_name, domain_category, expected_per_day, gap_threshold_amber, gap_threshold_red, cqc_alignment, description)
VALUES
    ('Washing/Bathing', 'Personal Care', 1.0, 24, 48, 'Safe, Effective, Caring', 
     'Daily washing and bathing activities'),
    ('Oral Care', 'Personal Care', 2.0, 16, 24, 'Safe, Caring', 
     'Teeth brushing and oral hygiene (typically morning and evening)'),
    ('Dressing/Clothing', 'Personal Care', 1.0, 24, 48, 'Caring, Responsive', 
     'Assistance with getting dressed and undressed'),
    ('Toileting', 'Personal Care', 4.0, 12, 24, 'Safe, Caring, Responsive', 
     'Assistance with toileting needs (minimum 4x daily expected)'),
    ('Grooming', 'Personal Care', 0.5, 48, 96, 'Caring', 
     'Hair care, shaving, and general grooming (every other day)');

-- =============================================================================
-- UTILITY FUNCTIONS
-- =============================================================================

-- Function to populate date dimension
CREATE OR REPLACE FUNCTION populate_dim_date(start_date DATE, end_date DATE)
RETURNS INTEGER AS $$
DECLARE
    loop_date DATE := start_date;
    rows_inserted INTEGER := 0;
BEGIN
    WHILE loop_date <= end_date LOOP
        INSERT INTO dim_date (
            date_id,
            full_date,
            year,
            quarter,
            month,
            week,
            day_of_month,
            day_of_week,
            day_name,
            is_weekend
        ) VALUES (
            TO_CHAR(loop_date, 'YYYYMMDD')::INTEGER,
            loop_date,
            EXTRACT(YEAR FROM loop_date)::SMALLINT,
            EXTRACT(QUARTER FROM loop_date)::SMALLINT,
            EXTRACT(MONTH FROM loop_date)::SMALLINT,
            EXTRACT(WEEK FROM loop_date)::SMALLINT,
            EXTRACT(DAY FROM loop_date)::SMALLINT,
            EXTRACT(DOW FROM loop_date)::SMALLINT,
            TO_CHAR(loop_date, 'Day'),
            CASE WHEN EXTRACT(DOW FROM loop_date) IN (0, 6) THEN TRUE ELSE FALSE END
        )
        ON CONFLICT (full_date) DO NOTHING;
        
        rows_inserted := rows_inserted + 1;
        loop_date := loop_date + INTERVAL '1 day';
    END LOOP;
    
    RETURN rows_inserted;
END;
$$ LANGUAGE plpgsql;

-- Populate date dimension for 10 years (2020-2030)
SELECT populate_dim_date('2020-01-01'::DATE, '2030-12-31'::DATE);

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- View: Active residents with client info
CREATE OR REPLACE VIEW v_active_residents AS
SELECT 
    r.resident_id,
    r.resident_name,
    c.client_id,
    c.client_name,
    c.client_type,
    r.admission_date,
    r.care_level
FROM dim_resident r
JOIN dim_client c ON r.client_id = c.client_id
WHERE r.is_active = TRUE
  AND c.is_active = TRUE;

COMMENT ON VIEW v_active_residents IS 'Active residents with their client organization';

-- View: Latest 7-day scores by resident
CREATE OR REPLACE VIEW v_latest_scores AS
WITH latest_period AS (
    SELECT DISTINCT end_date_id
    FROM fact_resident_domain_score
    ORDER BY end_date_id DESC
    LIMIT 1
)
SELECT 
    s.*,
    r.resident_name,
    c.client_name,
    d.domain_name
FROM fact_resident_domain_score s
JOIN dim_resident r ON s.resident_id = r.resident_id
JOIN dim_client c ON r.client_id = c.client_id
JOIN dim_domain d ON s.domain_id = d.domain_id
WHERE s.end_date_id = (SELECT end_date_id FROM latest_period);

COMMENT ON VIEW v_latest_scores IS 'Most recent calculated scores across all residents';

-- =============================================================================
-- SAMPLE QUERIES
-- =============================================================================

-- Executive Grid Query (Layer 1)
/*
WITH resident_scores AS (
    SELECT 
        c.client_id,
        c.client_name,
        d.domain_name,
        s.crs_level,
        s.dcs_level,
        CASE s.crs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END AS crs_rank,
        CASE s.dcs_level WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 ELSE 1 END AS dcs_rank
    FROM fact_resident_domain_score s
    JOIN dim_resident r ON s.resident_id = r.resident_id
    JOIN dim_client c ON r.client_id = c.client_id
    JOIN dim_domain d ON s.domain_id = d.domain_id
    WHERE s.end_date_id = 20260216  -- Today
      AND s.start_date_id = 20260209  -- 7 days ago
      AND r.is_active = TRUE
)
SELECT 
    client_name,
    domain_name,
    MAX(crs_rank) AS primary_risk_rank,
    MAX(dcs_rank) AS doc_risk_rank,
    COUNT(*) FILTER (WHERE crs_level = 'RED') AS red_count,
    COUNT(*) FILTER (WHERE crs_level = 'AMBER') AS amber_count,
    COUNT(*) FILTER (WHERE crs_level = 'GREEN') AS green_count
FROM resident_scores
GROUP BY client_name, domain_name
ORDER BY client_name, domain_name;
*/

-- Resident Timeline Query (Layer 3)
/*
SELECT 
    e.event_timestamp,
    e.assistance_level,
    e.is_refusal,
    e.event_title,
    e.event_description,
    s.staff_name,
    EXTRACT(EPOCH FROM (
        LAG(e.event_timestamp) OVER (ORDER BY e.event_timestamp DESC) - e.event_timestamp
    ))/3600 AS gap_hours
FROM fact_adl_event e
LEFT JOIN dim_staff s ON e.staff_id = s.staff_id
WHERE e.resident_id = :resident_id
  AND e.domain_id = :domain_id
  AND e.event_timestamp >= NOW() - INTERVAL '7 days'
ORDER BY e.event_timestamp DESC;
*/

-- =============================================================================
-- MAINTENANCE
-- =============================================================================

-- Update table statistics (run weekly)
-- ANALYZE fact_adl_event;
-- ANALYZE fact_resident_domain_score;

-- Check index usage
-- SELECT schemaname, tablename, indexname, idx_scan
-- FROM pg_stat_user_indexes
-- WHERE tablename LIKE 'fact_%'
-- ORDER BY idx_scan;

COMMENT ON DATABASE care_analytics IS 'Care Analytics System - Risk Intelligence and Audit Layer';
