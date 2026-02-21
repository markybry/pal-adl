# Scripts

Utility scripts for the Care Analytics System.

## Copy/Paste Commands (Bash)

Use these exactly as-is in terminal:

```bash
psql "host=<your_neon_host> port=5432 dbname=neondb user=<root_user> sslmode=require" -f database/migrations/003_create_app_roles.sql
ENV_FILE=.env.staging python scripts/run_sql.py database/migrations/003_create_app_roles.sql
python scripts/import_csv_to_db.py "/c/Users/marky/Downloads/LMC export 19-02-2026 19_53_14/logs.csv" --client "Primary Access Ltd"
python scripts/backfill_scores.py --client "Primary Access Ltd"
streamlit run src/dashboard_v2.py
```

Do not include markdown link syntax like `[name](url)` in terminal commands.

## run_sql.py

Runs a `.sql` file against the configured PostgreSQL database.

### Usage

Default `.env`:

```bash
python scripts/run_sql.py database/migrations/003_create_app_roles.sql
```

Staging `.env` file:

```bash
ENV_FILE=.env.staging python scripts/run_sql.py database/migrations/003_create_app_roles.sql
```

Override connection values from CLI:

```bash
ENV_FILE=.env.staging python scripts/run_sql.py database/migrations/003_create_app_roles.sql --user neondb_owner --sslmode require
```

## backfill_scores.py

Backfills daily score snapshots over a date range using the same scoring logic as
`calculate_scores.py`.

### Usage

Default: backfill last 30 days ending today, for 7/14/30-day windows:

```bash
python scripts/backfill_scores.py
```

Custom range:

```bash
python scripts/backfill_scores.py --start-date 2026-01-20 --end-date 2026-02-19
```

Custom windows and single client:

```bash
python scripts/backfill_scores.py --periods 7,14,30 --client "Primary Access Ltd"
```

This is idempotent for the same `(resident, domain, start_date_id, end_date_id)`
because scores are upserted.

## import_csv_to_db.py

ETL script to import care log CSV files into PostgreSQL.

### Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure database connection**

Create a `.env` file in the project root:
```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual credentials
```

Your `.env` file should contain:
```env
DB_NAME=care_analytics
DB_USER=postgres
DB_PASSWORD=your_actual_password
DB_HOST=localhost
DB_PORT=5432
DB_SSLMODE=prefer
```

For Neon:
```env
DB_NAME=neondb
DB_USER=care_app_rw
DB_PASSWORD=your_app_password
DB_HOST=your-neon-host.neon.tech
DB_PORT=5432
DB_SSLMODE=require
```

**3. Enable idempotent imports (one-time migration)**
```bash
psql -U postgres -d care_analytics -f database/migrations/002_add_event_dedupe_index.sql
```

This adds the dedupe index used by `ON CONFLICT DO NOTHING` so re-running the same CSV does not create duplicate events.

### Usage

**With .env file** (recommended)
```bash
python scripts/import_csv_to_db.py logs.csv
```

**With command line password**
```bash
python scripts/import_csv_to_db.py logs.csv --password YOUR_PASSWORD
```

**With environment variable**
```bash
# Windows
set DB_PASSWORD=YOUR_PASSWORD
python scripts/import_csv_to_db.py logs.csv

# Linux/Mac
export DB_PASSWORD=YOUR_PASSWORD
python scripts/import_csv_to_db.py logs.csv
```

### Examples

**Basic import with .env file**
```bash
python scripts/import_csv_to_db.py logs.csv --client "Sunshine Care Home"
```

**Test with first 100 rows**
```bash
python scripts/import_csv_to_db.py logs.csv --client "Sunshine Care Home" --limit 100
```

**Import with command line password**
```bash
python scripts/import_csv_to_db.py "C:\path\to\logs.csv" \
    --password YOUR_PASSWORD \
    --client "Sunshine Care Home" \
    --limit 100
```

**Note**: The `.env` file approach is recommended for security. Never commit `.env` to version control (it's already in `.gitignore`).

### Options

- `csv_file` - Path to CSV file to import (required)
- `--password`, `-p` - Database password
- `--user` - Database user (default: postgres)
- `--dbname` - Database name (default: care_analytics)
- `--host` - Database host (default: localhost)
- `--port` - Database port (default: 5432)
- `--sslmode` - Database SSL mode (`prefer`, `require`, `disable`)
- `--client NAME` - Client/organization name (default: "Default Care Home")
- `--limit N` - Import only first N rows (useful for testing)
- `--date-format FORMAT` - Date format in CSV (default: `%d/%m/%Y %H:%M:%S`)

### CSV Requirements

Required columns:
- `Time logged` - Timestamp of event
- `Resident` - Resident name
- `Item` - Domain/ADL type
- `Title` - Event title
- `Description` - Event description

Optional columns:
- `Staff` - Staff member name

### Domain Mapping

The script imports **Personal Care ADL domains only**:
- **Washing/Bathing** - Getting Washed, Washing, Bathing, Bath, Wash
- **Oral Care** - Oral Hygiene, Teeth Brushing, Dental, Teeth, Oral
- **Dressing/Clothing** - Getting Dressed, Dressing, Dress, Clothing
- **Toileting** - Toilet, Continence, Pad Change
 - **Toileting** - Toilet, Continence, Pad Change, Pad check
- **Grooming** - Shaving, Hair Care, Hair, Nails

**Domains not imported** (will be skipped):
- Meal, Hydration, Activity, Medication, etc.
- These are not part of the Personal Care ADL scoring system

**To track additional domains**: Add them to `dim_domain` table in the database first, then update `DOMAIN_MAP` in the script.

The script automatically handles:
- ✅ Common naming variations (e.g., "Getting Washed" → "Washing/Bathing")
- ✅ Missing/null domain values (skipped silently)
- ✅ Summary report of skipped domains at the end

### Features

- ✅ Automatic client/resident/staff creation
- ✅ Date dimension population
- ✅ Assistance level parsing
- ✅ Refusal detection
- ✅ Error handling and reporting
- ✅ Progress updates
- ✅ Batch commits (every 100 rows)

### Example Output

```
============================================================
Care Analytics - CSV Import Tool
============================================================
✓ Loaded 5000 rows from logs.csv

🔌 Connecting to database: care_analytics as postgres
✓ Connected

📋 Setting up client: Sunshine Care Home
✓ Found 5 domains in database
✓ Found 45 unique residents in CSV
✓ Created/verified 45 residents

📥 Importing all 5,000 events...
  ✓ Imported 100 events...
  ✓ Imported 200 events...
  ...
  ✓ Imported 4800 events...

============================================================
✅ Import complete!
   Imported: 4,850 events
   Skipped:  150 events
   Duplicates (already present): 0 events
   Errors:   0 events

⚠️  Skipped domains (not in Personal Care ADLs):
   - Meal: 85 events
   - Hydration: 45 events
   - Activity: 20 events

   💡 Tip: Only Personal Care ADL domains are imported:
      Washing/Bathing, Oral Care, Dressing/Clothing, Toileting, Grooming
============================================================

✓ Database connection closed
```
