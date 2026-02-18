-- Care Analytics System - Company Seed Data
-- PostgreSQL 14+
-- Created: February 18, 2026
--
-- Instructions:
-- 1. Modify the company information below for your environment
-- 2. Run this AFTER schema.sql has been executed
-- 3. Create separate versions for dev/staging/production as needed
-- 4. Run with: psql -d your_database -f seed_company.sql

-- =============================================================================
-- COMPANY/CLIENT DATA
-- =============================================================================

-- Insert your care organization(s)
INSERT INTO dim_client (client_name, client_type, address, primary_contact, phone, is_active, contract_start, contract_end)
VALUES
    ('Example Care Home', 'Care Home', '123 Main Street, Cityville, ST 12345', 'Jane Manager', '555-0100', TRUE, '2024-01-01', NULL),
    ('Sample Home Care Agency', 'Home Care', '456 Oak Avenue, Townsburg, ST 67890', 'John Administrator', '555-0200', TRUE, '2025-06-01', NULL);

-- Note: Adjust client_type to match your business:
-- Options: 'Care Home', 'Home Care', 'Domiciliary', 'Nursing Home', 'Assisted Living'

-- =============================================================================
-- OPTIONAL: SAMPLE RESIDENTS (for testing/demo purposes)
-- =============================================================================

-- Uncomment and modify if you want to seed initial test residents
/*
INSERT INTO dim_resident (resident_name, client_id, admission_date, date_of_birth, care_level)
VALUES
    ('Test Resident A', 1, '2024-01-15', '1945-03-20', 'Standard'),
    ('Test Resident B', 1, '2024-02-01', '1938-07-14', 'Enhanced'),
    ('Test Resident C', 2, '2025-06-15', '1942-11-08', 'Standard');
*/

-- =============================================================================
-- OPTIONAL: SAMPLE STAFF (for testing/demo purposes)
-- =============================================================================

-- Uncomment and modify if you want to seed initial test staff
/*
INSERT INTO dim_staff (staff_name, client_id, role, hire_date)
VALUES
    ('Care Worker 1', 1, 'Care Assistant', '2024-01-01'),
    ('Care Worker 2', 1, 'Senior Carer', '2024-01-01'),
    ('Care Worker 3', 2, 'Care Assistant', '2025-06-01');
*/

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Verify data was inserted correctly
SELECT 'Companies Loaded:' AS status, COUNT(*) AS count FROM dim_client;
SELECT client_id, client_name, client_type, is_active FROM dim_client;

-- Uncomment if you loaded residents/staff
-- SELECT 'Residents Loaded:' AS status, COUNT(*) AS count FROM dim_resident;
-- SELECT 'Staff Loaded:' AS status, COUNT(*) AS count FROM dim_staff;
