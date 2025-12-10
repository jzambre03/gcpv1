# Supervisor Agent

The **Supervisor Agent** is the orchestration brain of the Golden Config AI system. It coordinates the validation workflow across worker agents and makes final business decisions.

---

## 🎯 Responsibilities

1. **Workflow Orchestration** - Coordinate validation across 2 worker agents
2. **Run Management** - Create and track validation runs with unique IDs
3. **Agent Coordination** - Execute multi-agent pipeline in sequence
4. **Result Aggregation** - Combine outputs from all agents
5. **Business Logic** - Apply PASS/FAIL decision rules
6. **Reporting** - Format comprehensive, actionable reports
7. **Audit Trail** - Maintain complete history of decisions

---

## 🤖 Configuration

**Model:** Claude 3.5 Sonnet (`anthropic.claude-3-5-sonnet-20241022-v2:0`)

**Why Sonnet?** Supervisor requires higher reasoning for:
- Complex workflow orchestration
- Multi-agent coordination
- Business rule application
- Comprehensive report generation

---

## 🔧 Tools

The Supervisor Agent has 5 specialized tools:

### 1. `create_validation_run`
Creates a unique validation run with timestamp-based ID.

**Usage:**
```python
create_validation_run(
    project_id="myorg/myrepo",
    mr_iid="123",
    source_branch="feature",
    target_branch="gold"
)
```

### 2. `execute_worker_pipeline`
Orchestrates the 2-agent file-based pipeline.

**Workflow:**
1. Config Collector - Fetches Git diffs, saves to file
2. Diff Engine - Reads file, analyzes with AI, saves results

**Usage:**
```python
execute_worker_pipeline(
    project_id="myorg/myrepo",
    mr_iid="123",
    run_id="run_20251004_165130_123",
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    golden_branch="gold",
    drift_branch="drift",
    target_folder=""
)
```

### 3. `aggregate_validation_results`
Combines results from both worker agents.

**Aggregates:**
- Files analyzed/compared
- Drift count
- Policy violations
- Risk level
- Final verdict (PASS/FAIL)

### 4. `format_validation_report`
Creates comprehensive markdown report.

**Includes:**
- Status emoji (✅/❌)
- Verdict and risk level
- Summary of findings
- Detailed analysis
- Recommendations
- Pipeline info

### 5. `save_validation_report`
Saves report to `config_data/reports/{run_id}_report.md`.

---

## 📊 Workflow

### Complete Validation Flow:

```
1. User Request
   ↓
2. Supervisor creates unique run_id
   ↓
3. Execute 2-agent pipeline:
   │
   ├─► Config Collector
   │   ├─ Clone Git repo
   │   ├─ Fetch branch diffs
   │   └─ Save: drift_analysis_*.json
   │
   └─► Diff Policy Engine
       ├─ Read: drift_analysis_*.json
       ├─ AI-powered analysis
       └─ Save: diff_analysis_*.json
   ↓
4. Aggregate results from both agents
   ↓
5. Apply business logic (PASS/FAIL)
   ↓
6. Format comprehensive report
   ↓
7. Save: {run_id}_report.md
   ↓
8. Return validation results
```

---

## 🚀 Usage

### Create Agent Instance:

```python
from Agents.Supervisor.supervisor_agent import create_supervisor_agent

agent = create_supervisor_agent()
```

### Run Complete Validation:

```python
from Agents.Supervisor.supervisor_agent import run_validation

result = run_validation(
    project_id="myorg/myrepo",
    mr_iid="123",
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    golden_branch="gold",
    drift_branch="drift",
    target_folder=""  # Optional: analyze specific folder
)

print(f"Run ID: {result['run_id']}")
print(f"Verdict: {result['verdict']}")
print(f"Execution time: {result['execution_time_ms']}ms")
```

### Direct Agent Invocation:

```python
agent = create_supervisor_agent()

instruction = """
Please orchestrate validation for:
- Project: myorg/myrepo
- MR: 123
- Repo: https://gitlab.verizon.com/saja9l7/golden_config.git
- Golden Branch: gold
- Drift Branch: drift

Complete workflow:
1. Create validation run
2. Execute 2-agent pipeline
3. Aggregate results
4. Format and save report
"""

result = agent(instruction)
```

---

## 📁 Outputs

### Validation Reports
**Location:** `config_data/reports/{run_id}_report.md`

**Format:**
```markdown
## ✅ Configuration Validation Report

**Run ID:** `run_20251004_165130_123`
**Verdict:** **PASS**
**Risk Level:** **LOW**

### 📋 Summary
✅ Configuration validated successfully. No drift detected.

### 📊 Analysis Details
- **Files with Drift:** 0
- **Policy Violations:** 0
- **Risk Level:** low

### 📊 Validation Pipeline
Config Collector → Diff Engine

*Powered by AWS Strands Multi-Agent Framework*
```

---

## 🔍 Business Logic

### PASS/FAIL Decision:

**PASS if:**
- No files with drift
- No policy violations
- Risk level: low

**FAIL if:**
- Files with drift > 0
- Policy violations > 0
- Risk level: medium, high, or critical

---

## ⚙️ Configuration

Set in `.env`:

```bash
# Supervisor Model (Claude 3.5 Sonnet for orchestration)
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# AWS Region
AWS_REGION=us-east-1
```

---

## 🐛 Troubleshooting

### "Worker pipeline execution failed"
**Check:**
1. Config Collector Agent is accessible
2. Diff Policy Engine Agent is accessible
3. Git repository is accessible
4. AWS credentials are valid

### "Failed to aggregate results"
**Check:**
1. Worker agents completed successfully
2. Output files exist in `config_data/`
3. File permissions are correct

### "Failed to save report"
**Check:**
1. `config_data/reports/` directory exists
2. Write permissions for `config_data/`
3. Disk space available

---

## 📚 Related

- **Config Collector:** `../workers/config_collector/README.md`
- **Diff Engine:** `../workers/diff_policy_engine/README.md`
- **Main README:** `../../README.md`

---

**The orchestration brain of your multi-agent system!** 🧠

