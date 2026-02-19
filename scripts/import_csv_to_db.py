"""
ETL Script: Import Care Logs from CSV to PostgreSQL
Usage: python scripts/import_csv_to_db.py <csv_file> [--limit N]
"""

import sys
import argparse
import os
import pandas as pd
import psycopg2
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring_engine import parse_assistance_level, is_refusal


# =============================================================================
# CONFIGURATION
# =============================================================================

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'care_analytics'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),  # Default: 'postgres' - CHANGE THIS!
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432'))
}

# NOTE: Set environment variable DB_PASSWORD or edit the default above
# Windows: set DB_PASSWORD=your_password
# Linux/Mac: export DB_PASSWORD=your_password

# Map CSV domain names to database domain names
# The database contains 5 standard Personal Care ADL domains:
# - Washing/Bathing, Oral Care, Dressing/Clothing, Toileting, Grooming
DOMAIN_MAP = {
    # Washing/Bathing variants
    'Getting Washed': 'Washing/Bathing',
    'Washing': 'Washing/Bathing',
    'Bathing': 'Washing/Bathing',
    'Wash': 'Washing/Bathing',
    'Bath': 'Washing/Bathing',
    'Washing/Bathing': 'Washing/Bathing',
    
    # Oral Care variants
    'Oral Hygiene': 'Oral Care',
    'Oral': 'Oral Care',
    'Teeth': 'Oral Care',
    'Teeth Brushing': 'Oral Care',
    'Dental': 'Oral Care',
    'Oral Care': 'Oral Care',
    
    # Dressing variants
    'Getting Dressed': 'Dressing/Clothing',
    'Dressing': 'Dressing/Clothing',
    'Dress': 'Dressing/Clothing',
    'Clothing': 'Dressing/Clothing',
    'Dressing/Clothing': 'Dressing/Clothing',
    
    # Toileting variants
    'Toileting': 'Toileting',
    'Toilet': 'Toileting',
    'Continence': 'Toileting',
    'Pad Change': 'Toileting',
    'Pad check': 'Toileting',
    
    # Grooming variants
    'Shaving': 'Grooming',
    'Hair Care': 'Grooming',
    'Hair': 'Grooming',
    'Grooming': 'Grooming',
    'Nails': 'Grooming'
}

# NOTE: Domains not in the map (like 'Meal', 'Hydration', 'Activity', etc.) 
# are not part of the standard Personal Care ADL domains and will be skipped.
# To track these, add them to dim_domain in the database first.

# Expected CSV columns
EXPECTED_COLUMNS = ['Time logged', 'Resident', 'Item', 'Title', 'Description']


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def connect_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print(f"\n💡 Solutions:")
        print(f"   1. Pass password via command line:")
        print(f"      python scripts/import_csv_to_db.py file.csv --password YOUR_PASSWORD")
        print(f"\n   2. Set environment variable:")
        print(f"      Windows: set DB_PASSWORD=YOUR_PASSWORD")
        print(f"      Linux/Mac: export DB_PASSWORD=YOUR_PASSWORD")
        print(f"\n   3. Edit the default in scripts/import_csv_to_db.py:")
        print(f"      'password': os.getenv('DB_PASSWORD', 'YOUR_PASSWORD')")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


def load_csv(filepath, date_format='%d/%m/%Y %H:%M:%S'):
    """Load and validate CSV file"""
    try:
        df = pd.read_csv(filepath)
        
        # Check required columns
        missing = set(EXPECTED_COLUMNS) - set(df.columns)
        if missing:
            print(f"❌ Missing CSV columns: {missing}")
            print(f"   Found columns: {list(df.columns)}")
            sys.exit(1)
        
        # Parse datetime
        df['Time logged'] = pd.to_datetime(df['Time logged'], format=date_format)
        
        print(f"✓ Loaded {len(df)} rows from {filepath}")
        return df
        
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        sys.exit(1)


def get_or_create_client(cursor, client_name, client_type='Care Home'):
    """Get existing client or create new one"""
    cursor.execute("""
        SELECT client_id FROM dim_client WHERE client_name = %s
    """, (client_name,))
    
    result = cursor.fetchone()
    if result:
        return result[0]
    
    cursor.execute("""
        INSERT INTO dim_client (client_name, client_type, is_active)
        VALUES (%s, %s, TRUE)
        RETURNING client_id
    """, (client_name, client_type))
    
    return cursor.fetchone()[0]


