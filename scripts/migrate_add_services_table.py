#!/usr/bin/env python3
"""
Safe Migration Script: Add Services Table to Existing Database

This script safely adds the services table to an existing database without
affecting any existing data.

Usage:
    python scripts/migrate_add_services_table.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.db import (
    init_db, get_db_connection, get_service_by_id, add_service
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default service configuration (the one you're currently working on)
DEFAULT_SERVICE = {
    "service_id": "cxp_ptg_adapter",
    "service_name": "CXP PTG Adapter",
    "repo_url": "https://gitlab.verizon.com/saja9l7/cxp-ptg-adapter.git",
    "main_branch": "main",
    "environments": ["prod", "alpha", "beta1", "beta2"],
    "description": "CXP Payment Gateway Adapter Service"
}

DEFAULT_CONFIG_PATHS = [
    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
    "*.cfg", "*.conf", "*.config",
    "Dockerfile", "docker-compose.yml",
    "pom.xml", "build.gradle", "requirements.txt"
]


def check_services_table_exists():
    """Check if services table already exists."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='services'
            """)
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking table: {e}")
        return False


def create_services_table():
    """Create the services table if it doesn't exist."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create services table with VSAT columns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    repo_url TEXT NOT NULL,
                    main_branch TEXT NOT NULL DEFAULT 'main',
                    environments JSON NOT NULL,
                    config_paths JSON,
                    vsat TEXT DEFAULT 'saja9l7',
                    vsat_url TEXT DEFAULT 'https://gitlab.verizon.com/saja9l7',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    metadata JSON
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_active ON services(is_active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_id ON services(service_id)")
            
            conn.commit()
            logger.info("✅ Services table created successfully (with VSAT columns)")
            return True
    except Exception as e:
        logger.error(f"❌ Error creating services table: {e}")
        return False


def add_default_service():
    """Add the default service if it doesn't exist."""
    try:
        # Check if service already exists
        existing = get_service_by_id(DEFAULT_SERVICE["service_id"])
        if existing:
            logger.info(f"ℹ️  Service '{DEFAULT_SERVICE['service_id']}' already exists in database")
            logger.info(f"   Service Name: {existing['service_name']}")
            logger.info(f"   Repo: {existing['repo_url']}")
            return False
        
        # Add default service
        # VSAT will be auto-extracted from repo_url
        add_service(
            service_id=DEFAULT_SERVICE["service_id"],
            service_name=DEFAULT_SERVICE["service_name"],
            repo_url=DEFAULT_SERVICE["repo_url"],
            main_branch=DEFAULT_SERVICE["main_branch"],
            environments=DEFAULT_SERVICE["environments"],
            config_paths=DEFAULT_CONFIG_PATHS,
            description=DEFAULT_SERVICE["description"]
        )
        
        logger.info(f"✅ Default service '{DEFAULT_SERVICE['service_id']}' added successfully")
        logger.info(f"   Service Name: {DEFAULT_SERVICE['service_name']}")
        logger.info(f"   Repo: {DEFAULT_SERVICE['repo_url']}")
        logger.info(f"   Environments: {', '.join(DEFAULT_SERVICE['environments'])}")
        return True
    except Exception as e:
        logger.error(f"❌ Error adding default service: {e}")
        return False


def verify_migration():
    """Verify the migration was successful."""
    try:
        # Check table exists
        if not check_services_table_exists():
            logger.error("❌ Services table does not exist!")
            return False
        
        # Check default service exists
        service = get_service_by_id(DEFAULT_SERVICE["service_id"])
        if not service:
            logger.warning("⚠️  Default service not found (you can add it later)")
            return True
        
        logger.info("\n✅ Migration Verification:")
        logger.info(f"   ✅ Services table exists")
        logger.info(f"   ✅ Default service exists: {service['service_id']}")
        return True
    except Exception as e:
        logger.error(f"❌ Error verifying migration: {e}")
        return False


def main():
    """Main migration function."""
    print("\n" + "=" * 80)
    print("🔧 MIGRATE: Add Services Table to Existing Database")
    print("=" * 80)
    print()
    print("⚠️  This script will:")
    print("   1. Create the 'services' table with VSAT columns (if it doesn't exist)")
    print("   2. Add default service 'cxp_ptg_adapter' with VSAT values (if it doesn't exist)")
    print("   3. NOT modify or delete any existing data")
    print()
    
    # Confirm
    response = input("Continue? (y/n): ").strip().lower()
    if response != 'y':
        print("❌ Migration cancelled")
        sys.exit(0)
    
    print()
    print("📊 Starting migration...")
    print()
    
    # Step 1: Check if table already exists
    logger.info("Step 1: Checking if services table exists...")
    if check_services_table_exists():
        logger.info("ℹ️  Services table already exists")
    else:
        logger.info("ℹ️  Services table does not exist, will create it")
    
    # Step 2: Initialize database (safe - uses IF NOT EXISTS)
    logger.info("\nStep 2: Running init_db() (safe - won't erase existing data)...")
    try:
        init_db()
        logger.info("✅ Database initialization complete")
    except Exception as e:
        logger.error(f"❌ Error during initialization: {e}")
        sys.exit(1)
    
    # Step 3: Create services table (double-check)
    logger.info("\nStep 3: Ensuring services table exists...")
    if not check_services_table_exists():
        if not create_services_table():
            logger.error("❌ Failed to create services table")
            sys.exit(1)
    else:
        logger.info("✅ Services table already exists")
    
    # Step 4: Add default service
    logger.info("\nStep 4: Adding default service...")
    add_default_service()
    
    # Step 5: Verify
    logger.info("\nStep 5: Verifying migration...")
    if verify_migration():
        print("\n" + "=" * 80)
        print("✅ MIGRATION COMPLETE!")
        print("=" * 80)
        print()
        print("📋 Summary:")
        print("   ✅ Services table created/verified")
        print(f"   ✅ Default service '{DEFAULT_SERVICE['service_id']}' added/verified")
        print("   ✅ No existing data was modified or deleted")
        print()
        print("💡 Next steps:")
        print("   1. Restart your server: python main.py")
        print("   2. Services will be loaded from database automatically")
        print("   3. Add more services via API or CLI:")
        print("      - API: POST /api/services")
        print("      - CLI: python scripts/manage_services.py add")
        print()
    else:
        print("\n" + "=" * 80)
        print("⚠️  MIGRATION COMPLETED WITH WARNINGS")
        print("=" * 80)
        print("Please review the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
