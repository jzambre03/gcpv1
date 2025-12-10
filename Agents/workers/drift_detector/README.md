# Drift Detector Agent

The **Drift Detector Agent** performs precision drift analysis between golden and drift branch snapshots.

## 🎯 Responsibilities

1. **Context Parsing** - Parse YAML, JSON, properties, XML, TOML files
2. **Compare Algorithms** - Structural diff, semantic diff, hash comparison
3. **Diff Generation** - Line-by-line deltas with exact locators
4. **Specialized Detection** - Spring profiles, Jenkinsfile, Docker changes
5. **Context Bundle** - Generate structured context_bundle.json

**⚠️ IMPORTANT:** This agent does NOT perform risk analysis or LLM reasoning. That's handled by the **Triaging-Routing Agent**.

---

## 🤖 Configuration

**Model:** Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`)

**Why Haiku?** Drift Detector performs mostly deterministic tasks:
- File tree extraction
- Structural comparison
- Semantic diff calculation
- Does not require complex reasoning

---

## 🔧 Tools

### 1. `run_drift_analysis` ⭐ MAIN TOOL
Complete drift analysis workflow.

**Performs:**
1. Extract file trees from both branches
2. Classify files by type (config, code, build)
3. Compute structural diff (added/removed/modified/renamed)
4. Compute semantic diff (key-level changes)
5. Analyze dependencies
6. Run specialized detectors (Spring, Jenkins, Docker)
7. Build code hunks with line numbers
8. Generate context_bundle.json

**Usage:**
```python
run_drift_analysis(
    golden_path="/tmp/golden_...",
    drift_path="/tmp/drift_...",
    target_folder=""
)
```

### 2. `extract_file_trees`
Extract file lists from repositories.

### 3. `compute_structural_diff`
Find added/removed/modified/renamed files.

### 4. `compute_semantic_diff`
Find key-level changes in config files.

### 5. `run_specialized_detectors`
Run Spring/Jenkins/Docker detectors.

### 6. `generate_context_bundle`
Create context_bundle.json.

---

## 📊 Workflow

### Complete Drift Analysis Flow:

```
1. Input from Config Collector
   ├─ golden_path: /tmp/.../golden
   ├─ drift_path: /tmp/.../drift
   └─ config_files: [list]
   ↓
2. Extract File Trees
   ├─ Scan golden branch
   ├─ Scan drift branch
   └─ Filter to config files only
   ↓
3. Classify Files
   ├─ config (yml, json, properties)
   ├─ build (pom.xml, gradle)
   ├─ ci (Jenkinsfile)
   └─ infra (Dockerfile)
   ↓
4. Structural Diff
   ├─ Files added
   ├─ Files removed
   ├─ Files modified
   └─ Files renamed (hash matching)
   ↓
5. Semantic Diff
   ├─ Keys added (new config entries)
   ├─ Keys removed (deleted entries)
   └─ Keys changed (value modifications)
   ↓
6. Dependency Analysis
   ├─ Maven dependencies
   ├─ Gradle dependencies
   ├─ npm packages
   └─ Python requirements
   ↓
7. Specialized Detectors
   ├─ Spring profiles (application.yml)
   ├─ Jenkinsfile changes
   └─ Docker changes
   ↓
8. Code Hunks
   ├─ Line-by-line diffs
   ├─ Exact line numbers
   └─ Git-style patches
   ↓
9. Generate context_bundle.json
   └─ Structured deltas with locators
   ↓
10. Return to Supervisor
    └─ context_bundle_file path
