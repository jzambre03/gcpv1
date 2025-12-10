# Config Collector Agent

The **Config Collector Agent** is responsible for extracting configuration files from Git repositories and creating snapshot branches.

## 🎯 Responsibilities

1. **Extract Configuration Files** - Identify and list all configuration files in repository
2. **Create Snapshot Branches** - Create golden and drift snapshot branches from main branch
3. **Basic Git Operations** - Clone repositories, checkout branches, manage branches
4. **Repository Preparation** - Prepare repository snapshots for drift detection

**⚠️ IMPORTANT:** This agent does NOT perform diff detection. That's handled by the **Drift Detector Agent**.

---

## 🤖 Configuration

**Model:** Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`)

**Why Haiku?** Config Collector performs deterministic tasks:
- Git operations
- File identification
- Branch creation
- Does not require complex reasoning

---

## 🔧 Tools

The Config Collector Agent has specialized tools:

### 1. `setup_repository_access`
Setup repository access with authentication.

**Usage:**
```python
setup_repository_access(
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git"
)
```

### 2. `clone_repository`
Clone a Git repository branch to temporary location.

**Usage:**
```python
clone_repository(
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    branch="main",
    temp_dir="/tmp/repo_clone"
)
```

### 3. `extract_config_files`
Extract configuration files from repository.

**Detects:**
- YAML (`.yml`, `.yaml`)
- JSON (`.json`)
- Properties (`.properties`, `.ini`, `.cfg`, `.conf`, `.config`)
- TOML (`.toml`)
- XML (`.xml`)
- Build files (`pom.xml`, `build.gradle`, `requirements.txt`, `go.mod`)
- Container files (`Dockerfile`, `docker-compose.yml`)

### 4. `create_golden_snapshot`
Create golden snapshot branch from main branch (config-only).

**Usage:**
```python
create_golden_snapshot(
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    main_branch="main",
    environment="prod",
    service_id="gcp"
)
```

**Output:** Branch name like `golden_prod_20251201_143052_abc123`

### 5. `create_drift_snapshot`
Create drift snapshot branch from main branch (config-only).

**Usage:**
```python
create_drift_snapshot(
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    main_branch="main",
    environment="prod",
    service_id="gcp"
)
```

**Output:** Branch name like `drift_prod_20251201_143052_abc123`

### 6. `prepare_repository_snapshots`
Complete workflow: Create snapshots and extract config files.

**This is the main method that:**
1. Creates golden snapshot branch
2. Creates drift snapshot branch
3. Clones both branches to temporary locations
4. Extracts config files from both

---

## 📊 Workflow

### Complete Config Collection Flow:

```
1. User Request (via Supervisor)
   ↓
2. Create Golden Snapshot Branch
   ├─ Generate unique branch name
   ├─ Create config-only branch from main
   └─ Push to remote
   ↓
3. Create Drift Snapshot Branch
   ├─ Generate unique branch name
   ├─ Create config-only branch from main
   └─ Push to remote
   ↓
4. Clone Both Branches
   ├─ Clone golden branch → /tmp/golden_...
   └─ Clone drift branch → /tmp/drift_...
   ↓
5. Extract Config Files
   ├─ Scan golden branch for config files
   ├─ Scan drift branch for config files
   └─ Combine and deduplicate
   ↓
6. Return Results
   └─ repository_snapshots: {
        golden_branch: "golden_prod_...",
        drift_branch: "drift_prod_...",
        golden_path: "/tmp/golden_...",
        drift_path: "/tmp/drift_..."
      }
      config_files: [...]
```

---

## 🚀 Usage

### Via Supervisor (Recommended):

The Supervisor automatically calls this agent as part of the workflow.

### Direct Usage:

```python
from Agents.workers.config_collector.config_collector_agent import ConfigCollectorAgent
from shared.config import Config
from shared.models import TaskRequest

# Initialize
config = Config()
agent = ConfigCollectorAgent(config)

# Create task
task = TaskRequest(
    task_id="test_collection",
    task_type="collect_configs",
    parameters={
        "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
        "main_branch": "main",
        "environment": "prod",
        "service_id": "gcp",
        "target_folder": ""  # Optional
    }
)

# Process task
result = agent.process_task(task)

