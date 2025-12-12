#!/usr/bin/env python3
"""
VSAT Master Config Sync - Automated Service Discovery and Management

This script automatically:
1. Reads VSAT master config file
2. Fetches all services from configured VSATs
3. Syncs services to database (add/update/remove)
4. Creates golden branches for new services (in parallel)
5. Handles errors and sends notifications

Can run as:
- One-time sync: python scripts/vsat_sync.py
- Scheduled job: Integrated with APScheduler
- File watcher: Auto-sync on config changes
"""

import sys
import yaml
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

import os
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from shared.db import (
    get_db_connection, add_service, get_service_by_id, 
    get_all_services, init_db
)
from shared.git_operations import (
    create_config_only_branch,
    create_env_specific_config_branch
)
from shared.golden_branch_tracker import add_golden_branch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
MASTER_CONFIG_FILE = project_root / "config" / "vsat_master.yaml"
DETAILED_CONFIG_FILE = project_root / "config" / "vsat_config.yaml"
CONFIG_HASH_FILE = project_root / "config" / ".vsat_master_hash"


class VSATSyncError(Exception):
    """Custom exception for VSAT sync errors"""
    pass


def load_vsat_config() -> Dict[str, Any]:
    """
    Load and merge VSAT master config (simple) with detailed config.
    
    Master config (vsat_master.yaml): Simple - just VSAT list
    Detailed config (vsat_config.yaml): All detailed settings
    """
    try:
        # Load master config (simple - just VSATs)
        if not MASTER_CONFIG_FILE.exists():
            raise VSATSyncError(f"Master config file not found: {MASTER_CONFIG_FILE}")
        
        with open(MASTER_CONFIG_FILE, 'r') as f:
            master_config = yaml.safe_load(f) or {}
        
        # Validate required fields
        if 'vsats' not in master_config:
            raise VSATSyncError("Master config file missing 'vsats' section")
        
        logger.info(f"✅ Loaded master config: {len(master_config['vsats'])} VSATs")
        
        # Load detailed config (defaults, sync settings, filters, etc.)
        detailed_config = {}
        if DETAILED_CONFIG_FILE.exists():
            with open(DETAILED_CONFIG_FILE, 'r') as f:
                detailed_config = yaml.safe_load(f) or {}
            logger.info("✅ Loaded detailed config")
        else:
            logger.warning(f"⚠️  Detailed config not found: {DETAILED_CONFIG_FILE}")
            logger.warning("   Using minimal defaults")
        
        # Merge configs: master (simple) + detailed (defaults)
        merged_config = {
            'vsats': master_config['vsats'],
            'global_defaults': detailed_config.get('defaults', {
                'main_branch': 'main',
                'environments': ['prod'],
                'config_paths': ['*.yml', '*.yaml', '*.properties']
            }),
            'sync_config': detailed_config.get('sync', {
                'create_golden_branches': True,
                'parallel_branch_creation': True,
                'max_branch_workers': 5,
                'weekly_sync_schedule': '0 2 0',
                'min_services_threshold': 1,
                'max_delete_percentage': 50
            }),
            'filters': detailed_config.get('filters', {
                'exclude_patterns': [],
                'require_main_branch': True
            }),
            'notifications': detailed_config.get('notifications', {
                'enabled': True,
                'channels': [{'type': 'log', 'level': 'info'}]
            })
        }
        
        # Apply VSAT-specific overrides from detailed config (if any)
        vsat_overrides = detailed_config.get('vsat_overrides') or {}
        if vsat_overrides and isinstance(vsat_overrides, dict):
            for vsat in merged_config['vsats']:
                vsat_name = vsat.get('name')
                if vsat_name and vsat_name in vsat_overrides:
                    override = vsat_overrides[vsat_name]
                    if isinstance(override, dict):
                        if 'service_config' not in vsat:
                            vsat['service_config'] = {}
                        vsat['service_config'].update(override)
                        logger.info(f"   Applied overrides for VSAT: {vsat_name}")
        
        return merged_config
    
    except yaml.YAMLError as e:
        raise VSATSyncError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise VSATSyncError(f"Error loading config: {e}")


