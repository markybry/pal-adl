-- Migration 002: Make CSV imports idempotent via event dedupe index
-- Safe to run once after schema.sql has already been applied.

BEGIN;

-- Remove duplicate events before creating the unique index
WITH ranked AS (
    SELECT
        event_id,
        ROW_NUMBER() OVER (
            PARTITION BY
                resident_id,
                domain_id,
                event_timestamp,
                COALESCE(event_title, ''),
                COALESCE(event_description, ''),
                COALESCE(assistance_level, ''),
                is_refusal,
                COALESCE(staff_id, -1),
                COALESCE(source_system, '')
            ORDER BY event_id
        ) AS rn
    FROM fact_adl_event
)
DELETE FROM fact_adl_event
WHERE event_id IN (
    SELECT event_id
    FROM ranked
    WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_adl_event_dedupe
    ON fact_adl_event (
        resident_id,
        domain_id,
        event_timestamp,
        COALESCE(event_title, ''),
        COALESCE(event_description, ''),
        COALESCE(assistance_level, ''),
        is_refusal,
        COALESCE(staff_id, -1),
        COALESCE(source_system, '')
    );

COMMIT;
