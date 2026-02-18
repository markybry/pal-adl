-- Migration: Remove Staff-Client Assignment
-- Date: February 18, 2026
-- Description: Drop bridge_staff_client table and client_id from dim_staff
-- Rationale: Staff work locations are derived from fact_adl_event, not pre-assigned

-- =============================================================================
-- STEP 1: Drop bridge table if it exists
-- =============================================================================

DROP TABLE IF EXISTS bridge_staff_client CASCADE;

-- =============================================================================
-- STEP 2: Remove client_id from dim_staff if it exists
-- =============================================================================

-- Drop the index first (if it exists)
DROP INDEX IF EXISTS idx_staff_client;

-- Drop the column (if it exists)
ALTER TABLE dim_staff DROP COLUMN IF EXISTS client_id;

-- =============================================================================
-- STEP 3: Update comments to reflect design decision
-- =============================================================================

COMMENT ON TABLE dim_staff IS 'Care staff members - client assignments derived from fact_adl_event';
COMMENT ON COLUMN dim_staff.staff_id IS 'No client_id: staff work locations are determined by actual care events in fact_adl_event, not pre-assigned';

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Check that the changes were applied
SELECT 'dim_staff columns:' AS check_type;
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'dim_staff' 
ORDER BY ordinal_position;

SELECT 'bridge_staff_client exists:' AS check_type;
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'bridge_staff_client'
) AS table_exists;

-- If you had existing data in bridge_staff_client, you can verify staff 
-- work locations are still discoverable from fact_adl_event:
/*
SELECT 
    s.staff_name,
    s.role,
    c.client_name,
    COUNT(*) as events_logged
FROM dim_staff s
JOIN fact_adl_event e ON s.staff_id = e.staff_id
JOIN dim_resident r ON e.resident_id = r.resident_id
JOIN dim_client c ON r.client_id = c.client_id
GROUP BY s.staff_name, s.role, c.client_name
ORDER BY s.staff_name;
*/
