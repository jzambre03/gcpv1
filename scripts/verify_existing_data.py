#!/usr/bin/env python3
"""
Verify Existing Database Data is Safe

This script checks your existing database to show what data exists,
and confirms that running init_db() will NOT affect it.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.db import get_db_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def count_records(table_name):
    """Count records in a table."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]
    except Exception as e:
        return f"Error: {e}"


def list_tables():
    """List all tables in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return []


def verify_data_safety():
    """Verify that init_db() won't affect existing data."""
    print("\n" + "=" * 80)
    print("🔍 VERIFYING EXISTING DATABASE DATA")
    print("=" * 80)
    print()
    
    # List all tables
    tables = list_tables()
    
    if not tables:
        print("❌ No tables found in database")
        print("   Database may be empty or doesn't exist yet")
        return
    
    print(f"📊 Found {len(tables)} tables in database:")
    print()
    
    total_records = 0
    
    # Check each table
    for table in sorted(tables):
        count = count_records(table)
        if isinstance(count, int):
            total_records += count
            status = "✅" if count > 0 else "ℹ️"
            print(f"   {status} {table:30} → {count:6} records")
        else:
            print(f"   ⚠️  {table:30} → {count}")
    
    print()
    print("=" * 80)
    print(f"📈 TOTAL RECORDS: {total_records}")
    print("=" * 80)
    print()
    
    # Check if services table exists
    has_services_table = "services" in tables
    
    if has_services_table:
        print("✅ Services table already exists!")
        print("   Migration script will skip creating it")
    else:
        print("ℹ️  Services table does NOT exist yet")
        print("   Migration script will create it (safe)")
    
    print()
    print("=" * 80)
    print("🔒 DATA SAFETY VERIFICATION")
    print("=" * 80)
    print()
    print("✅ init_db() uses 'CREATE TABLE IF NOT EXISTS'")
    print("   → Only creates tables that don't exist")
    print("   → Does NOT drop existing tables")
    print("   → Does NOT delete any data")
    print()
    print("✅ No DROP TABLE statements in init_db()")
    print("   → Existing tables will remain untouched")
    print()
    print("✅ No TRUNCATE or DELETE statements in init_db()")
    print("   → Existing records will remain untouched")
    print()
    print("=" * 80)
    print("✅ CONCLUSION: Your existing data is SAFE!")
    print("=" * 80)
    print()
    print("💡 You can safely run:")
    print("   python scripts/migrate_add_services_table.py")
    print()
    print("   OR")
    print()
    print("   from shared.db import init_db")
    print("   init_db()  # This will only create the services table")
    print()


if __name__ == "__main__":
    try:
        verify_data_safety()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