print(f"Status: {result.status}")
print(f"Golden branch: {result.result['repository_snapshots']['golden_branch']}")
print(f"Drift branch: {result.result['repository_snapshots']['drift_branch']}")
print(f"Config files: {len(result.result['config_files'])}")
```

---

## 📁 Outputs

### TaskResponse Result Structure:

```json
{
  "repository_snapshots": {
    "golden_branch": "golden_prod_20251201_143052_abc123",
    "drift_branch": "drift_prod_20251201_143052_def456",
    "golden_path": "/tmp/config_collector/gcp_prod_20251201_143052/golden",
    "drift_path": "/tmp/config_collector/gcp_prod_20251201_143052/drift"
  },
  "config_files": [
    "application.yml",
    "application-prod.yml",
    "docker-compose.yml",
    "pom.xml",
    "requirements.txt"
  ],
  "summary": {
    "total_config_files": 15,
    "environment": "prod",
    "service_id": "gcp"
  }
}
```

**Note:** The repository paths are temporary and will be cleaned up after drift detection completes.

---

## 🎯 Supported File Types

### Configuration Files:
- **YAML:** `.yml`, `.yaml`
- **JSON:** `.json`
- **Properties:** `.properties`, `.ini`, `.cfg`, `.conf`, `.config`
- **TOML:** `.toml`
- **XML:** `.xml`

### Build Files:
- **Maven:** `pom.xml`
- **Gradle:** `build.gradle`, `build.gradle.kts`, `settings.gradle`
- **Python:** `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`
- **Go:** `go.mod`
- **NPM:** `package.json`, `package-lock.json`

### Container Files:
- **Docker:** `Dockerfile`, `docker-compose.yml`

### Special Files:
- **CI/CD:** `Jenkinsfile`
- **Build:** `Makefile`

---

## 📊 Snapshot Branch Creation

### Golden Snapshot Branch:
- **Purpose:** Represents the certified baseline configuration
- **Source:** Created from main branch
- **Content:** Only configuration files (sparse checkout)
- **Naming:** `golden_{environment}_{timestamp}_{uuid}`

### Drift Snapshot Branch:
- **Purpose:** Represents current configuration state
- **Source:** Created from main branch
- **Content:** Only configuration files (sparse checkout)
- **Naming:** `drift_{environment}_{timestamp}_{uuid}`

### Config-Only Branches:
Uses Git sparse checkout to only include configuration files, making branches:
- **Faster to create** (no need to clone entire repo)
- **Smaller in size** (only config files)
- **Easier to compare** (focused on what matters)

---

## 🔧 Configuration

Set in `.env`:

```bash
# Worker Model (Claude 3 Haiku)
BEDROCK_WORKER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# AWS Region
AWS_REGION=us-east-1

# GitLab (for private repos)
GITLAB_TOKEN=your_token_here
GIT_USER_NAME=Your Name
GIT_USER_EMAIL=your.email@example.com
```

---

## 🔄 Next Agent in Pipeline

After Config Collector completes, the **Drift Detector Agent** receives:
- Repository snapshot paths (golden and drift)
- List of configuration files
- Branch names

The Drift Detector then performs:
- Context parsing
- Compare algorithms
- Diff generation
- Delta creation

---

## 🐛 Troubleshooting

### "Repository clone failed"
**Check:**
1. Repository URL is accessible
2. GitLab token is valid (for private repos)
3. Git is installed
4. Network connectivity

### "Branch not found"
**Check:**
1. Branch name is correct
2. Branch exists in repository
3. Repository access permissions

### "No config files found"
**Check:**
1. Target folder path is correct
2. Repository contains configuration files
3. File extensions match supported types

### "Snapshot creation failed"
**Check:**
1. GitLab token has write permissions
2. Main branch exists
3. Config paths are valid

---

## 📚 Related

- **Supervisor:** `../../Supervisor/README.md`
- **Drift Detector:** `../drift_detector/README.md` (receives output from this agent)
- **Main README:** `../../../README.md`

---

## ⚠️ Important Notes

1. **No Diff Detection:** This agent does NOT compare branches or detect changes
2. **Snapshot Creation:** Creates branches but doesn't analyze them
3. **Temporary Paths:** Repository paths are temporary and cleaned up after use
4. **Config-Only:** Snapshot branches contain only configuration files (sparse checkout)

---

**The configuration file extraction engine of your multi-agent system!** 📦
