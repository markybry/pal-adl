BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'care_app_ro') THEN
        CREATE ROLE care_app_ro LOGIN PASSWORD 'On8gc#bc39nE^W';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'care_app_rw') THEN
        CREATE ROLE care_app_rw LOGIN PASSWORD 'OFw3n@^8EC6lM5';
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO care_app_ro, care_app_rw',
        current_database()
    );
END
$$;
GRANT USAGE ON SCHEMA public TO care_app_ro, care_app_rw;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO care_app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO care_app_ro;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO care_app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO care_app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO care_app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO care_app_rw;

COMMIT;