def get_config_hash() -> str:
    """Calculate hash of both config files for change detection"""
    combined_content = b""
    
    # Include master config
    if MASTER_CONFIG_FILE.exists():
        with open(MASTER_CONFIG_FILE, 'rb') as f:
            combined_content += f.read()
    
    # Include detailed config
    if DETAILED_CONFIG_FILE.exists():
        with open(DETAILED_CONFIG_FILE, 'rb') as f:
            combined_content += f.read()
    
    return hashlib.sha256(combined_content).hexdigest()


def has_config_changed() -> bool:
    """Check if config file has changed since last sync"""
    if not CONFIG_HASH_FILE.exists():
        return True
    
    with open(CONFIG_HASH_FILE, 'r') as f:
        old_hash = f.read().strip()
    
    current_hash = get_config_hash()
    return old_hash != current_hash


def save_config_hash():
    """Save current config hash"""
    CONFIG_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_HASH_FILE, 'w') as f:
        f.write(get_config_hash())


def create_http_session() -> requests.Session:
    """Create requests session with retry logic"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def fetch_user_projects(
    username: str,
    gitlab_base: str,
    gitlab_token: str,
    filters: Dict[str, Any],
    session: requests.Session
) -> List[Dict[str, Any]]:
    """
    Fetch projects owned by a user namespace.
    Used when VSAT is a user namespace instead of a group.
    
    Uses GitLab's user-specific API endpoint for better performance.
    """
    logger.info(f"   '{username}' is a user namespace, fetching user projects...")
    
    headers = {"PRIVATE-TOKEN": gitlab_token}
    all_projects = []
    page = 1
    per_page = 100
    
    while True:
        # Use user-specific projects API (more efficient than filtering all projects)
        url = f"{gitlab_base}/api/v4/users/{username}/projects"
        params = {
            "per_page": per_page,
            "page": page,
            "owned": True,  # Only projects owned by user
            "archived": False
        }
        
        try:
            response = session.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            projects = response.json()
            if not projects:
                break
            
            all_projects.extend(projects)
            page += 1
            
            # Rate limiting
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error fetching user projects for {username}: {e}")
            raise VSATSyncError(f"Failed to fetch user projects for {username}")
    
    logger.info(f"   Found {len(all_projects)} projects owned by '{username}'")
    
    # Apply filters
    filtered_projects = apply_filters(all_projects, filters)
    logger.info(f"   After filtering: {len(filtered_projects)} projects")
    
    # Check for main branch
    projects_with_main = check_main_branch_parallel(
        filtered_projects, gitlab_token, session
    )
    
    logger.info(f"   With main branch: {len(projects_with_main)} projects")
    
    return projects_with_main


def fetch_vsat_projects(
    vsat_name: str,
    vsat_url: str,
    gitlab_token: str,
    filters: Dict[str, Any],
    session: requests.Session
) -> List[Dict[str, Any]]:
    """
    Fetch all projects from a VSAT (supports both groups and user namespaces).
    Auto-detects whether VSAT is a group or user and uses appropriate API.
    Optimized with parallel branch checking.
    """
    logger.info(f"📡 Fetching projects from VSAT: {vsat_name}")
    
    # Extract base URL
    gitlab_base = vsat_url.replace(f"/{vsat_name}", "")
    headers = {"PRIVATE-TOKEN": gitlab_token}
    
    # Try group API first
    all_projects = []
    page = 1
    per_page = 100
    
    while True:
        url = f"{gitlab_base}/api/v4/groups/{vsat_name}/projects"
        params = {
            "per_page": per_page,
            "page": page,
            "include_subgroups": True,
            "archived": False
        }
        
        try:
            response = session.get(url, headers=headers, params=params, timeout=30)
            
            # If first page returns 404, it's not a group - try user namespace
            if response.status_code == 404 and page == 1:
                logger.info(f"   Not a group, trying user namespace API...")
                return fetch_user_projects(vsat_name, gitlab_base, gitlab_token, filters, session)
            
            response.raise_for_status()
            
            projects = response.json()
            if not projects:
                break
            
            all_projects.extend(projects)
            page += 1
            
            # Rate limiting
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            # If first page failed, propagate error
            if page == 1:
                logger.error(f"❌ Error fetching projects from {vsat_name}: {e}")
                raise VSATSyncError(f"Failed to fetch projects from {vsat_name}")
            else:
                # Later pages - just stop pagination
                break
    
    logger.info(f"   Found {len(all_projects)} total projects (group)")
    
    # Apply filters
    filtered_projects = apply_filters(all_projects, filters)
    logger.info(f"   After filtering: {len(filtered_projects)} projects")
    
    # Check for main branch (optimized with parallel checking)
    projects_with_main = check_main_branch_parallel(
        filtered_projects, gitlab_token, session
    )
    
    logger.info(f"   With main branch: {len(projects_with_main)} projects")
    
    return projects_with_main


def apply_filters(projects: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
    """Apply exclude/include filters to projects"""
    if not filters:
        return projects
    
    filtered = projects
    
    # Exclude patterns
    exclude_patterns = filters.get('exclude_patterns', [])
    if exclude_patterns:
        filtered = [
            p for p in filtered
            if not any(
                p['name'].lower().endswith(pattern.replace('*', '').lower())
                or p['name'].lower().startswith(pattern.replace('*', '').lower())
                for pattern in exclude_patterns
            )
        ]
    
    # Include patterns (if specified)
    include_patterns = filters.get('include_patterns', [])
    if include_patterns:
        filtered = [
            p for p in filtered
            if any(
                p['name'].lower().endswith(pattern.replace('*', '').lower())
                or p['name'].lower().startswith(pattern.replace('*', '').lower())
                for pattern in include_patterns
            )
        ]
    
    return filtered


def check_main_branch_parallel(
    projects: List[Dict],
    gitlab_token: str,
    session: requests.Session
) -> List[Dict]:
    """
    Check which projects have main branch (optimized with parallel execution).
    Similar to test.py logic but integrated here.
    """
    projects_with_main_default = []
    projects_to_check = []
    
    # Quick filter: Projects where default_branch == 'main'
    for project in projects:
        if project.get('default_branch') == 'main':
            project['has_main_branch'] = True
            projects_with_main_default.append(project)
        else:
            projects_to_check.append(project)
    
    logger.info(f"   ⚡ Quick filter: {len(projects_with_main_default)} with main as default")
    
    if not projects_to_check:
        return projects_with_main_default
    
    logger.info(f"   🔍 Checking {len(projects_to_check)} projects for main branch...")
    
    # Parallel branch checking
    def check_branch(project):
        """Check if project has main branch"""
        try:
            # Extract GitLab base URL properly
            web_url = project.get('web_url', '')
            project_id = project.get('id')
            
            if not web_url or not project_id:
                return None
            
            # Construct API URL for checking main branch
            gitlab_base = web_url.split('/-/')[0] if '/-/' in web_url else web_url.rsplit('/', 1)[0]
            api_url = f"{gitlab_base}/api/v4/projects/{project_id}/repository/branches/main"
            headers = {"PRIVATE-TOKEN": gitlab_token}
            
            response = session.get(api_url, headers=headers, timeout=10)
            has_main = response.status_code == 200
            
            if has_main:
                project['has_main_branch'] = True
                return project
            return None
        except Exception as e:
            # Silently skip - project doesn't have main branch or error
            return None
    
    filtered_projects = list(projects_with_main_default)
    
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(check_branch, proj): proj for proj in projects_to_check}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                filtered_projects.append(result)
    
    return filtered_projects


def create_golden_branches_parallel(
    service_id: str,
    repo_url: str,
    main_branch: str,
    environments: List[str],
    config_paths: List[str],
    gitlab_token: str
) -> Dict[str, str]:
    """
    Create golden branches for a service in parallel.
    Reuses the optimized logic from migration script.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = datetime.now().strftime("%H%M%S")[:6]
    
    created_branches = {}
    
    def create_branch_task(branch_type, branch_name, environment=None):
        """Task for parallel execution"""
        try:
            if branch_type == 'snapshot':
                success = create_config_only_branch(
                    repo_url=repo_url,
                    main_branch=main_branch,
                    new_branch_name=branch_name,
                    config_paths=config_paths,
                    gitlab_token=gitlab_token
                )
                return ('snapshot', branch_name, success, None)
            else:
                success = create_env_specific_config_branch(
                    repo_url=repo_url,
                    main_branch=main_branch,
                    new_branch_name=branch_name,
                    environment=environment,
                    config_paths=config_paths,
                    gitlab_token=gitlab_token
                )
                return (environment, branch_name, success, environment)
        except Exception as e:
            logger.error(f"❌ Error creating {branch_type} branch '{branch_name}': {e}")
            return (branch_type, branch_name, False, environment)
    
    try:
        # Prepare all branch creation tasks
        tasks = []
        
        # Task 1: Complete snapshot
        snapshot_branch = f"golden_snapshot_{timestamp}_{short_hash}"
        tasks.append(('snapshot', snapshot_branch, None))
        
        # Tasks 2-N: Environment-specific branches
        for env in environments:
            env_branch = f"golden_{env}_{timestamp}_{short_hash}"
            tasks.append(('env', env_branch, env))
        
        # Execute all branch creations in parallel (silent - parent handles logging)
        with ThreadPoolExecutor(max_workers=min(5, len(tasks))) as executor:
            futures = {
                executor.submit(create_branch_task, task[0], task[1], task[2]): task
                for task in tasks
            }
            
            for future in as_completed(futures):
                branch_type, branch_name, success, environment = future.result()
                
                if success:
                    if branch_type == 'snapshot':
                        created_branches['snapshot'] = branch_name
                        add_golden_branch(
                            service_name=service_id,
                            environment='all',
                            branch_name=branch_name,
                            metadata={'type': 'complete_snapshot', 'contains': 'all_config_files'}
                        )
                    else:
                        created_branches[environment] = branch_name
                        add_golden_branch(
                            service_name=service_id,
                            environment=environment,
                            branch_name=branch_name,
                            metadata={'type': 'env_specific', 'filtered_for': environment}
                        )
        
        # Return without logging (parent handles progress)
        return created_branches
        
    except Exception as e:
        logger.error(f"❌ Error creating golden branches for {service_id}: {e}")
        return {}