def get_or_create_resident(cursor, resident_name, client_id, admission_date=None):
    """Get existing resident or create new one"""
    cursor.execute("""
        SELECT resident_id FROM dim_resident 
        WHERE resident_name = %s AND client_id = %s
    """, (resident_name, client_id))
    
    result = cursor.fetchone()
    if result:
        return result[0]
    
    if admission_date is None:
        admission_date = datetime.now().date()
    
    cursor.execute("""
        INSERT INTO dim_resident (resident_name, client_id, admission_date)
        VALUES (%s, %s, %s)
        RETURNING resident_id
    """, (resident_name, client_id, admission_date))
    
    return cursor.fetchone()[0]


def get_or_create_staff(cursor, staff_name, role='Care Assistant'):
    """Get existing staff or create new one"""
    if not staff_name or pd.isna(staff_name):
        return None
    
    cursor.execute("""
        SELECT staff_id FROM dim_staff WHERE staff_name = %s
    """, (staff_name,))
    
    result = cursor.fetchone()
    if result:
        return result[0]
    
    cursor.execute("""
        INSERT INTO dim_staff (staff_name, role, hire_date)
        VALUES (%s, %s, CURRENT_DATE)
        RETURNING staff_id
    """, (staff_name, role))
    
    return cursor.fetchone()[0]


def ensure_date_dimension(cursor, event_date):
    """Ensure date exists in dim_date"""
    date_id = int(event_date.strftime('%Y%m%d'))
    
    cursor.execute("SELECT 1 FROM dim_date WHERE date_id = %s", (date_id,))
    if cursor.fetchone():
        return date_id
    
    # Insert date
    cursor.execute("""
        INSERT INTO dim_date (
            date_id, full_date, year, quarter, month, week,
            day_of_month, day_of_week, day_name, is_weekend
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (date_id) DO NOTHING
    """, (
        date_id,
        event_date,
        event_date.year,
        (event_date.month - 1) // 3 + 1,
        event_date.month,
        event_date.isocalendar()[1],
        event_date.day,
        event_date.weekday(),
        event_date.strftime('%A'),
        event_date.weekday() >= 5
    ))
    
    return date_id


def verify_idempotency_index(cursor):
    """Ensure required dedupe index exists before import."""
    cursor.execute("""
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'uq_fact_adl_event_dedupe'
        LIMIT 1
    """)

    if cursor.fetchone():
        return

    print("❌ Missing required dedupe index: uq_fact_adl_event_dedupe")
    print("\nThis import is configured to be idempotent, but your database schema")
    print("has not yet been migrated.")
    print("\nRun this once, then retry import:")
    print("  psql -U postgres -d care_analytics -f database/migrations/002_add_event_dedupe_index.sql")
    sys.exit(1)


# =============================================================================
# MAIN ETL LOGIC
# =============================================================================

