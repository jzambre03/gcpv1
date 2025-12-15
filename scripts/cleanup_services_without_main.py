#!/usr/bin/env python3
"""
Cleanup script to remove services that don't have a main branch.
This script identifies services where the main branch doesn't exist in GitLab
and removes them from the database (including their golden branches).

Usage: python scripts/cleanup_services_without_main.py [--dry-run] [--vsat VSAT_NAME]
"""

import sys
import os
import logging
import argparse
import requests
from pathlib import Path
from typing import List, Dict, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from shared.db import get_db_connection, get_all_services

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_main_branch_exists(repo_url: str, gitlab_token: str) -> bool:
    """
    Check if a service has a main branch in GitLab.
    
    Args:
        repo_url: Repository URL (e.g., https://gitlab.verizon.com/vsat/repo.git)
        gitlab_token: GitLab API token
    
    Returns:
        True if main branch exists, False otherwise
    """
    try:
        # Extract project path from repo URL
        # Example: https://gitlab.verizon.com/vsat/repo.git -> vsat/repo
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Get GitLab base URL and project path
        parts = repo_url.replace('https://', '').replace('http://', '').split('/')
        gitlab_base = f"https://{parts[0]}"
        project_path = '/'.join(parts[1:])
        
        # URL encode the project path
        import urllib.parse
        encoded_path = urllib.parse.quote(project_path, safe='')
        
        # Check if main branch exists
        api_url = f"{gitlab_base}/api/v4/projects/{encoded_path}/repository/branches/main"
        headers = {"PRIVATE-TOKEN": gitlab_token}
        
        response = requests.get(api_url, headers=headers, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        logger.warning(f"   ⚠️  Error checking main branch for {repo_url}: {e}")
        return False


def find_services_without_main(
    gitlab_token: str,
    vsat_filter: str = None
) -> Tuple[List[Dict], List[Dict]]:
    """
    Find services that don't have a main branch.
    
    Args:
        gitlab_token: GitLab API token
        vsat_filter: Optional VSAT name to filter by
    
    Returns:
        Tuple of (services_without_main, services_with_main)
    """
    logger.info("🔍 Scanning database for services...")
    
    # Get all active services
    all_services = get_all_services(active_only=True)
    
    # Filter by VSAT if specified
    if vsat_filter:
        all_services = [s for s in all_services if s.get('vsat') == vsat_filter]
        logger.info(f"   Filtered to VSAT '{vsat_filter}': {len(all_services)} services")
    else:
        logger.info(f"   Found {len(all_services)} total active services")
    
    services_without_main = []
    services_with_main = []
    
    logger.info("\n🔎 Checking each service for main branch...")
    for i, service in enumerate(all_services, 1):
        service_id = service['service_id']
        repo_url = service['repo_url']
        vsat = service.get('vsat', 'unknown')
        
        logger.info(f"   [{i}/{len(all_services)}] {service_id}...")
        
        has_main = check_main_branch_exists(repo_url, gitlab_token)
        
        if has_main:
            logger.info(f"      ✅ Has main branch")
            services_with_main.append(service)
        else:
            logger.info(f"      ❌ NO main branch")
            services_without_main.append(service)
    
    return services_without_main, services_with_main


def delete_services(services: List[Dict], dry_run: bool = True) -> int:
    """
    Delete services from the database.
    
    Args:
        services: List of service dictionaries
        dry_run: If True, only show what would be deleted
    
    Returns:
        Number of services deleted
    """
    if not services:
        logger.info("✅ No services to delete!")
        return 0
    
    logger.info(f"\n{'='*80}")
    if dry_run:
        logger.info("🔍 DRY RUN - Would delete the following services:")
    else:
        logger.info("🗑️  DELETING services without main branch:")
    logger.info(f"{'='*80}")
    
    for service in services:
        logger.info(f"   ❌ {service['service_id']}")
        logger.info(f"      VSAT: {service.get('vsat', 'unknown')}")
        logger.info(f"      Repo: {service['repo_url']}")
    
    logger.info(f"{'='*80}")
    logger.info(f"   Total: {len(services)} services")
    logger.info(f"{'='*80}")
    
    if dry_run:
        logger.info("\n⚠️  This is a DRY RUN. No changes were made.")
        logger.info("   To actually delete, run: python scripts/cleanup_services_without_main.py --execute")
        return 0
    
    # Confirm deletion
    logger.info(f"\n⚠️  WARNING: You are about to delete {len(services)} services and their golden branches!")
    response = input("   Type 'DELETE' to confirm: ")
    
    if response != 'DELETE':
        logger.info("❌ Deletion cancelled.")
        return 0
    
    # Delete services
    deleted_count = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for service in services:
            service_id = service['service_id']
            
            try:
                # Delete golden branches first (foreign key constraint)
                cursor.execute(
                    "DELETE FROM golden_branches WHERE service_name = ?",
                    (service_id,)
                )
                branches_deleted = cursor.rowcount
                
                # Delete service
                cursor.execute(
                    "DELETE FROM services WHERE service_id = ?",
                    (service_id,)
                )
                
                deleted_count += 1
                logger.info(f"   ✅ Deleted {service_id} ({branches_deleted} branches)")
                
            except Exception as e:
                logger.error(f"   ❌ Error deleting {service_id}: {e}")
        
        conn.commit()
    
    logger.info(f"\n✅ Successfully deleted {deleted_count} services!")
    return deleted_count


def main():
    parser = argparse.ArgumentParser(
        description="Remove services that don't have a main branch"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Show what would be deleted without actually deleting (default)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually delete services (requires confirmation)'
    )
    parser.add_argument(
        '--vsat',
        type=str,
        help='Only check services for specific VSAT (e.g., saja9l7)'
    )
    
    args = parser.parse_args()
    
    # Get GitLab token
    gitlab_token = os.getenv('GITLAB_TOKEN')
    if not gitlab_token:
        logger.error("❌ GITLAB_TOKEN not found in .env file!")
        return 1
    
    logger.info("="*80)
    logger.info("🧹 SERVICE CLEANUP - Remove Services Without Main Branch")
    logger.info("="*80)
    
    if args.vsat:
        logger.info(f"🎯 Target VSAT: {args.vsat}")
    else:
        logger.info(f"🎯 Target: ALL VSATs")
    
    if args.execute:
        logger.info(f"⚠️  Mode: EXECUTE (will delete services)")
    else:
        logger.info(f"🔍 Mode: DRY RUN (no changes)")
    
    logger.info("="*80)
    
    # Find services without main branch
    services_without_main, services_with_main = find_services_without_main(
        gitlab_token, args.vsat
    )
    
    logger.info(f"\n{'='*80}")
    logger.info("📊 SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"   ✅ Services WITH main branch: {len(services_with_main)}")
    logger.info(f"   ❌ Services WITHOUT main branch: {len(services_without_main)}")
    logger.info(f"   📊 Total services checked: {len(services_with_main) + len(services_without_main)}")
    logger.info(f"{'='*80}")
    
    # Delete services (or show what would be deleted)
    dry_run = not args.execute
    deleted_count = delete_services(services_without_main, dry_run=dry_run)
    
    if not dry_run and deleted_count > 0:
        logger.info("\n✅ Cleanup complete!")
        logger.info(f"   Removed: {deleted_count} services")
        logger.info(f"   Remaining: {len(services_with_main)} services")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