```

---

## 📁 Input Format

### From Config Collector:

```json
{
  "golden_path": "/tmp/config_collector/gcp_prod_20251201/golden",
  "drift_path": "/tmp/config_collector/gcp_prod_20251201/drift",
  "golden_branch": "golden_prod_20251115_120000",
  "drift_branch": "drift_prod_20251201_143052",
  "config_files": ["application.yml", "pom.xml", ...]
}
```

---

## 📁 Output Format

### context_bundle.json Structure:

```json
{
  "meta": {
    "timestamp": "2025-12-01T14:30:52.123456",
    "golden_branch": "golden_prod_20251115_120000",
    "drift_branch": "drift_prod_20251201_143052"
  },
  "overview": {
    "golden_files": 45,
    "candidate_files": 47,
    "total_files": 92,
    "drifted_files": 12
  },
  "file_changes": {
    "added": ["config/new-service.yml"],
    "removed": ["config/deprecated.yml"],
    "modified": ["application.yml", "pom.xml"],
    "renamed": [{"from": "old.yml", "to": "new.yml"}]
  },
  "deltas": [
    {
      "id": "delta_001",
      "file": "application.yml",
      "change_type": "modified",
      "key": "server.port",
      "from_value": "8080",
      "to_value": "8090",
      "locator": {
        "type": "yamlpath",
        "value": "application.yml.server.port",
        "line": 15
      },
      "env_tag": "prod"
    }
  ],
  "dependencies": {
    "maven": {
      "added": {"spring-boot-starter-web": "3.2.0"},
      "removed": {},
      "changed": {"spring-core": {"from": "5.3.0", "to": "6.0.0"}}
    }
  },
  "evidence": [
    {
      "file": "application.yml",
      "hunk": "@@ -15,7 +15,7 @@\n server:\n-  port: 8080\n+  port: 8090"
    }
  ]
}
```

### TaskResponse Result:

```json
{
  "context_bundle_file": "config_data/context_bundles/bundle_20251201_143052/context_bundle.json",
  "summary": {
    "total_files": 92,
    "drifted_files": 12,
    "added": 2,
    "removed": 1,
    "modified": 9,
    "total_deltas": 45,
    "config_changes": 23,
    "dependency_changes": 5,
    "code_hunks": 15
  }
}
```

---

## 🔍 Delta Types

### 1. Config Key Changes
```json
{
  "change_type": "key_changed",
  "key": "server.port",
  "from_value": "8080",
  "to_value": "8090",
  "locator": {"type": "yamlpath", "value": "application.yml.server.port"}
}
```

### 2. File Changes
```json
{
  "change_type": "file_added",
  "file": "config/new-service.yml"
}
```

### 3. Dependency Changes
```json
{
  "change_type": "dependency_changed",
  "ecosystem": "maven",
  "package": "spring-core",
  "from_version": "5.3.0",
  "to_version": "6.0.0"
}
```

### 4. Code Hunks
```json
{
  "change_type": "hunk",
  "file": "application.yml",
  "old_start": 15,
  "old_lines": 7,
  "new_start": 15,
  "new_lines": 7,
  "body": "@@ -15,7 +15,7 @@\n server:\n-  port: 8080\n+  port: 8090"
}
```

---

## 🔄 Locator Types

### YAMLPath
For YAML files:
```json
{"type": "yamlpath", "value": "application.yml.server.port", "line": 15}
```

### JSONPath
For JSON files:
```json
{"type": "jsonpath", "value": "package.json.dependencies.express", "line": 8}
```

### KeyPath
For properties/INI files:
```json
{"type": "keypath", "value": "application.properties.server.port", "line": 3}
```

### Line Number
For code hunks:
```json
{"type": "line", "start": 15, "end": 22}
```

---

## 🚀 Usage

### Via Supervisor (Recommended):

The Supervisor automatically calls this agent after Config Collector.

### Direct Usage:

```python
from Agents.workers.drift_detector.drift_detector_agent import DriftDetectorAgent
from shared.config import Config
from shared.models import TaskRequest

# Initialize
config = Config()
agent = DriftDetectorAgent(config)

# Create task
task = TaskRequest(
    task_id="test_drift",
    task_type="detect_drift",
    parameters={
        "golden_path": "/tmp/golden_...",
        "drift_path": "/tmp/drift_...",
        "golden_branch": "golden_prod_20251115",
        "drift_branch": "drift_prod_20251201"
    }
)

# Process task
result = agent.process_task(task)

print(f"Status: {result.status}")
print(f"Context bundle: {result.result['context_bundle_file']}")
print(f"Total deltas: {result.result['summary']['total_deltas']}")
```

---

## 🔧 Configuration

Set in `.env`:

```bash
# Worker Model (Claude 3 Haiku)
BEDROCK_WORKER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# AWS Region
AWS_REGION=us-east-1
```

---

## 📚 Related

- **Config Collector:** `../config_collector/README.md` (provides input)
- **Triaging-Routing:** `../triaging_routing/README.md` (receives output)
- **drift.py:** `../../../shared/drift_analyzer/` (core analysis engine)

---

## ⚠️ Important Notes

1. **No Risk Analysis:** This agent only detects diffs, not risk levels
2. **No LLM Reasoning:** Uses LLM only for tool orchestration
3. **Config Files Only:** Filters to configuration files
4. **Exact Locators:** Always provides line-level precision
5. **Deterministic:** Same input = same output

---

**The precision diff engine of your multi-agent system!** 🔍
