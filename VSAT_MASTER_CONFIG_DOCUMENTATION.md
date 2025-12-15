# VSAT Master Config System - Complete Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Configuration Files](#configuration-files)
4. [Core Components](#core-components)
5. [Execution Flow](#execution-flow)
6. [Detailed Code Walkthrough](#detailed-code-walkthrough)
7. [Automation & Scheduling](#automation--scheduling)
8. [Database Schema](#database-schema)
9. [Environment-Specific Filtering](#environment-specific-filtering)
10. [Branch Creation Logic](#branch-creation-logic)
11. [Error Handling](#error-handling)
12. [Testing & Verification](#testing--verification)
13. [Usage Examples](#usage-examples)
14. [Troubleshooting](#troubleshooting)

---

## 1. System Overview

### What is VSAT Master Config?

The VSAT (Virtual Service Access Terminal) Master Config system is an **automated service discovery and management platform** that:

- 📡 **Discovers** services automatically from GitLab groups/users
- 🗄️ **Syncs** service metadata to a SQLite database
- 🌿 **Creates** golden branches with environment-specific configurations
- 🔄 **Monitors** config file changes in real-time
- ⏰ **Schedules** weekly full syncs automatically
- 🧹 **Cleans up** orphaned services

### Key Features

✅ **Zero-touch automation** - Just run `main.py` and everything works  
✅ **Real-time sync** - Detects config changes instantly  
✅ **Parallel processing** - Fast branch creation across multiple services  
✅ **Environment filtering** - Smart config file segregation (prod/alpha/beta1/beta2)  
✅ **Duplicate prevention** - Validates VSAT IDs to prevent duplicates  
✅ **Robust error handling** - Retries, logging, and graceful failures  

---

## 2. Architecture

### System Components

```
┌────────────────────────────────────────────────────────────────┐
│                         main.py                                 │
│               (FastAPI Server + VSAT Automation)                │
└───────────────────┬────────────────────────────────────────────┘
                    │
        ┌───────────┴────────────────┐
        │                            │
┌───────▼─────────┐         ┌────────▼──────────┐
│  APScheduler    │         │    watchdog       │
│  (Weekly Sync)  │         │  (File Monitor)   │
└───────┬─────────┘         └────────┬──────────┘
        │                            │
        └────────────┬───────────────┘
                     │
          ┌──────────▼──────────────┐
          │   scripts/vsat_sync.py  │
          │   (Core Sync Engine)    │
          └──────────┬──────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────────────┐
│ Config Files │ │ GitLab  │ │   SQLite DB     │
│ vsat_*.yaml  │ │   API   │ │   (Services)    │
└──────────────┘ └─────────┘ └─────────────────┘
```

### Data Flow

```
1. Config File Change Detected
   ↓
2. Load & Validate Config (vsat_master.yaml + vsat_config.yaml)
   ↓
3. Check if Sync Needed (hash comparison, DB checks)
   ↓
4. For Each VSAT:
   ├─ Fetch Projects from GitLab API
   ├─ Filter Projects (exclude patterns, main branch check)
   ├─ Parallel Branch Existence Check
   ├─ Add/Update Services in Database
   └─ Queue New Services for Branch Creation
   ↓
5. Parallel Golden Branch Creation
   ├─ 1 Snapshot Branch (all configs)
   └─ 4 Environment Branches (filtered configs)
   ↓
6. Cleanup Orphaned Services
   ↓
7. Save Config Hash (for change detection)
```

---

## 3. Configuration Files

### 3.1 `config/vsat_master.yaml` - Simple VSAT List

**Purpose**: Define which VSATs to monitor  
**Location**: `config/vsat_master.yaml`

```yaml
# VSAT Master Configuration - Simple & Minimal
# This file defines which VSATs to monitor and sync
# Keep it simple - only essential VSAT information here
# Detailed configuration is in vsat_config.yaml

version: "1.0"

# VSATs to monitor and sync
# Format: name, url, enabled (that's it!)
vsats:
  - name: saja9l7
    url: https://gitlab.verizon.com/saja9l7
    enabled: true

  # Add more VSATs here:
  # - name: another_team
  #   url: https://gitlab.verizon.com/another_team
  #   enabled: true
```

**Fields Explained**:
- **`name`** (required): Unique VSAT identifier (must be unique across all VSATs)
- **`url`** (required): GitLab group or user URL
- **`enabled`** (optional, default: true): Enable/disable this VSAT

**Validation Rules**:
1. ✅ Each VSAT must have a unique `name`
2. ✅ Duplicate names are rejected immediately
3. ✅ Missing `name` field throws error
4. ✅ File must have `vsats` section

---

### 3.2 `config/vsat_config.yaml` - Detailed Settings

**Purpose**: Global defaults, sync settings, filters, notifications  
**Location**: `config/vsat_config.yaml`

```yaml
# VSAT Configuration - Detailed Settings
# This file contains all detailed configuration for VSAT automation
# Most settings have sensible defaults - you can remove sections you don't need

version: "1.0"

# Default service configuration (applied to all VSATs unless overridden)
defaults:
  main_branch: main
  environments:
    - prod
    - alpha
    - beta1
    - beta2
  config_paths:
    - "*.yml"
    - "*.yaml"
    - "*.properties"
    - "*.toml"
    - "*.ini"
    - "*.cfg"
    - "*.conf"
    - "*.config"
    - "Dockerfile"
    - "docker-compose.yml"
    - "pom.xml"
    - "build.gradle"
    - "requirements.txt"

# VSAT-specific overrides (optional - remove if not needed)
vsat_overrides: {}
  # Example (uncomment to use):
  # saja9l7:
  #   main_branch: master
  #   environments: [prod, dev]

# Sync behavior configuration
sync:
  # Weekly sync schedule (cron: minute hour day-of-week, Sunday=0)
  weekly_schedule: "0 2 0"  # Every Sunday at 2 AM
  
  # Branch creation
  create_golden_branches: true
  parallel_branch_creation: true
  max_branch_workers: 5
  
  # API settings
  api_delay: 0.5  # seconds between API calls
  max_concurrent_requests: 10

# Service filtering rules
filters:
  # Exclude repos matching these patterns
  exclude_patterns:
    - "*-archived"
    - "*-deprecated"
    - "test-*"
    - "*-backup"
  
  # Only include repos with main branch
  require_main_branch: true

# Notification settings
notifications:
  enabled: true
  channels:
    - type: log
      level: info
    - type: database
      table: sync_logs
```

**Sections Explained**:

#### `defaults` - Service Defaults
- **`main_branch`**: Default branch name (usually `main` or `master`)
- **`environments`**: List of environments for branch creation
- **`config_paths`**: File patterns to consider as "config files"

#### `vsat_overrides` - Per-VSAT Customization
Override defaults for specific VSATs (rarely needed)

#### `sync` - Sync Behavior
- **`weekly_schedule`**: Cron expression for scheduled syncs (minute hour day-of-week)
- **`create_golden_branches`**: Enable/disable branch creation
- **`parallel_branch_creation`**: Use parallel processing (recommended)
- **`max_branch_workers`**: Concurrent services for branch creation
- **`api_delay`**: Delay between GitLab API calls (rate limiting)

#### `filters` - Project Filtering
- **`exclude_patterns`**: Skip repos matching these patterns
- **`require_main_branch`**: Only include repos with `main` branch

#### `notifications` - Alerts
- **`enabled`**: Enable notifications
- **`channels`**: Where to send notifications (log, database, slack, etc.)

---

### 3.3 Config Hash File (Auto-Generated)

**Purpose**: Track config changes for incremental syncs  
**Location**: `config/.vsat_master_hash`  
**Format**: SHA256 hash of both config files

```
a3f5c8d9e2b1f4a7c6d8e9f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1
```

**How It Works**:
1. On sync completion, hash of config files is saved
2. On next run, current hash is compared with saved hash
3. If different → config changed → force sync
4. If same → check other conditions (DB empty, VSATs missing, etc.)

---

## 4. Core Components

### 4.1 `main.py` - FastAPI Server + VSAT Automation

**Location**: `main.py` (lines 1840-1923)

**Responsibilities**:
- Start FastAPI web server
- Initialize VSAT automation on startup
- Schedule weekly syncs
- Monitor config file changes
- Gracefully shutdown on stop

**Key Functions**:

#### `start_vsat_automation()` (Lines 1840-1893)
```python
def start_vsat_automation():
    """Start VSAT automation: scheduler + file watcher"""
    global scheduler, config_observer
    
    # 1. Run initial sync
    logger.info("Running initial VSAT sync...")
    run_sync()
    
    # 2. Setup weekly scheduler
    scheduler = BackgroundScheduler()
    weekly_cron = config.get('sync_config', {}).get('weekly_schedule', '0 2 0')
    minute, hour, day_of_week = weekly_cron.split()
    scheduler.add_job(
        run_sync,
        trigger=CronTrigger(
            day_of_week=day_of_week,
            hour=int(hour),
            minute=int(minute)
        ),
        id='weekly_vsat_sync',
        name='Weekly VSAT Sync',
        replace_existing=True
    )
    scheduler.start()
    
    # 3. Setup file watcher (watchdog)
    event_handler = ConfigFileChangeHandler()
    config_observer = Observer()
    config_observer.schedule(
        event_handler,
        path=str(MASTER_CONFIG_FILE.parent),
        recursive=False
    )
    config_observer.start()
```

**Breakdown**:
1. **Line 1847-1848**: Run initial sync on startup
2. **Lines 1851-1865**: Configure APScheduler for weekly syncs
3. **Lines 1868-1889**: Setup watchdog for real-time file monitoring

#### `ConfigFileChangeHandler` (Lines 1820-1838)
```python
class ConfigFileChangeHandler(FileSystemEventHandler):
    """Watch for config file changes and trigger sync"""
    
    def __init__(self):
        self.last_sync = datetime.now()
        self.debounce_seconds = 5  # Prevent rapid re-syncs
    
    def on_modified(self, event):
        # Only watch specific config files
        if event.src_path.endswith(('vsat_master.yaml', 'vsat_config.yaml')):
            now = datetime.now()
            if (now - self.last_sync).total_seconds() > self.debounce_seconds:
                logger.info(f"Config file changed: {event.src_path}")
                logger.info("Triggering VSAT sync...")
                run_sync()
                self.last_sync = now
```

**Debouncing**: Prevents multiple syncs if file is saved multiple times rapidly

---

### 4.2 `scripts/vsat_sync.py` - Core Sync Engine

**Location**: `scripts/vsat_sync.py` (980 lines)

This is the **heart** of the system. Let's walk through every major function.

---

#### 4.2.1 `load_vsat_config()` - Load & Merge Configs

**Lines**: 68-162

**Purpose**: Load both config files, merge them, validate, and detect duplicates

```python
def load_vsat_config() -> Dict[str, Any]:
    """
    Load and merge VSAT master config (simple) with detailed config.
    
    Master config (vsat_master.yaml): Simple - just VSAT list
    Detailed config (vsat_config.yaml): All detailed settings
    """
```

**Step-by-Step**:

```python
# STEP 1: Load master config (Lines 76-81)
if not MASTER_CONFIG_FILE.exists():
    raise VSATSyncError(f"Master config file not found: {MASTER_CONFIG_FILE}")

with open(MASTER_CONFIG_FILE, 'r') as f:
    master_config = yaml.safe_load(f) or {}
```
→ Read `vsat_master.yaml` and parse YAML

```python
# STEP 2: Validate required fields (Lines 83-85)
if 'vsats' not in master_config:
    raise VSATSyncError("Master config file missing 'vsats' section")
```
→ Ensure `vsats` key exists

```python
# STEP 3: Check for duplicate VSAT names (Lines 87-104)
vsat_names = []
duplicates = []
for vsat in master_config['vsats']:
    vsat_name = vsat.get('name')
    if not vsat_name:
        raise VSATSyncError("VSAT entry missing 'name' field")
    
    if vsat_name in vsat_names:
        duplicates.append(vsat_name)
    else:
        vsat_names.append(vsat_name)

if duplicates:
    raise VSATSyncError(
        f"Duplicate VSAT IDs found in config: {', '.join(set(duplicates))}. "
        f"Each VSAT must have a unique name."
    )
```
→ **NEW**: Validate no duplicate VSAT IDs (YOUR FIX!)

```python
# STEP 4: Load detailed config (Lines 108-116)
detailed_config = {}
if DETAILED_CONFIG_FILE.exists():
    with open(DETAILED_CONFIG_FILE, 'r') as f:
        detailed_config = yaml.safe_load(f) or {}
    logger.info("✅ Loaded detailed config")
else:
    logger.warning(f"⚠️  Detailed config not found: {DETAILED_CONFIG_FILE}")
    logger.warning("   Using minimal defaults")
```
→ Read `vsat_config.yaml` (optional, has defaults)

```python
# STEP 5: Merge configs (Lines 118-142)
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
```
→ Combine both configs, apply defaults if sections missing

```python
# STEP 6: Apply VSAT-specific overrides (Lines 144-155)
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
```
→ Apply per-VSAT overrides from `vsat_overrides` section

```python
return merged_config
```

**Output**: Fully merged configuration dictionary

---

#### 4.2.2 Config Change Detection Functions

**`get_config_hash()`** (Lines 165-179)
```python
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
```
→ SHA256 hash of both config files

**`has_config_changed()`** (Lines 182-191)
```python
def has_config_changed() -> bool:
    """Check if config file has changed since last sync"""
    if not CONFIG_HASH_FILE.exists():
        return True  # First run
    
    with open(CONFIG_HASH_FILE, 'r') as f:
        old_hash = f.read().strip()
    
    current_hash = get_config_hash()
    return old_hash != current_hash
```
→ Compare current hash with saved hash

**`save_config_hash()`** (Lines 194-198)
```python
def save_config_hash():
    """Save current config hash"""
    CONFIG_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_HASH_FILE, 'w') as f:
        f.write(get_config_hash())
```
→ Save hash after successful sync

---

#### 4.2.3 `create_http_session()` - HTTP Session with Retries

**Lines**: 201-216

```python
def create_http_session() -> requests.Session:
    """Create requests session with retry logic"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,                               # Max 3 retries
        backoff_factor=2,                      # 2s, 4s, 8s delays
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP errors
        allowed_methods=["GET", "POST"]
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,                   # Connection pooling
        pool_maxsize=10
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session
```

**Benefits**:
- ✅ Automatic retries on transient errors
- ✅ Exponential backoff (prevents hammering API)
- ✅ Connection pooling (reuses TCP connections)

---

#### 4.2.4 `fetch_vsat_projects()` - Fetch Projects from GitLab

**Lines**: 283-357

**Purpose**: Fetch all projects from a VSAT (supports both GitLab groups and user namespaces)

```python
def fetch_vsat_projects(
    vsat_name: str,
    vsat_url: str,
    gitlab_token: str,
    filters: Dict[str, Any],
    session: requests.Session
) -> List[Dict[str, Any]]:
```

**Step-by-Step**:

```python
# STEP 1: Extract GitLab base URL (Line 298)
gitlab_base = vsat_url.replace(f"/{vsat_name}", "")
# Example: "https://gitlab.verizon.com/saja9l7" → "https://gitlab.verizon.com"
```

```python
# STEP 2: Try group API first (Lines 306-321)
while True:
    url = f"{gitlab_base}/api/v4/groups/{vsat_name}/projects"
    params = {
        "per_page": 100,
        "page": page,
        "include_subgroups": True,
        "archived": False
    }
    
    response = session.get(url, headers=headers, params=params, timeout=30)
    
    # If first page returns 404, it's not a group - try user namespace
    if response.status_code == 404 and page == 1:
        logger.info(f"   Not a group, trying user namespace API...")
        return fetch_user_projects(vsat_name, gitlab_base, gitlab_token, filters, session)
```
→ If group API returns 404 on first page, fallback to user API

```python
# STEP 3: Apply filters (Lines 346-348)
filtered_projects = apply_filters(all_projects, filters)
logger.info(f"   After filtering: {len(filtered_projects)} projects")
```
→ Exclude repos matching patterns

```python
# STEP 4: Check for main branch (optimized) (Lines 350-353)
projects_with_main = check_main_branch_parallel(
    filtered_projects, gitlab_token, session
)
logger.info(f"   With main branch: {len(projects_with_main)} projects")
```
→ Parallel check for `main` branch existence

**Output**: List of project dicts with `main` branch

---

#### 4.2.5 `fetch_user_projects()` - User Namespace Support

**Lines**: 219-280

**Purpose**: Fetch projects from a user namespace (not a group)

**Why Needed**: GitLab has two types of namespaces:
- **Groups** (`/api/v4/groups/{name}/projects`) - Teams/organizations
- **Users** (`/api/v4/users/{username}/projects`) - Individual users

The system auto-detects which one based on API response.

```python
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
    """
    logger.info(f"   '{username}' is a user namespace, fetching user projects...")
    
    # Use user-specific API endpoint
    url = f"{gitlab_base}/api/v4/users/{username}/projects"
    params = {
        "per_page": 100,
        "page": page,
        "owned": True,      # Only projects owned by user
        "archived": False
    }
    # ... paginated fetching ...
```

**Auto-Detection Flow**:
```
1. Try: GET /api/v4/groups/saja9l7/projects
   ↓
2. Response: 404 Not Found
   ↓
3. Fallback: GET /api/v4/users/saja9l7/projects
   ↓
4. Response: 200 OK → Success!
```

---

#### 4.2.6 `check_main_branch_parallel()` - Parallel Branch Checking

**Lines**: 394-458

**Purpose**: Check which projects have `main` branch (optimized with parallelization)

**Optimization Strategy**:

```python
# STEP 1: Quick filter - Projects where default_branch == 'main' (Lines 406-412)
projects_with_main_default = []
projects_to_check = []

for project in projects:
    if project.get('default_branch') == 'main':
        project['has_main_branch'] = True
        projects_with_main_default.append(project)
    else:
        projects_to_check.append(project)
```
→ **Fast path**: If default branch is `main`, no API call needed!

```python
# STEP 2: Parallel check for remaining projects (Lines 422-456)
def check_branch(project):
    """Check if project has main branch"""
    gitlab_base = # ... extract from project URL ...
    api_url = f"{gitlab_base}/api/v4/projects/{project_id}/repository/branches/main"
    response = session.get(api_url, headers=headers, timeout=10)
    return response.status_code == 200

with ThreadPoolExecutor(max_workers=25) as executor:
    futures = {executor.submit(check_branch, proj): proj for proj in projects_to_check}
    for future in as_completed(futures):
        result = future.result()
        if result:
            filtered_projects.append(result)
```
→ **Parallel check**: 25 concurrent API calls

**Performance**:
- Before: 100 repos × 0.5s = 50 seconds
- After: 100 repos ÷ 25 workers = 2 seconds!

---

#### 4.2.7 `sync_vsat_services()` - Sync Services for a VSAT

**Lines**: 553-763

**Purpose**: Sync all services from a VSAT to the database and create golden branches

**This is the MOST IMPORTANT function. Let's break it down in detail.**

```python
def sync_vsat_services(
    vsat: Dict[str, Any],
    gitlab_token: str,
    sync_config: Dict[str, Any],
    filters: Dict[str, Any],
    global_defaults: Dict[str, Any],
    session: requests.Session
) -> Tuple[int, int, int, List[str]]:
```

**Phase 1: Fetch Projects (Lines 578-592)**

```python
# Check if VSAT is enabled
if not vsat.get('enabled', True):
    logger.info(f"⏭️  Skipping disabled VSAT: {vsat_name}")
    return (0, 0, 0, [])

# Fetch projects from GitLab
projects = fetch_vsat_projects(
    vsat_name, vsat_url, gitlab_token, filters, session
)

# Threshold check
if len(projects) < sync_config.get('min_services_threshold', 1):
    logger.warning(f"⚠️  VSAT {vsat_name} has only {len(projects)} services (below threshold)")
```

**Phase 2: Process Services (Lines 599-683)**

```python
# Get service config (VSAT-specific or global defaults)
service_config = vsat.get('service_config', {})
main_branch = service_config.get('main_branch', global_defaults.get('main_branch', 'main'))
environments = service_config.get('environments', global_defaults.get('environments', ['prod']))
config_paths = service_config.get('config_paths', global_defaults.get('config_paths', ['*.yml']))

added_count = 0
updated_count = 0
unchanged_count = 0
new_services_for_branches = []  # Queue for branch creation

# Process each project
for project in projects:
    service_id = f"{vsat_name}_{project['path']}"
    service_name = project['name']
    repo_url = project['http_url_to_repo']
    
    # Check if service exists
    existing = get_service_by_id(service_id)
```

**For Existing Services (Lines 610-653)**:

```python
if existing:
    # Update if repo_url or main_branch changed
    if existing['repo_url'] != repo_url or existing['main_branch'] != main_branch:
        logger.info(f"   📝 Updating: {service_id}")
        add_service(...)  # Updates service in DB
        updated_count += 1
    else:
        unchanged_count += 1
    
    # CHECK IF SERVICE HAS GOLDEN BRANCHES (Lines 629-653)
    if sync_config.get('create_golden_branches', True):
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
        
        # If no branches, queue for creation
        if not has_branches:
            logger.info(f"   🌿 Service exists but has no branches, queuing: {service_id}")
            new_services_for_branches.append({
                'service_id': service_id,
                'repo_url': repo_url,
                'main_branch': main_branch,
                'environments': environments,
                'config_paths': config_paths
            })
```
→ **YOUR FIX**: Services without branches are queued for creation!

**For New Services (Lines 654-678)**:

```python
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
    
    # Queue for branch creation
    if sync_config.get('create_golden_branches', True):
        new_services_for_branches.append({
            'service_id': service_id,
            'repo_url': repo_url,
            'main_branch': main_branch,
            'environments': environments,
            'config_paths': config_paths
        })
```

**Phase 3: Parallel Golden Branch Creation (Lines 685-748)**

```python
if new_services_for_branches:
    logger.info(f"\n   🌿 Creating golden branches for {len(new_services_for_branches)} services...")
    logger.info(f"      ⚡ Using parallel execution (max {sync_config.get('max_branch_workers', 10)} concurrent services)")
    
    max_workers = sync_config.get('max_branch_workers', 10)
    
    def create_branches_for_service(service_info):
        """Task to create branches for a single service"""
        branches = create_golden_branches_parallel(
            service_info['service_id'],
            service_info['repo_url'],
            service_info['main_branch'],
            service_info['environments'],
            service_info['config_paths'],
            gitlab_token
        )
        
        if branches:
            return (service_id, True, len(branches))
        else:
            return (service_id, False, 0)
    
    # Execute branch creation for all services in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(create_branches_for_service, service_info): service_info
            for service_info in new_services_for_branches
        }
        
        for future in as_completed(futures):
            service_id, success, branch_count = future.result()
            if success:
                branches_created_count += branch_count
            
            # Progress logging every 10 services
            if completed % 10 == 0:
                logger.info(f"      📊 Progress: {completed}/{len(new_services_for_branches)}")
```

**Two Levels of Parallelization**:
1. **Service-level**: Multiple services processed concurrently (10 workers)
2. **Branch-level**: 5 branches per service created concurrently (inside `create_golden_branches_parallel`)

**Performance**:
- Sequential: 10 services × 5 branches × 10s = 500 seconds
- Parallel: ~50-100 seconds (5-10x faster!)

---

#### 4.2.8 `create_golden_branches_parallel()` - Create 5 Branches

**Lines**: 461-550

**Purpose**: Create 5 golden branches for a service in parallel

```python
def create_golden_branches_parallel(
    service_id: str,
    repo_url: str,
    main_branch: str,
    environments: List[str],
    config_paths: List[str],
    gitlab_token: str
) -> Dict[str, str]:
```

**Branches Created**:
1. **`golden_snapshot_YYYYMMDD_HHMMSS_hash`** - Complete snapshot (all config files)
2. **`golden_prod_YYYYMMDD_HHMMSS_hash`** - Prod-specific configs only
3. **`golden_alpha_YYYYMMDD_HHMMSS_hash`** - Alpha-specific configs only
4. **`golden_beta1_YYYYMMDD_HHMMSS_hash`** - Beta1-specific configs only
5. **`golden_beta2_YYYYMMDD_HHMMSS_hash`** - Beta2-specific configs only

**Code Walkthrough**:

```python
# Prepare all branch creation tasks (Lines 505-515)
tasks = []

# Task 1: Complete snapshot
snapshot_branch = f"golden_snapshot_{timestamp}_{short_hash}"
tasks.append(('snapshot', snapshot_branch, None))

# Tasks 2-5: Environment-specific branches
for env in environments:
    env_branch = f"golden_{env}_{timestamp}_{short_hash}"
    tasks.append(('env', env_branch, env))
```

```python
# Execute all branch creations in parallel (Lines 518-543)
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
```

**Branch Creation Functions** (called internally):

```python
def create_branch_task(branch_type, branch_name, environment=None):
    if branch_type == 'snapshot':
        success = create_config_only_branch(
            repo_url=repo_url,
            main_branch=main_branch,
            new_branch_name=branch_name,
            config_paths=config_paths,
            gitlab_token=gitlab_token
        )
    else:
        success = create_env_specific_config_branch(
            repo_url=repo_url,
            main_branch=main_branch,
            new_branch_name=branch_name,
            environment=environment,
            config_paths=config_paths,
            gitlab_token=gitlab_token
        )
```

These functions are in `shared/git_operations.py` (detailed in section 4.4).

---

#### 4.2.9 `cleanup_orphaned_services()` - Remove Deleted VSATs

**Lines**: 766-812

**Purpose**: Delete services whose VSAT is no longer in config

```python
def cleanup_orphaned_services(
    active_vsats: Set[str],
    sync_config: Dict[str, Any]
) -> int:
    """
    Remove services from VSATs that are no longer in the config.
    """
    logger.info(f"\n🧹 Checking for orphaned services...")
    
    all_services = get_all_services()
    deleted_count = 0
    
    # Group services by VSAT
    services_by_vsat = {}
    for service in all_services:
        vsat = service.get('vsat', 'unknown')
        if vsat not in services_by_vsat:
            services_by_vsat[vsat] = []
        services_by_vsat[vsat].append(service)
    
    # Delete services for inactive VSATs
    for vsat, services in services_by_vsat.items():
        if vsat not in active_vsats:
            logger.info(f"   🗑️  VSAT '{vsat}' removed from config")
            
            # Safety check: Don't auto-delete if > 10 services
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
    
    return deleted_count
```

**Safety Mechanism**: Won't auto-delete if > 10 services (prevents accidental bulk deletion)

---

#### 4.2.10 `run_sync()` - Main Sync Orchestrator

**Lines**: 815-955

**Purpose**: The main entry point that orchestrates the entire sync process

**This function contains ALL the checks you asked about!**

```python
def run_sync(force: bool = False) -> Dict[str, Any]:
    """
    Run full VSAT synchronization.
    
    Args:
        force: Force sync even if config hasn't changed
    """
    start_time = datetime.now()
    
    logger.info("\n" + "="*80)
    logger.info("🚀 VSAT MASTER CONFIG SYNC")
    logger.info("="*80)
    
    # Initialize database first
    init_db()
```

**CHECK #1: Database Empty Check (Lines 834-843)**

```python
# Check if database is empty
try:
    existing_services = get_all_services()
    db_is_empty = len(existing_services) == 0
except:
    db_is_empty = True

if db_is_empty:
    logger.info("📊 Database is empty - forcing full sync")
    force = True
```
→ If no services exist, force sync

**CHECK #2: Force Flag (Line 844)**

```python
elif not force and not has_config_changed():
```
→ If `force=True`, skip all other checks and sync

**CHECK #3: Config Hash Check (Line 844)**

```python
elif not force and not has_config_changed():
    # Config hasn't changed, but check other conditions...
```
→ If config hash changed, sync runs

**CHECK #4: Missing VSAT Check (Lines 846-854)**

```python
# Config hasn't changed, but check if VSATs in config exist in DB
config = load_vsat_config()
vsats_in_config = {v['name'] for v in config.get('vsats', []) if v.get('enabled', True)}
vsats_in_db = {s.get('vsat') for s in existing_services if s.get('vsat')}

missing_vsats = vsats_in_config - vsats_in_db
if missing_vsats:
    logger.info(f"📊 VSATs in config but not in DB: {missing_vsats} - forcing sync")
    force = True
```
→ If new VSATs in config, force sync

**CHECK #5: Services Without Active Branches (Lines 856-876)**

```python
# Check if any existing services are missing golden branches
services_without_branches = []
for service in existing_services:
    service_id = service.get('service_id')
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM golden_branches 
                WHERE service_name = ? 
                AND branch_type = 'golden' 
                AND is_active = 1
            """, (service_id,))
            has_branches = cursor.fetchone()['count'] > 0
            if not has_branches:
                services_without_branches.append(service_id)
    except:
        pass

if services_without_branches:
    logger.info(f"🌿 Found {len(services_without_branches)} services without golden branches - forcing sync")
    logger.info(f"   Services needing branches: {', '.join(services_without_branches[:5])}{'...' if len(services_without_branches) > 5 else ''}")
    force = True
```
→ **YOUR KEY FIX**: If any service lacks active branches, force sync!

**SKIP CONDITION (Lines 877-879)**

```python
else:
    logger.info("✅ Config unchanged, all VSATs present, and all services have golden branches - skipping")
    return {"status": "skipped", "reason": "config_unchanged_and_branches_exist"}
```
→ Only skips if ALL checks pass

**Sync Execution (Lines 884-922)**

```python
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
    logger.info("✅ SYNC COMPLETE")
    logger.info(f"⏱️  Duration: {duration:.1f}s")
    logger.info(f"📊 Summary:")
    logger.info(f"   ✅ Added: {total_added}")
    logger.info(f"   📝 Updated: {total_updated}")
    logger.info(f"   ➖ Unchanged: {total_unchanged}")
    logger.info(f"   🗑️  Deleted: {deleted}")
```

---

### 4.3 `scripts/migrate_add_services_table.py` - Migration Script

**Location**: `scripts/migrate_add_services_table.py` (388 lines)

**Purpose**: One-time script to:
1. Create services table
2. Add default service (`cxp_ptg_adapter`)
3. Create 5 golden branches for that service

**Usage**:
```bash
python scripts/migrate_add_services_table.py
```

**Key Function**: `create_golden_branches_for_service()` (Lines 110-223)

This is similar to `create_golden_branches_parallel()` in `vsat_sync.py`, but with more verbose logging for manual runs.

---

### 4.4 `shared/env_filter.py` - Environment Filtering

**Location**: `shared/env_filter.py` (171 lines)

**Purpose**: Categorize config files by environment to prevent cross-environment leaks

**Core Function**: `categorize_file_by_environment()` (Lines 15-75)

```python
def categorize_file_by_environment(filepath: str) -> List[str]:
    """
    Determine which environments a configuration file belongs to.
    
    Rules:
    - Files with *prod* in name/path → ONLY prod
    - Files with *alpha* in name/path → ONLY alpha  
    - Files with *beta1* or *T1.yml in name/path → ONLY beta1
    - Files with *beta2*, *T2.yml, or *T3.yml in name/path → ONLY beta2
    - Files with *T4.yml, *T5.yml, *T6.yml in name/path → ONLY beta2 (default)
    - Files with no environment marker → ALL environments (global/service-level)
    """
    filepath_lower = str(filepath).lower().replace('\\', '/')
    filename = Path(filepath).name.lower()
    
    # Rule 1: Prod-specific files
    if 'prod' in filepath_lower:
        return ['prod']
    
    # Rule 2: Alpha-specific files
    if 'alpha' in filepath_lower:
        return ['alpha']
    
    # Rule 3: Beta1-specific files
    if 'beta1' in filepath_lower or filename.endswith('t1.yml'):
        return ['beta1']
    
    # Rule 4: Beta2-specific files (including T2, T3, T4, T5, T6)
    if ('beta2' in filepath_lower or 
        filename.endswith('t2.yml') or 
        filename.endswith('t3.yml') or
        filename.endswith('t4.yml') or
        filename.endswith('t5.yml') or
        filename.endswith('t6.yml')):
        return ['beta2']
    
    # Rule 5: Global/service-level files (no environment marker)
    return ['prod', 'alpha', 'beta1', 'beta2']
```

**Examples**:

| File Path | Environment(s) |
|-----------|---------------|
| `application-prod.yml` | `['prod']` |
| `config/alpha/settings.yml` | `['alpha']` |
| `helm/values-T1.yml` | `['beta1']` |
| `helm/values-T2.yml` | `['beta2']` |
| `application.yml` | `['prod', 'alpha', 'beta1', 'beta2']` |

**Filter Function**: `filter_files_for_environment()` (Lines 78-97)

```python
def filter_files_for_environment(file_list: List[str], environment: str) -> List[str]:
    """
    Filter a list of files to only include those that belong to a specific environment.
    """
    filtered = []
    
    for filepath in file_list:
        envs = categorize_file_by_environment(filepath)
        if environment in envs:
            filtered.append(filepath)
    
    logger.info(f"Environment '{environment}': {len(filtered)}/{len(file_list)} files included")
    return filtered
```

---

### 4.5 `shared/git_operations.py` - Git Branch Operations

**Location**: `shared/git_operations.py` (822 lines)

**Key Functions**:

#### `create_config_only_branch()` - Complete Snapshot Branch

Creates a branch with ALL config files (no filtering)

#### `create_env_specific_config_branch()` - Environment-Specific Branch

Creates a branch with ONLY environment-specific config files

**Steps**:
1. Clone repo
2. Checkout main branch
3. Setup sparse checkout (config files only)
4. **Filter files by environment** (using `env_filter.py`)
5. Create orphan branch
6. Remove non-environment files
7. Commit with message: `"Merge branch '{branch_name}'"`
8. Push to GitLab

**Commit Message Format** (Lines 350-370):

```python
# Commit message format matches GitLab's expectation
commit_message = f"Merge branch '{new_branch_name}'\n\n" \
                f"Environment-specific golden branch for '{environment}'.\n" \
                f"Contains only config files relevant to this environment."
```

**Why**: GitLab requires commit messages starting with `"Merge branch "` for certain policies.

---

## 5. Execution Flow

### 5.1 First Run (Database Empty)

```
1. main.py starts
   ↓
2. startup_event() called
   ↓
3. start_vsat_automation()
   ├─ run_sync() (initial sync)
   │  ├─ CHECK #1: DB empty → force = True
   │  ├─ Load config
   │  ├─ For each VSAT:
   │  │  ├─ Fetch projects from GitLab
   │  │  ├─ Add services to DB
   │  │  └─ Create 5 golden branches per service (parallel)
   │  └─ Save config hash
   │
   ├─ Setup APScheduler (weekly sync)
   └─ Setup watchdog (file monitor)
   ↓
4. Server running, waiting for:
   - Weekly cron trigger
   - Config file change
   - Manual API call
```

### 5.2 Config File Change (Real-time Sync)

```
1. User edits vsat_master.yaml
   ↓
2. watchdog detects change
   ↓
3. ConfigFileChangeHandler.on_modified()
   ├─ Check: 5 seconds since last sync? (debounce)
   └─ run_sync()
      ├─ CHECK #3: Config hash changed → sync
      ├─ Load config
      ├─ Fetch projects
      ├─ Add/update/delete services
      ├─ Create branches for new services
      └─ Save new hash
```

### 5.3 Weekly Scheduled Sync

```
1. Sunday 2:00 AM (cron: "0 2 0")
   ↓
2. APScheduler triggers
   ↓
3. run_sync(force=False)
   ├─ CHECK #3: Config unchanged?
   ├─ CHECK #4: All VSATs present?
   ├─ CHECK #5: All services have branches?
   └─ If any check fails → sync
      Otherwise → skip
```

### 5.4 Service Without Branches (Edge Case)

```
1. Service exists in DB but no golden branches
   ↓
2. Weekly sync runs
   ↓
3. run_sync()
   ├─ CHECK #5: Query golden_branches table
   │  └─ Found service with 0 active branches
   ├─ force = True
   ├─ sync_vsat_services()
   │  └─ For existing service:
   │     └─ CHECK #10: has_branches = False
   │        └─ Queue for branch creation
   └─ create_golden_branches_parallel()
      └─ Create 5 branches
```

---

## 6. Detailed Code Walkthrough

### 6.1 Every Line of `load_vsat_config()` Explained

```python
def load_vsat_config() -> Dict[str, Any]:
```
→ Function signature: Returns merged configuration dictionary

```python
    try:
```
→ Start try-except block for error handling

```python
        if not MASTER_CONFIG_FILE.exists():
            raise VSATSyncError(f"Master config file not found: {MASTER_CONFIG_FILE}")
```
→ **Line 77-78**: Check if `config/vsat_master.yaml` exists, raise error if missing

```python
        with open(MASTER_CONFIG_FILE, 'r') as f:
            master_config = yaml.safe_load(f) or {}
```
→ **Line 80-81**: Open file, parse YAML, fallback to empty dict if None

```python
        if 'vsats' not in master_config:
            raise VSATSyncError("Master config file missing 'vsats' section")
```
→ **Line 84-85**: Validate required 'vsats' key exists

```python
        vsat_names = []
        duplicates = []
```
→ **Line 88-89**: Initialize lists to track names and duplicates

```python
        for vsat in master_config['vsats']:
```
→ **Line 90**: Loop through each VSAT entry

```python
            vsat_name = vsat.get('name')
```
→ **Line 91**: Extract 'name' field (None if missing)

```python
            if not vsat_name:
                raise VSATSyncError("VSAT entry missing 'name' field")
```
→ **Line 92-93**: Validate 'name' field exists

```python
            if vsat_name in vsat_names:
                duplicates.append(vsat_name)
```
→ **Line 95-96**: If name already seen, add to duplicates list

```python
            else:
                vsat_names.append(vsat_name)
```
→ **Line 97-98**: Otherwise, add to names list

```python
        if duplicates:
            raise VSATSyncError(
                f"Duplicate VSAT IDs found in config: {', '.join(set(duplicates))}. "
                f"Each VSAT must have a unique name."
            )
```
→ **Line 100-104**: If duplicates found, raise error with list of duplicate names

```python
        logger.info(f"✅ Loaded master config: {len(master_config['vsats'])} VSATs")
```
→ **Line 106**: Log success message with count

```python
        detailed_config = {}
        if DETAILED_CONFIG_FILE.exists():
            with open(DETAILED_CONFIG_FILE, 'r') as f:
                detailed_config = yaml.safe_load(f) or {}
            logger.info("✅ Loaded detailed config")
        else:
            logger.warning(f"⚠️  Detailed config not found: {DETAILED_CONFIG_FILE}")
            logger.warning("   Using minimal defaults")
```
→ **Line 109-116**: Load `vsat_config.yaml` if exists, otherwise use defaults

```python
        merged_config = {
            'vsats': master_config['vsats'],
```
→ **Line 119-120**: Start merged config with VSAT list from master

```python
            'global_defaults': detailed_config.get('defaults', {
                'main_branch': 'main',
                'environments': ['prod'],
                'config_paths': ['*.yml', '*.yaml', '*.properties']
            }),
```
→ **Line 121-125**: Extract defaults section, use hardcoded defaults if missing

```python
            'sync_config': detailed_config.get('sync', {
                'create_golden_branches': True,
                'parallel_branch_creation': True,
                'max_branch_workers': 5,
                'weekly_sync_schedule': '0 2 0',
                'min_services_threshold': 1,
                'max_delete_percentage': 50
            }),
```
→ **Line 126-133**: Extract sync settings, use hardcoded defaults if missing

```python
            'filters': detailed_config.get('filters', {
                'exclude_patterns': [],
                'require_main_branch': True
            }),
```
→ **Line 134-137**: Extract filter rules

```python
            'notifications': detailed_config.get('notifications', {
                'enabled': True,
                'channels': [{'type': 'log', 'level': 'info'}]
            })
        }
```
→ **Line 138-141**: Extract notification settings

```python
        vsat_overrides = detailed_config.get('vsat_overrides') or {}
```
→ **Line 145**: Get VSAT-specific overrides (or empty dict if None)

```python
        if vsat_overrides and isinstance(vsat_overrides, dict):
```
→ **Line 146**: Check if overrides exist and is a dict

```python
            for vsat in merged_config['vsats']:
                vsat_name = vsat.get('name')
```
→ **Line 147-148**: Loop through VSATs, get name

```python
                if vsat_name and vsat_name in vsat_overrides:
                    override = vsat_overrides[vsat_name]
```
→ **Line 149-150**: Check if override exists for this VSAT

```python
                    if isinstance(override, dict):
                        if 'service_config' not in vsat:
                            vsat['service_config'] = {}
                        vsat['service_config'].update(override)
                        logger.info(f"   Applied overrides for VSAT: {vsat_name}")
```
→ **Line 151-155**: Apply override to VSAT's service_config

```python
        return merged_config
```
→ **Line 157**: Return final merged configuration

```python
    except yaml.YAMLError as e:
        raise VSATSyncError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise VSATSyncError(f"Error loading config: {e}")
```
→ **Line 159-162**: Catch and re-raise errors with context

---

## 7. Automation & Scheduling

### 7.1 APScheduler - Weekly Sync

**Configuration** (`main.py` lines 1851-1865):

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()
weekly_cron = config.get('sync_config', {}).get('weekly_schedule', '0 2 0')
minute, hour, day_of_week = weekly_cron.split()

scheduler.add_job(
    run_sync,                    # Function to call
    trigger=CronTrigger(
        day_of_week=day_of_week,  # Sunday=0, Monday=1, ..., Saturday=6
        hour=int(hour),           # Hour (0-23)
        minute=int(minute)        # Minute (0-59)
    ),
    id='weekly_vsat_sync',
    name='Weekly VSAT Sync',
    replace_existing=True
)
scheduler.start()
```

**Cron Format**: `"minute hour day_of_week"`

Examples:
- `"0 2 0"` → Sunday at 2:00 AM
- `"30 14 3"` → Wednesday at 2:30 PM
- `"0 0 *"` → Every day at midnight

---

### 7.2 watchdog - File Monitoring

**Configuration** (`main.py` lines 1868-1889):

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigFileChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_sync = datetime.now()
        self.debounce_seconds = 5  # Prevent rapid re-syncs
    
    def on_modified(self, event):
        if event.src_path.endswith(('vsat_master.yaml', 'vsat_config.yaml')):
            now = datetime.now()
            if (now - self.last_sync).total_seconds() > self.debounce_seconds:
                logger.info(f"Config file changed: {event.src_path}")
                logger.info("Triggering VSAT sync...")
                run_sync()
                self.last_sync = now

event_handler = ConfigFileChangeHandler()
config_observer = Observer()
config_observer.schedule(
    event_handler,
    path=str(MASTER_CONFIG_FILE.parent),  # Watch config/ directory
    recursive=False
)
config_observer.start()
```

**How It Works**:
1. Observer watches `config/` directory
2. On file modification, `on_modified()` is called
3. Checks if file is `vsat_master.yaml` or `vsat_config.yaml`
4. Debounces (5-second minimum between syncs)
5. Triggers `run_sync()`

---

## 8. Database Schema

### 8.1 `services` Table

```sql
CREATE TABLE services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT UNIQUE NOT NULL,           -- e.g., "saja9l7_cxp-ptg-adapter"
    service_name TEXT NOT NULL,                 -- e.g., "CXP PTG Adapter"
    repo_url TEXT NOT NULL,                     -- GitLab repo URL
    main_branch TEXT NOT NULL DEFAULT 'main',   -- Main branch name
    environments JSON NOT NULL,                 -- ["prod", "alpha", "beta1", "beta2"]
    config_paths JSON,                          -- ["*.yml", "*.yaml", ...]
    vsat TEXT DEFAULT 'saja9l7',               -- VSAT group/user name
    vsat_url TEXT DEFAULT 'https://gitlab.verizon.com/saja9l7',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    metadata JSON
);

CREATE INDEX idx_services_active ON services(is_active);
CREATE INDEX idx_services_id ON services(service_id);
```

### 8.2 `golden_branches` Table

```sql
CREATE TABLE golden_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,                 -- Foreign key to services.service_id
    environment TEXT NOT NULL,                  -- "prod", "alpha", "beta1", "beta2", "all"
    branch_name TEXT NOT NULL,                  -- "golden_prod_20251214_103045_abc123"
    branch_type TEXT DEFAULT 'golden',          -- "golden" or "drift"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    metadata JSON,
    UNIQUE(service_name, environment, branch_name)
);

CREATE INDEX idx_golden_branches_service ON golden_branches(service_name);
CREATE INDEX idx_golden_branches_active ON golden_branches(is_active);
```

**Relationships**:
- `golden_branches.service_name` → `services.service_id`
- One service has many golden branches (1:N)

---

## 9. Environment-Specific Filtering

### 9.1 File Categorization Rules

| Pattern | Environment(s) | Example |
|---------|---------------|---------|
| `*prod*` | prod only | `application-prod.yml` |
| `*alpha*` | alpha only | `config/alpha/settings.yml` |
| `*beta1*` or `*T1.yml` | beta1 only | `helm/values-T1.yml` |
| `*beta2*`, `*T2.yml`, `*T3.yml`, `*T4.yml`, `*T5.yml`, `*T6.yml` | beta2 only | `helm/values-T2.yml` |
| No environment marker | ALL environments | `application.yml` |

### 9.2 Filtering Process

```
1. Checkout all config files from main branch
   ↓
2. List all config files
   ↓
3. For each file:
   ├─ Call categorize_file_by_environment(filepath)
   └─ Returns list of environments
   ↓
4. For environment branch (e.g., prod):
   ├─ Filter: keep files where 'prod' in environments
   └─ Remove other files
   ↓
5. Commit filtered files
   ↓
6. Push to GitLab
```

### 9.3 Example Filtering

**All Files** (20 total):
```
application.yml               → ALL envs
application-prod.yml          → prod
application-alpha.yml         → alpha
helm/values-T1.yml            → beta1
helm/values-T2.yml            → beta2
helm/configmap-prod.yml       → prod
src/config/database.yml       → ALL envs
```

**After Filtering for `prod`**:
```
application.yml               ← global
application-prod.yml          ← prod-specific
helm/configmap-prod.yml       ← prod-specific
src/config/database.yml       ← global
```

**After Filtering for `beta1`**:
```
application.yml               ← global
helm/values-T1.yml            ← beta1-specific
src/config/database.yml       ← global
```

---

## 10. Branch Creation Logic

### 10.1 Branch Naming Convention

**Format**: `{prefix}_{environment}_{timestamp}_{hash}`

Examples:
- `golden_snapshot_20251214_143052_abc123`
- `golden_prod_20251214_143052_abc123`
- `golden_alpha_20251214_143052_abc123`
- `golden_beta1_20251214_143052_abc123`
- `golden_beta2_20251214_143052_abc123`

**Components**:
- **prefix**: `golden` or `drift`
- **environment**: `snapshot`, `prod`, `alpha`, `beta1`, `beta2`
- **timestamp**: `YYYYMMDD_HHMMSS`
- **hash**: 6-character UUID (for uniqueness)

### 10.2 Parallel Branch Creation

**Two Levels of Parallelization**:

#### Level 1: Per-Service Parallelization
5 branches created concurrently for a single service

```python
with ThreadPoolExecutor(max_workers=5) as executor:
    # Create all 5 branches simultaneously
    futures = [
        executor.submit(create_snapshot_branch),
        executor.submit(create_prod_branch),
        executor.submit(create_alpha_branch),
        executor.submit(create_beta1_branch),
        executor.submit(create_beta2_branch)
    ]
```

**Time**: ~10 seconds (instead of 50 seconds sequential)

#### Level 2: Cross-Service Parallelization
Multiple services processed concurrently

```python
with ThreadPoolExecutor(max_workers=10) as executor:
    # Process 10 services simultaneously
    for service_info in new_services:
        executor.submit(create_golden_branches_parallel, service_info)
```

**Combined Performance**:
- **Sequential**: 10 services × 5 branches × 10s = 500 seconds (8+ minutes)
- **Parallel**: ~50-100 seconds (5-10x faster!)

---

## 11. Error Handling

### 11.1 Error Types

#### `VSATSyncError` - Custom Exception
```python
class VSATSyncError(Exception):
    """Custom exception for VSAT sync errors"""
    pass
```

Raised for:
- Config file not found
- Missing required fields
- Duplicate VSAT IDs
- GitLab API errors
- Invalid YAML syntax

### 11.2 Retry Strategy

**HTTP Retries** (in `create_http_session()`):
```python
retry_strategy = Retry(
    total=3,                                # Max 3 retries
    backoff_factor=2,                       # 2s, 4s, 8s delays
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these errors
    allowed_methods=["GET", "POST"]
)
```

**Retry Schedule**:
- Attempt 1: Immediate
- Attempt 2: After 2 seconds
- Attempt 3: After 4 seconds
- Attempt 4: After 8 seconds
- Total: 14 seconds before failure

### 11.3 Graceful Failures

**Service-Level Errors**: Don't stop entire sync
```python
for project in projects:
    try:
        # Process service
    except Exception as e:
        error_msg = f"Error processing {project['name']}: {e}"
        logger.error(f"   ❌ {error_msg}")
        errors.append(error_msg)
        # Continue to next service
```

**VSAT-Level Errors**: Log and continue
```python
for vsat in vsats:
    try:
        sync_vsat_services(vsat, ...)
    except Exception as e:
        logger.error(f"❌ Failed to sync VSAT {vsat['name']}: {e}")
        all_errors.append(str(e))
        # Continue to next VSAT
```

---

## 12. Testing & Verification

### 12.1 Manual Testing

**Test 1: Initial Sync (Empty Database)**
```bash
# Start server
python main.py

# Check logs for:
# - "Database is empty - forcing full sync"
# - Services added
# - Branches created
```

**Test 2: Config Change Detection**
```bash
# Edit config/vsat_master.yaml
# Add a new VSAT

# Check logs for:
# - "Config file changed: config/vsat_master.yaml"
# - "Triggering VSAT sync..."
# - New VSAT synced
```

**Test 3: Duplicate VSAT Detection**
```bash
# Edit config/vsat_master.yaml
# Add duplicate VSAT name

# Expected error:
# "Duplicate VSAT IDs found in config: saja9l7"
```

**Test 4: Weekly Sync**
```bash
# Wait for scheduled time OR
# Trigger manually: curl -X POST http://localhost:3002/api/vsat/sync
```

### 12.2 Database Verification

```bash
# Check services
sqlite3 config_data/golden_config.db "SELECT * FROM services;"

# Check golden branches
sqlite3 config_data/golden_config.db "SELECT * FROM golden_branches WHERE is_active = 1;"

# Check services without branches
sqlite3 config_data/golden_config.db "
SELECT s.service_id 
FROM services s 
LEFT JOIN golden_branches gb ON s.service_id = gb.service_name AND gb.is_active = 1
WHERE gb.id IS NULL;
"
```

### 12.3 GitLab Verification

```bash
# List branches for a service
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.verizon.com/api/v4/projects/saja9l7%2Fcxp-ptg-adapter/repository/branches"

# Check branch contents
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.verizon.com/api/v4/projects/saja9l7%2Fcxp-ptg-adapter/repository/tree?ref=golden_prod_20251214_143052_abc123"
```

---

## 13. Usage Examples

### 13.1 Adding a New VSAT

**Edit `config/vsat_master.yaml`**:
```yaml
vsats:
  - name: saja9l7
    url: https://gitlab.verizon.com/saja9l7
    enabled: true

  - name: another_team     # ← NEW
    url: https://gitlab.verizon.com/another_team
    enabled: true
```

**What Happens**:
1. watchdog detects file change
2. `run_sync()` triggered
3. Config hash check fails → sync runs
4. Fetches projects from `another_team`
5. Adds services to database
6. Creates golden branches for all new services

### 13.2 Disabling a VSAT

**Edit `config/vsat_master.yaml`**:
```yaml
vsats:
  - name: saja9l7
    url: https://gitlab.verizon.com/saja9l7
    enabled: false       # ← DISABLED
```

**What Happens**:
1. Config change detected → sync runs
2. `sync_vsat_services()` skips disabled VSAT
3. `cleanup_orphaned_services()` deletes services from DB
4. Golden branches remain in GitLab (can be manually deleted)

### 13.3 Overriding Settings for a VSAT

**Edit `config/vsat_config.yaml`**:
```yaml
vsat_overrides:
  saja9l7:
    main_branch: master       # Use 'master' instead of 'main'
    environments:
      - prod
      - staging            # Different environments
```

**What Happens**:
1. Config loaded with overrides
2. Services from `saja9l7` use `master` branch
3. Golden branches created for `prod` and `staging` only

### 13.4 Manual Sync Trigger

**Via Python**:
```python
from scripts.vsat_sync import run_sync

result = run_sync(force=True)
print(result)
```

**Via CLI**:
```bash
python -c "from scripts.vsat_sync import run_sync; run_sync(force=True)"
```

**Via API** (if endpoint added):
```bash
curl -X POST http://localhost:3002/api/vsat/sync?force=true
```

---

## 14. Troubleshooting

### 14.1 Common Issues

#### Issue: "GITLAB_TOKEN not set in environment"

**Cause**: Missing GitLab token

**Solution**:
```bash
# Add to .env file
echo "GITLAB_TOKEN=your_token_here" >> .env

# Or export in shell
export GITLAB_TOKEN="your_token_here"
```

#### Issue: "Duplicate VSAT IDs found in config"

**Cause**: Same VSAT name appears multiple times in `vsat_master.yaml`

**Solution**:
```yaml
# BAD:
vsats:
  - name: saja9l7
    url: ...
  - name: saja9l7    # ← DUPLICATE!
    url: ...

# GOOD:
vsats:
  - name: saja9l7
    url: ...
  - name: another_team
    url: ...
```

#### Issue: "404 Not Found" when fetching projects

**Cause**: VSAT name doesn't exist or token lacks permissions

**Solution**:
1. Verify VSAT name/URL is correct
2. Check token has access to that group/user
3. Test manually:
   ```bash
   curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
     "https://gitlab.verizon.com/api/v4/groups/saja9l7/projects"
   ```

#### Issue: Services exist but no golden branches

**Cause**: Branch creation failed or was interrupted

**Solution**:
```bash
# Force sync to recreate branches
python -c "from scripts.vsat_sync import run_sync; run_sync(force=True)"
```

**System Will**:
- Check #5 detects services without branches
- Forces sync
- Creates missing branches

#### Issue: Config changes not detected

**Cause**: File saved but hash not updated

**Solution**:
```bash
# Delete hash file to force sync
rm config/.vsat_master_hash

# Restart server
python main.py
```

### 14.2 Logging & Debugging

**Enable Debug Logging**:
```python
# In vsat_sync.py, change:
logging.basicConfig(level=logging.DEBUG)  # Instead of INFO
```

**Check Database**:
```bash
sqlite3 config_data/golden_config.db

# List tables
.tables

# Show schema
.schema services

# Query services
SELECT * FROM services;

# Query branches
SELECT * FROM golden_branches;
```

**Check Config Hash**:
```bash
cat config/.vsat_master_hash
```

**Manual Sync with Logging**:
```bash
python -c "
import logging
logging.basicConfig(level=logging.INFO)
from scripts.vsat_sync import run_sync
result = run_sync(force=True)
print(result)
"
```

---

## 15. Complete Checklist

### All 18 Checks in Order

```
CHECK #0: Duplicate VSAT ID Check (load_vsat_config)
  ├─ Validates each VSAT has 'name' field
  ├─ Detects duplicate VSAT names
  └─ Prevents config loading if duplicates found

CHECK #1: Database Empty Check (run_sync)
  ├─ Query: SELECT * FROM services
  └─ If empty → force = True

CHECK #2: Force Flag Check (run_sync)
  └─ If force=True → skip other checks

CHECK #3: Config Hash Check (run_sync)
  ├─ Compare current hash vs saved hash
  └─ If different → sync

CHECK #4: Missing VSAT Check (run_sync)
  ├─ Compare VSATs in config vs VSATs in DB
  └─ If new VSATs → force = True

CHECK #5: Services Without Active Branches (run_sync)
  ├─ Query golden_branches for each service
  └─ If any service has 0 active branches → force = True

CHECK #6: VSAT Enabled Check (sync_vsat_services)
  └─ Skip if vsat.enabled = False

CHECK #7: Service Count Threshold (sync_vsat_services)
  └─ Warn if services < threshold

CHECK #8: Service Existence Check (sync_vsat_services)
  └─ Query services table for service_id

CHECK #9: Service Update Check (sync_vsat_services)
  └─ Compare repo_url and main_branch

CHECK #10: Service Branch Check (sync_vsat_services)
  ├─ Query golden_branches for service
  └─ If 0 → queue for branch creation

CHECK #11: Add New Service (sync_vsat_services)
  └─ Insert into services table

CHECK #12: New Service Branch Queue (sync_vsat_services)
  └─ Add to new_services_for_branches list

CHECK #13: Branch Creation Enabled (sync_vsat_services)
  └─ Check sync_config.create_golden_branches

CHECK #14: Parallel Execution (sync_vsat_services)
  └─ ThreadPoolExecutor with max_branch_workers

CHECK #15: Branch Creation Per Service (create_golden_branches_parallel)
  └─ Create 5 branches (1 snapshot + 4 env-specific)

CHECK #16: Orphaned Service Cleanup (cleanup_orphaned_services)
  └─ Delete services from removed VSATs

CHECK #17: Config Hash Save (run_sync)
  └─ Save current hash for next comparison
```

---

## Summary

This VSAT Master Config system provides:

✅ **Automated service discovery** from GitLab groups/users  
✅ **Real-time synchronization** via file monitoring  
✅ **Scheduled weekly syncs** via APScheduler  
✅ **Parallel golden branch creation** for performance  
✅ **Environment-specific filtering** to prevent config leaks  
✅ **Robust error handling** with retries and graceful failures  
✅ **Comprehensive validation** with 18 checks  
✅ **Zero-touch operation** - just run `main.py`  

**Key Files**:
- `config/vsat_master.yaml` - VSAT list
- `config/vsat_config.yaml` - Detailed settings
- `main.py` - Server + automation startup
- `scripts/vsat_sync.py` - Core sync engine
- `shared/env_filter.py` - Environment filtering
- `shared/git_operations.py` - Branch creation

**All automation runs from `main.py` - no separate scripts needed!**

---

END OF DOCUMENTATION

