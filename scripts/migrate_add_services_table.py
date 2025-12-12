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

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from shared.db import (
    init_db, get_db_connection, get_service_by_id, add_service
)
from shared.git_operations import (
    create_config_only_branch,
    create_env_specific_config_branch
)
from shared.golden_branch_tracker import add_golden_branch
from datetime import datetime
import os
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


def create_golden_branches_for_service(service_config, config_paths):
    """
    Create golden branches for a service:
    1. One complete snapshot with all config files (golden_snapshot_*)
    2. Four environment-specific branches (golden_prod_*, golden_alpha_*, etc.)
    
    Args:
        service_config: Service configuration dict
        config_paths: List of config file patterns
    
    Returns:
        Dict with created branch names
    """
    gitlab_token = os.getenv("GITLAB_TOKEN")
    if not gitlab_token:
        logger.warning("⚠️  GITLAB_TOKEN not set, skipping golden branch creation")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = datetime.now().strftime("%H%M%S")[:6]
    
    created_branches = {}
    
    try:
        # 1. Create complete golden snapshot (all config files)
        logger.info(f"\n📸 Creating complete golden snapshot for all environments...")
        snapshot_branch = f"golden_snapshot_{timestamp}_{short_hash}"
        
        success = create_config_only_branch(
            repo_url=service_config["repo_url"],
            main_branch=service_config["main_branch"],
            new_branch_name=snapshot_branch,
            config_paths=config_paths,
            gitlab_token=gitlab_token
        )
        
        if success:
            logger.info(f"   ✅ Complete snapshot: {snapshot_branch}")
            created_branches['snapshot'] = snapshot_branch
            
            # Track in database (use 'all' as environment indicator)
            add_golden_branch(
                service_name=service_config["service_id"],
                environment='all',
                branch_name=snapshot_branch,
                metadata={'type': 'complete_snapshot', 'contains': 'all_config_files'}
            )
        else:
            logger.warning(f"   ⚠️  Failed to create complete snapshot")
        
        # 2. Create environment-specific golden branches
        logger.info(f"\n📸 Creating environment-specific golden branches...")
        
        for env in service_config["environments"]:
            env_branch = f"golden_{env}_{timestamp}_{short_hash}"
            
            logger.info(f"\n   Creating {env} branch...")
            success = create_env_specific_config_branch(
                repo_url=service_config["repo_url"],
                main_branch=service_config["main_branch"],
                new_branch_name=env_branch,
                environment=env,
                config_paths=config_paths,
                gitlab_token=gitlab_token
            )
            
            if success:
                logger.info(f"   ✅ {env}: {env_branch}")
                created_branches[env] = env_branch
                
                # Track in database
                add_golden_branch(
                    service_name=service_config["service_id"],
                    environment=env,
                    branch_name=env_branch,
                    metadata={'type': 'env_specific', 'filtered_for': env}
                )
            else:
                logger.warning(f"   ⚠️  Failed to create {env} branch")
        
        return created_branches
        
    except Exception as e:
        logger.error(f"❌ Error creating golden branches: {e}")
        return None


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
        
        # Create golden branches for this service
        logger.info(f"\n🌿 Creating golden branches for service...")
        branches = create_golden_branches_for_service(DEFAULT_SERVICE, DEFAULT_CONFIG_PATHS)
        
        if branches:
            logger.info(f"\n✅ Golden branches created:")
            logger.info(f"   📸 Complete snapshot: {branches.get('snapshot', 'N/A')}")
            for env in DEFAULT_SERVICE["environments"]:
                if env in branches:
                    logger.info(f"   🌿 {env}: {branches[env]}")
        else:
            logger.warning(f"\n⚠️  Golden branches were not created (check GitLab token)")
        
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
    print("   3. Create 5 golden branches in GitLab:")
    print("      - 1 complete snapshot: golden_snapshot_* (all config files)")
    print("      - 4 environment-specific: golden_prod_*, golden_alpha_*, golden_beta1_*, golden_beta2_*")
    print("   4. NOT modify or delete any existing data")
    print()
    print("⚠️  Requirements:")
    print("   - GITLAB_TOKEN environment variable must be set")
    print("   - Network access to GitLab")
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
        print("   ✅ Golden branches created in GitLab:")
        print("      - Complete snapshot (all config files)")
        print("      - Environment-specific branches (prod, alpha, beta1, beta2)")
        print("   ✅ No existing data was modified or deleted")
        print()
        print("💡 Next steps:")
        print("   1. Verify golden branches on GitLab:")
        print("      https://gitlab.verizon.com/saja9l7/cxp-ptg-adapter/-/branches")
        print("   2. Restart your server: python main.py")
        print("   3. Services will be loaded from database automatically")
        print("   4. Add more services via API or CLI:")
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
