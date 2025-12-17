# Hardcoded Values Audit Report
## Complete Analysis of Hardcoded Values in Python Files

**Generated:** December 16, 2025  
**Scope:** All `.py` files in `/Users/jayeshzambre/Documents/GitHub/gcpv1/`

---

## 🔴 CRITICAL: Hardcoded Values That MUST Be Removed

### 1. **Hardcoded Windows Paths** (HIGHEST PRIORITY)
**File:** `shared/drift_analyzer/drift_v1.py` (Lines 821-824)

```python
DEFAULT_GOLDEN = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\golden"
DEFAULT_CANDIDATE = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\drifted"
DEFAULT_OUT = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\llmcontext"
DEFAULT_POLICIES = "C:\\Users\\saja9l7\\Downloads\\gcp\\context_generator\\policies.yaml"
```

**❌ Problem:**
- **Username hardcoded:** `saja9l7` - won't work for any other user
- **Windows-specific paths:** Won't work on Linux/Mac (EC2 instances)
- **Absolute paths:** Breaks portability completely

**✅ Recommended Fix:**
```python
# Use relative paths from project root
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_GOLDEN = PROJECT_ROOT / "test_data" / "golden"
DEFAULT_CANDIDATE = PROJECT_ROOT / "test_data" / "drifted"
DEFAULT_OUT = PROJECT_ROOT / "test_data" / "llmcontext"
DEFAULT_POLICIES = PROJECT_ROOT / "config" / "policies.yaml"
```

**Alternative (Better):**
```python
# Use environment variables with sensible defaults
DEFAULT_GOLDEN = os.getenv("DRIFT_GOLDEN_PATH", str(PROJECT_ROOT / "test_data" / "golden"))
DEFAULT_CANDIDATE = os.getenv("DRIFT_CANDIDATE_PATH", str(PROJECT_ROOT / "test_data" / "drifted"))
DEFAULT_OUT = os.getenv("DRIFT_OUTPUT_PATH", str(PROJECT_ROOT / "test_data" / "llmcontext"))
DEFAULT_POLICIES = os.getenv("DRIFT_POLICIES_PATH", str(PROJECT_ROOT / "config" / "policies.yaml"))
```

---

### 2. **Hardcoded User/Organization Name**
**Files:** Multiple files contain `saja9l7` references

#### **a) Database Schema Defaults**
**File:** `shared/db.py` (Lines 212-213)
```python
vsat TEXT DEFAULT 'saja9l7',
vsat_url TEXT DEFAULT 'https://gitlab.verizon.com/saja9l7',
```

**File:** `scripts/migrate_add_services_table.py` (Lines 88-89)
```python
vsat TEXT DEFAULT 'saja9l7',
vsat_url TEXT DEFAULT 'https://gitlab.verizon.com/saja9l7',
```

**❌ Problem:**
- Database will default to `saja9l7` for all new records
- Not reusable for other teams/users

**✅ Recommended Fix:**
```python
# Remove defaults or use NULL - force users to provide values
vsat TEXT NOT NULL,
vsat_url TEXT NOT NULL,
```

#### **b) Example/Test Data**
**File:** `scripts/migrate_add_services_table.py` (Line 43)
```python
"repo_url": "https://gitlab.verizon.com/saja9l7/cxp-ptg-adapter.git",
```

**File:** `shared/db.py` (Line 892)
```python
"https://gitlab.verizon.com/saja9l7/cxp-ptg-adapter.git"
```

**✅ These are OK IF:**
- They're in comments/docstrings as examples
- Used in test/example code (clearly marked)

**⚠️ Action Required:**
- Add comment: `# Example only - replace with your actual repository`

---

### 3. **Hardcoded GitLab Instance URL**
**Files:** Multiple files reference `https://gitlab.verizon.com`

#### **Production Code:**
**File:** `test.py` (Line 52, 329)
```python
def get_gitlab_group_projects(group_path: str, gitlab_url: str = "https://gitlab.verizon.com", ...)
GITLAB_URL = "https://gitlab.verizon.com"
```