def sync_vsat_services(
    vsat: Dict[str, Any],
    gitlab_token: str,
    sync_config: Dict[str, Any],
    filters: Dict[str, Any],
    global_defaults: Dict[str, Any],
    session: requests.Session
) -> Tuple[int, int, int, List[str]]:
    """
    Sync all services from a VSAT to the database.
    
    Returns:
        (added_count, updated_count, unchanged_count, errors)
    """
    vsat_name = vsat['name']
    vsat_url = vsat['url']
    
    if not vsat.get('enabled', True):
        logger.info(f"⏭️  Skipping disabled VSAT: {vsat_name}")
        return (0, 0, 0, [])
    
    logger.info(f"\n{'='*80}")
    logger.info(f"🔄 Syncing VSAT: {vsat_name}")
    logger.info(f"{'='*80}")
    
    try:
        # Fetch projects from GitLab
        projects = fetch_vsat_projects(
            vsat_name, vsat_url, gitlab_token, filters, session
        )
        
        if len(projects) < sync_config.get('min_services_threshold', 1):
            logger.warning(f"⚠️  VSAT {vsat_name} has only {len(projects)} services (below threshold)")
        
        # Get service config (VSAT-specific or global defaults)
        service_config = vsat.get('service_config', {})
        main_branch = service_config.get('main_branch', global_defaults.get('main_branch', 'main'))
        environments = service_config.get('environments', global_defaults.get('environments', ['prod']))
        config_paths = service_config.get('config_paths', global_defaults.get('config_paths', ['*.yml']))
        
        added_count = 0
        updated_count = 0
        unchanged_count = 0
        errors = []
        new_services_for_branches = []  # Collect services that need branch creation
        
        # Phase 1: Process all projects and add/update in database (fast, sequential)
        logger.info(f"   📊 Processing {len(projects)} services...")
        for project in projects:
            try:
                service_id = f"{vsat_name}_{project['path']}"
                service_name = project['name']
                repo_url = project['http_url_to_repo']
                
                # Check if service exists
                existing = get_service_by_id(service_id)
                
                if existing:
                    # Service exists - check if update needed
                    if existing['repo_url'] != repo_url or existing['main_branch'] != main_branch:
                        logger.info(f"   📝 Updating: {service_id}")
                        add_service(
                            service_id=service_id,
                            service_name=service_name,
                            repo_url=repo_url,
                            main_branch=main_branch,
                            environments=environments,
                            config_paths=config_paths,
                            vsat=vsat_name,
                            vsat_url=vsat_url,
                            description=project.get('description', '')
                        )
                        updated_count += 1
                    else:
                        unchanged_count += 1
                    
                    # Check if service has golden branches - if not, create them
                    if sync_config.get('create_golden_branches', True):
                        # Check if any golden branches exist for this service
                        from shared.db import get_db_connection
                        has_branches = False
                        try:
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    SELECT COUNT(*) as count FROM golden_branches 
                                    WHERE service_name = ? AND branch_type = 'golden'
                                """, (service_id,))
                                has_branches = cursor.fetchone()['count'] > 0
                        except:
                            pass
                        
                        if not has_branches:
                            logger.info(f"   🌿 Service exists but has no branches, queuing for branch creation: {service_id}")
                            new_services_for_branches.append({
                                'service_id': service_id,
                                'repo_url': repo_url,
                                'main_branch': main_branch,
                                'environments': environments,
                                'config_paths': config_paths
                            })
                else:
                    # New service - add to database
                    logger.info(f"   ➕ Adding: {service_id}")
                    add_service(
                        service_id=service_id,
                        service_name=service_name,
                        repo_url=repo_url,
                        main_branch=main_branch,
                        environments=environments,
                        config_paths=config_paths,
                        vsat=vsat_name,
                        vsat_url=vsat_url,
                        description=project.get('description', '')
                    )
                    added_count += 1
                    
                    # Collect new services for parallel branch creation
                    if sync_config.get('create_golden_branches', True):
                        new_services_for_branches.append({
                            'service_id': service_id,
                            'repo_url': repo_url,
                            'main_branch': main_branch,
                            'environments': environments,
                            'config_paths': config_paths
                        })
            
            except Exception as e:
                error_msg = f"Error processing {project.get('name', 'unknown')}: {e}"
                logger.error(f"   ❌ {error_msg}")
                errors.append(error_msg)
        
        # Phase 2: Create golden branches for all new services in parallel (optimized)
        branches_created_count = 0
        branches_failed_count = 0
        
        if new_services_for_branches:
            logger.info(f"\n   🌿 Creating golden branches for {len(new_services_for_branches)} new services...")
            logger.info(f"      ⚡ Using parallel execution (max {sync_config.get('max_branch_workers', 10)} concurrent services)")
            
            max_workers = sync_config.get('max_branch_workers', 10)
            
            def create_branches_for_service(service_info):
                """Task to create branches for a single service"""
                try:
                    service_id = service_info['service_id']
                    # Reduced logging for parallel execution (too verbose otherwise)
                    
                    branches = create_golden_branches_parallel(
                        service_id,
                        service_info['repo_url'],
                        service_info['main_branch'],
                        service_info['environments'],
                        service_info['config_paths'],
                        gitlab_token
                    )
                    
                    if branches:
                        return (service_id, True, len(branches))
                    else:
                        logger.warning(f"      ⚠️  {service_id}: Failed to create branches")
                        return (service_id, False, 0)
                        
                except Exception as e:
                    logger.error(f"      ❌ {service_info['service_id']}: Error creating branches: {e}")
                    return (service_info['service_id'], False, 0)
            
            # Execute branch creation for all services in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(create_branches_for_service, service_info): service_info
                    for service_info in new_services_for_branches
                }
                
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    service_id, success, branch_count = future.result()
                    
                    if success:
                        branches_created_count += branch_count
                    else:
                        branches_failed_count += 1
                    
                    # Progress update every 10 services or at completion
                    if completed % 10 == 0 or completed == len(new_services_for_branches):
                        logger.info(f"      📊 Progress: {completed}/{len(new_services_for_branches)} services ({branches_created_count} branches created)")
                    elif completed % 5 == 0:
                        # Less verbose updates
                        logger.debug(f"      📊 Progress: {completed}/{len(new_services_for_branches)}")
            
            logger.info(f"\n   ✅ Branch creation complete:")
            logger.info(f"      📊 Services processed: {len(new_services_for_branches)}")
            logger.info(f"      ✅ Total branches created: {branches_created_count}")
            if branches_failed_count > 0:
                logger.warning(f"      ⚠️  Failed: {branches_failed_count} services")
        
        logger.info(f"\n📊 VSAT {vsat_name} sync complete:")
        logger.info(f"   ✅ Added: {added_count}")
        logger.info(f"   📝 Updated: {updated_count}")
        logger.info(f"   ➖ Unchanged: {unchanged_count}")
        if new_services_for_branches:
            logger.info(f"   🌿 Branches: {branches_created_count} created for {len(new_services_for_branches)} services")
        if errors:
            logger.warning(f"   ❌ Errors: {len(errors)}")
        
        return (added_count, updated_count, unchanged_count, errors)
    
    except Exception as e:
        logger.error(f"❌ Failed to sync VSAT {vsat_name}: {e}")
        return (0, 0, 0, [str(e)])


def cleanup_orphaned_services(
    active_vsats: Set[str],
    sync_config: Dict[str, Any]
) -> int:
    """
    Remove services from VSATs that are no longer in the config.
    
    Returns:
        Number of services deleted
    """
    logger.info(f"\n🧹 Checking for orphaned services...")
    
    all_services = get_all_services()
    deleted_count = 0
    
    services_by_vsat = {}
    for service in all_services:
        vsat = service.get('vsat', 'unknown')
        if vsat not in services_by_vsat:
            services_by_vsat[vsat] = []
        services_by_vsat[vsat].append(service)
    
    for vsat, services in services_by_vsat.items():
        if vsat not in active_vsats:
            logger.info(f"   🗑️  VSAT '{vsat}' removed from config")
            
            # Safety check
            if len(services) > 10:
                logger.warning(f"      ⚠️  Would delete {len(services)} services - requires manual confirmation")
                continue
            
            for service in services:
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM services WHERE service_id = ?", (service['service_id'],))
                    logger.info(f"      ❌ Deleted: {service['service_id']}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"      ❌ Failed to delete {service['service_id']}: {e}")
    
    if deleted_count > 0:
        logger.info(f"   🗑️  Deleted {deleted_count} orphaned services")
    else:
        logger.info(f"   ✅ No orphaned services found")
    
    return deleted_count


def run_sync(force: bool = False) -> Dict[str, Any]:
    """
    Run full VSAT synchronization.
    
    Args:
        force: Force sync even if config hasn't changed
    
    Returns:
        Sync results summary
    """
    start_time = datetime.now()
    
    logger.info("\n" + "="*80)
    logger.info("🚀 VSAT MASTER CONFIG SYNC")
    logger.info("="*80)
    
    # Initialize database first
    init_db()
    
    # Check if database is empty or if VSATs are missing - if so, force sync
    try:
        existing_services = get_all_services()
        db_is_empty = len(existing_services) == 0
    except:
        db_is_empty = True
    
    if db_is_empty:
        logger.info("📊 Database is empty - forcing full sync")
        force = True
    elif not force and not has_config_changed():
        # Config hasn't changed, but check if VSATs in config exist in DB
        try:
            config = load_vsat_config()
            vsats_in_config = {v['name'] for v in config.get('vsats', []) if v.get('enabled', True)}
            vsats_in_db = {s.get('vsat') for s in existing_services if s.get('vsat')}
            
            missing_vsats = vsats_in_config - vsats_in_db
            if missing_vsats:
                logger.info(f"📊 VSATs in config but not in DB: {missing_vsats} - forcing sync")
                force = True
            else:
                logger.info("✅ Config unchanged and all VSATs present in DB - skipping")
                return {"status": "skipped", "reason": "config_unchanged"}
        except Exception as e:
            logger.warning(f"⚠️  Could not check VSAT presence: {e} - forcing sync")
            force = True
    
    try:
        # Load config
        config = load_vsat_config()
        vsats = config.get('vsats', [])
        sync_config = config.get('sync_config', {})
        filters = config.get('filters', {})
        global_defaults = config.get('global_defaults', {})
        
        # Get GitLab token
        gitlab_token = os.getenv('GITLAB_TOKEN')
        if not gitlab_token:
            raise VSATSyncError("GITLAB_TOKEN not set in environment")
        
        # Create HTTP session with retries
        session = create_http_session()
        
        # Track active VSATs
        active_vsats = {vsat['name'] for vsat in vsats if vsat.get('enabled', True)}
        
        # Sync each VSAT
        total_added = 0
        total_updated = 0
        total_unchanged = 0
        all_errors = []
        
        for vsat in vsats:
            added, updated, unchanged, errors = sync_vsat_services(
                vsat, gitlab_token, sync_config, filters, global_defaults, session
            )
            total_added += added
            total_updated += updated
            total_unchanged += unchanged
            all_errors.extend(errors)
        
        # Cleanup orphaned services
        deleted = cleanup_orphaned_services(active_vsats, sync_config)
        
        # Save config hash
        save_config_hash()
        
        # Summary
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info("\n" + "="*80)
        logger.info("✅ SYNC COMPLETE")
        logger.info("="*80)
        logger.info(f"⏱️  Duration: {duration:.1f}s")
        logger.info(f"📊 Summary:")
        logger.info(f"   ✅ Added: {total_added}")
        logger.info(f"   📝 Updated: {total_updated}")
        logger.info(f"   ➖ Unchanged: {total_unchanged}")
        logger.info(f"   🗑️  Deleted: {deleted}")
        if all_errors:
            logger.warning(f"   ❌ Errors: {len(all_errors)}")
        logger.info("="*80)
        
        return {
            "status": "success",
            "duration": duration,
            "added": total_added,
            "updated": total_updated,
            "unchanged": total_unchanged,
            "deleted": deleted,
            "errors": all_errors
        }
    
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        return {
            "status": "failed",
            "error": str(e)
        }


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VSAT Master Config Sync")
    parser.add_argument('--force', action='store_true', help='Force sync even if config unchanged')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no database changes)')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No database changes will be made")
    
    result = run_sync(force=args.force)
    
    if result['status'] == 'success':
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()