def import_events(df, conn, client_name, limit=None):
    """Import events from DataFrame to database"""
    cursor = conn.cursor()

    # Safety check: enforce idempotent-ready schema
    verify_idempotency_index(cursor)
    
    # Get or create client
    print(f"\n📋 Setting up client: {client_name}")
    client_id = get_or_create_client(cursor, client_name)
    conn.commit()
    
    # Get domain mapping from database
    cursor.execute("SELECT domain_id, domain_name FROM dim_domain")
    db_domains = {name: id for id, name in cursor.fetchall()}
    print(f"✓ Found {len(db_domains)} domains in database")
    
    # Get unique residents
    unique_residents = df['Resident'].unique()
    print(f"✓ Found {len(unique_residents)} unique residents in CSV")
    
    # Create resident mapping
    resident_map = {}
    for resident_name in unique_residents:
        if pd.notna(resident_name):
            resident_id = get_or_create_resident(cursor, resident_name, client_id)
            resident_map[resident_name] = resident_id
    conn.commit()
    print(f"✓ Created/verified {len(resident_map)} residents")
    
    # Import events
    if limit:
        df = df.head(limit)
        print(f"\n📥 Importing first {limit} events...")
    else:
        print(f"\n📥 Importing all {len(df)} events...")
    
    imported = 0
    skipped = 0
    duplicates = 0
    errors = 0
    skipped_domains = {}  # Track which domains were skipped and how many
    
    for idx, row in df.iterrows():
        try:
            # Get resident
            resident_id = resident_map.get(row['Resident'])
            if not resident_id:
                skipped += 1
                continue
            
            # Map domain
            item = row['Item']
            
            # Skip if item is null/NaN (silently)
            if pd.isna(item):
                skipped += 1
                continue
            
            domain_name = DOMAIN_MAP.get(item)
            if not domain_name:
                skipped += 1
                # Track skipped domain
                if item not in skipped_domains:
                    skipped_domains[item] = 0
                skipped_domains[item] += 1
                continue
            
            domain_id = db_domains.get(domain_name)
            if not domain_id:
                skipped += 1
                continue
            
            # Get or create staff (if column exists)
            staff_id = None
            if 'Staff' in row and pd.notna(row['Staff']):
                staff_id = get_or_create_staff(cursor, row['Staff'])
            
            # Parse assistance level and refusal
            description = str(row.get('Description', ''))
            title = str(row.get('Title', ''))
            
            assistance = parse_assistance_level(description, title)
            refusal = is_refusal(description, title)
            
            # Ensure date dimension
            event_date = row['Time logged'].date()
            date_id = ensure_date_dimension(cursor, event_date)
            
            # Insert event
            cursor.execute("""
                INSERT INTO fact_adl_event (
                    resident_id, domain_id, staff_id, date_id,
                    event_timestamp, logged_timestamp,
                    assistance_level, is_refusal,
                    event_title, event_description,
                    source_system
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                resident_id,
                domain_id,
                staff_id,
                date_id,
                row['Time logged'],
                row['Time logged'],
                assistance.value,
                refusal,
                title[:255] if title else None,
                description,
                'CSV Import'
            ))

            if cursor.rowcount == 1:
                imported += 1
            else:
                duplicates += 1
                continue
            
            # Commit every 100 rows
            if imported % 100 == 0:
                conn.commit()
                print(f"  ✓ Imported {imported} events...")
                
        except Exception as e:
            errors += 1
            if errors <= 5:  # Only print first few errors
                print(f"  ❌ Error on row {idx}: {e}")
            continue
    
    conn.commit()
    cursor.close()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Import complete!")
    print(f"   Imported: {imported:,} events")
    print(f"   Skipped:  {skipped:,} events")
    print(f"   Duplicates (already present): {duplicates:,} events")
    print(f"   Errors:   {errors:,} events")
    
    # Show skipped domains breakdown
    if skipped_domains:
        print(f"\n⚠️  Skipped domains (not in Personal Care ADLs):")
        for domain, count in sorted(skipped_domains.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {domain}: {count:,} events")
        print(f"\n   💡 Tip: Only Personal Care ADL domains are imported:")
        print(f"      Washing/Bathing, Oral Care, Dressing/Clothing, Toileting, Grooming")
    
    print(f"{'='*60}")
    
    return imported, skipped, duplicates, errors


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Import care log CSV into PostgreSQL database'
    )
    parser.add_argument('csv_file', help='Path to CSV file')
    parser.add_argument('--client', default='Default Care Home', 
                       help='Client/organization name')
    parser.add_argument('--limit', type=int, 
                       help='Limit number of rows to import (for testing)')
    parser.add_argument('--date-format', default='%d/%m/%Y %H:%M:%S',
                       help='Date format in CSV (default: %%d/%%m/%%Y %%H:%%M:%%S)')
    parser.add_argument('--password', '-p',
                       help='Database password (overrides DB_PASSWORD env var)')
    parser.add_argument('--user', 
                       help='Database user (default: postgres)')
    parser.add_argument('--dbname',
                       help='Database name (default: care_analytics)')
    
    args = parser.parse_args()
    
    # Override DB_CONFIG with command line args if provided
    if args.password:
        DB_CONFIG['password'] = args.password
    if args.user:
        DB_CONFIG['user'] = args.user
    if args.dbname:
        DB_CONFIG['dbname'] = args.dbname
    
    print("="*60)
    print("Care Analytics - CSV Import Tool")
    print("="*60)
    
    # Load CSV
    df = load_csv(args.csv_file, args.date_format)
    
    # Connect to database
    print(f"\n🔌 Connecting to database: {DB_CONFIG['dbname']} as {DB_CONFIG['user']}")
    conn = connect_db()
    print("✓ Connected")
    
    # Import events
    try:
        import_events(df, conn, args.client, args.limit)
    finally:
        conn.close()
        print("\n✓ Database connection closed")


if __name__ == '__main__':
    main()