**❌ Problem:**
- Hardcoded to Verizon's GitLab instance
- Cannot be used with github.com, gitlab.com, or other instances

**✅ Recommended Fix:**
```python
# Get from environment variable
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.verizon.com")

def get_gitlab_group_projects(
    group_path: str, 
    gitlab_url: str = None,  # Remove default
    private_token: str = None
):
    gitlab_url = gitlab_url or os.getenv("GITLAB_URL", "https://gitlab.verizon.com")
    # ... rest of function
```

**Alternative (Best):**
```python
# Extract from repo URL automatically (no hardcoding needed)
# Already implemented in vsat_sync.py lines 683-698
```

---

## 🟡 MEDIUM PRIORITY: Configuration Values

### 4. **Database Path**
**File:** `shared/db.py` (Line 18)
```python
DB_PATH = PROJECT_ROOT / "config_data" / "golden_config.db"
```

**⚠️ Status:** Partially OK (uses PROJECT_ROOT)
- Uses relative path from project root ✅
- But hardcodes `config_data` directory name

**✅ Recommended Improvement:**
```python
DB_PATH = Path(os.getenv("GCP_DB_PATH", str(PROJECT_ROOT / "config_data" / "golden_config.db")))
```

---

### 5. **AWS Region**
**File:** `shared/config.py` (Line 21)
```python
aws_region: str = os.getenv("AWS_REGION", "us-east-1")
```

**✅ Status:** GOOD - Uses environment variable with sensible default

---

### 6. **Model IDs**
**File:** `shared/config.py` (Lines 26-27)
```python
bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
bedrock_worker_model_id: str = os.getenv("BEDROCK_WORKER_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
```

**✅ Status:** GOOD - Uses environment variables with defaults

**⚠️ Note:** Model IDs will change over time as AWS updates models
- Consider adding a comment to check for latest versions
- Maybe use a config file instead for easier updates

---

### 7. **Server Port and Host**
**File:** `main.py` (Line 884)
```python
base_url = os.getenv("BASE_URL", "http://localhost:3000")
```

**✅ Status:** GOOD - Uses environment variable

**File:** `main.py` (Lines 1735-1737)
```python
print(f"   Dashboard:  http://localhost:{port}")
print(f"   API Docs:   http://localhost:{port}/docs")
print(f"   Health:     http://localhost:{port}/health")
```

**✅ Status:** OK - Uses `{port}` variable (dynamic)

---

## 🟢 LOW PRIORITY: Acceptable Hardcoded Values

### 8. **Default Branch Names**
**File:** `main.py` (Line 186)
```python
DEFAULT_MAIN_BRANCH = os.getenv("DEFAULT_MAIN_BRANCH", ... or "main")
```

**✅ Status:** GOOD - Sensible default (`main` is Git standard since 2020)

---

### 9. **Config File Patterns**
**File:** `shared/config.py` (Lines 8-13)
```python
CONFIG_FILE_PATTERNS = [
    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
    "*.cfg", "*.conf", "*.config",
    "Dockerfile", "docker-compose.yml",
    "pom.xml", "build.gradle", "requirements.txt"
]
```

**✅ Status:** OK - These are standard industry patterns
- Could be moved to a config file for customization
- But reasonable to hardcode as they're universal

---

### 10. **Redis Defaults**
**File:** `shared/config.py` (Lines 37-40)
```python
redis_host: str = os.getenv("REDIS_HOST", "localhost")
redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
redis_db: int = int(os.getenv("REDIS_DB", "0"))
```

**✅ Status:** GOOD - Standard Redis defaults, overridable via env vars

---

### 11. **Example/Documentation URLs**
**File:** `main.py` (Line 184)
```python
"https://gitlab.example.com/org/golden_config.git"
```

**File:** `main.py` (Line 1607)
```python
"repo_url": "https://gitlab.example.com/org/repo.git",
```

**✅ Status:** OK - Clearly example/placeholder URLs
- Uses `example.com` (reserved for documentation per RFC 2606)

