#!/usr/bin/env python3
"""
Database Initialization Script
Run this to initialize the SQLite database for Golden Config AI System.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.db import init_db, get_db_stats, DB_PATH
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Initialize the database."""
    print("=" * 80)
    print("Golden Config AI - Database Initialization")
    print("=" * 80)
    print()
    
    print(f"📁 Database Location: {DB_PATH}")
    print()
    
    if DB_PATH.exists():
        print("⚠️  Database already exists. This will ensure all tables are created.")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Aborted.")
            return
        print()
    
    try:
        # Initialize database
        print("🔨 Creating database tables...")
        init_db()
        print()
        
        # Get stats
        stats = get_db_stats()
        print("✅ Database initialized successfully!")
        print()
        print("📊 Database Statistics:")
        for table, count in stats.items():
            print(f"   - {table}: {count} records")
        print()
        
        print("=" * 80)
        print("✅ INITIALIZATION COMPLETE")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Run the application: python main.py")
        print("2. All validation data will be stored in the database")
        print("3. Use shared/db.py functions to query data")
        print()
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print()
        print("❌ INITIALIZATION FAILED")
        print(f"   Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