---

## 📊 Summary Statistics

| Category | Count | Severity | Action Required |
|----------|-------|----------|-----------------|
| **Windows User Paths** | 4 | 🔴 CRITICAL | Must fix immediately |
| **Hardcoded User/Org** | 6 | 🔴 CRITICAL | Remove from defaults |
| **GitLab Instance URL** | 3 | 🟡 MEDIUM | Make configurable |
| **Database Paths** | 1 | 🟡 MEDIUM | Consider env var |
| **Default Configs** | 10+ | 🟢 LOW | OK with env vars |
| **Example/Docs** | 5+ | 🟢 ACCEPTABLE | OK (documentation) |

---

## 🎯 Priority Action Items

### IMMEDIATE (This Week):
1. ✅ **Fix `drift_v1.py` Windows paths** - Blocks Linux/EC2 usage
2. ✅ **Remove `saja9l7` from database defaults** - Makes system non-reusable

### SHORT-TERM (Next Sprint):
3. 🟡 **Make GitLab URL configurable in `test.py`**
4. 🟡 **Add environment variable for database path**

### LONG-TERM (Nice to Have):
5. 🟢 **Create central config file for file patterns**
6. 🟢 **Document all environment variables in README**

---

## 🛠️ Recommended Environment Variables to Add

```bash
# Add to .env file
# ==============

# Drift Analyzer Paths (NEW)
DRIFT_GOLDEN_PATH=./test_data/golden
DRIFT_CANDIDATE_PATH=./test_data/drifted
DRIFT_OUTPUT_PATH=./test_data/llmcontext
DRIFT_POLICIES_PATH=./config/policies.yaml

# GitLab Configuration (NEW)
GITLAB_URL=https://gitlab.verizon.com

# Database Configuration (ENHANCE)
GCP_DB_PATH=./config_data/golden_config.db

# Existing (already good)
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
BEDROCK_WORKER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
GITLAB_TOKEN=your-token-here
BASE_URL=http://localhost:3000
```

---

## ✅ What's Already Done Right

### Good Practices Found:
1. ✅ **`tempfile.gettempdir()`** - Dynamic temp directory detection
2. ✅ **`Path(__file__).parent`** - Relative path resolution
3. ✅ **`os.getenv()` everywhere** - Environment variable usage
4. ✅ **Config class** - Centralized configuration management
5. ✅ **No secrets/tokens hardcoded** - All from environment

---

## 🚨 Files That Need Immediate Attention

### Priority 1 (MUST FIX):
```
1. shared/drift_analyzer/drift_v1.py (Lines 821-824)
   - Remove Windows user paths
   - Use relative paths or environment variables

2. shared/db.py (Lines 212-213)
   - Remove 'saja9l7' default values
   - Use NULL or remove defaults

3. scripts/migrate_add_services_table.py (Lines 88-89)
   - Same as #2 above
```

### Priority 2 (SHOULD FIX):
```
4. test.py (Lines 52, 329)
   - Make GitLab URL configurable
   - Read from environment variable
```

---

## 📝 Verification Checklist

After implementing fixes, verify:

- [ ] System works on Linux (EC2)
- [ ] System works on macOS
- [ ] System works on Windows (different user)
- [ ] No absolute paths with usernames
- [ ] All paths use `Path(__file__).parent` for relative resolution
- [ ] All configurable values have environment variable overrides
- [ ] `.env.example` documents all required variables
- [ ] README explains configuration options

---

## 🎓 Best Practices for Future Development

### ✅ DO:
- Use `os.getenv("VAR_NAME", "default_value")`
- Use `Path(__file__).parent` for relative paths
- Use `tempfile.gettempdir()` for temp directories
- Document all configuration in `.env.example`
- Use example.com for placeholder URLs

### ❌ DON'T:
- Use absolute paths with usernames
- Hardcode URLs without environment variable option
- Use Windows-specific paths (C:\Users\...)
- Commit real credentials/tokens
- Use company-specific defaults without overrides

---

**End of Audit Report**

