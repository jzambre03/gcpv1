# Configuration Drift Detection System

A multi-agent AI system for detecting and analyzing configuration drift using AWS Bedrock, GitLab integration, and policy-aware analysis.

## 🎯 Overview

This system validates configuration changes against a "Golden Config" (single source of truth) stored in GitLab, detects drift, enforces organizational policies, and generates detailed validation reports.

### Key Features

- **🔍 Precision Drift Detection**: Uses `drift.py` for line-precise analysis with structured deltas
- **🤖 Multi-Agent Architecture**: Orchestrates specialized agents for different tasks
- **📋 Policy-Aware**: Enforces organization-specific rules with explicit policy violations
- **🎯 Intelligent Verdicts**: 4-level decision system (PASS, WARN, REVIEW_REQUIRED, BLOCK)
- **📊 Comprehensive Reports**: Detailed markdown reports with actionable recommendations
- **🔐 GitLab Integration**: Automatic validation of merge requests
- **☁️ AWS Bedrock Powered**: Uses Claude 3.5 Sonnet and Claude 3 Haiku models

## 🏗️ Architecture

### Three-Agent System

```
┌─────────────────────────────────────────────────────────┐
│                  Supervisor Agent                        │
│              (Claude 3.5 Sonnet)                        │
│         Orchestrates validation workflow                │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌───────────────────┐  ┌────────────────────┐
│  Config Collector │  │  Diff Policy       │
│     Agent         │  │  Engine Agent      │
│  (Claude 3 Haiku) │  │  (Claude 3 Haiku)  │
│                   │  │                    │
│  • Clones repos   │  │  • AI analysis     │
│  • Runs drift.py  │  │  • Policy checks   │
│  • Generates      │  │  • Risk assessment │
│    context_bundle │  │  • Generates       │
│                   │  │    enhanced_       │
│                   │  │    analysis        │
└───────────────────┘  └────────────────────┘
```

### Data Flow

```
1. GitLab Repos
      ↓
2. Config Collector → Database (context_bundle + deltas)
   (drift.py precision analysis)
      ↓
3. Diff Engine → Database (llm_output + policy_validation)
   (Policy-aware AI analysis with LLM format)
      ↓
4. Supervisor → Database (aggregated_results + reports)
   (Final verdict + recommendations)
```

**💾 All data is stored in SQLite database** (`config_data/golden_config.db`)

### 🎯 LLM Output Format (NEW!)

The system now generates **adjudicator-friendly output** in a standardized format:

```json
{
  "meta": { "golden": "...", "candidate": "...", "generated_at": "..." },
  "overview": { "total_files": 5, "drifted_files": 2, "total_deltas": 37 },
  "high": [...],              // Critical drifts
  "medium": [...],            // Moderate drifts
  "low": [...],               // Minor drifts
  "allowed_variance": [...]   // Policy-approved
}
```

**Key Benefits**:
- ✅ **Batch Analysis**: 1 AI call per file (90% cost reduction)
- ✅ **Risk Categorization**: Automatic sorting into 4 buckets
- ✅ **Robust Parsing**: 4-tier JSON parsing with fallback
- ✅ **API Endpoint**: `GET /api/llm-output` for UI integration

📖 **Full Documentation**: [docs/LLM_OUTPUT_FORMAT.md](docs/LLM_OUTPUT_FORMAT.md)

## 📁 Project Structure

```
strands-multi-agent-system/
├── Agents/
│   ├── Supervisor/
│   │   ├── supervisor_agent.py      # Main orchestrator
│   │   └── README.md
│   └── workers/
│       ├── config_collector/
│       │   ├── config_collector_agent.py  # Git + drift.py
│       │   └── README.md
│       └── diff_policy_engine/
│           ├── diff_engine_agent.py       # AI analysis + policies
│           ├── prompts/                   # ⭐ NEW: LLM prompt templates
│           │   ├── __init__.py
│           │   └── llm_format_prompt.py
│           └── README.md
├── api/
│   ├── rest_server.py               # FastAPI server
│   └── README.md
├── shared/
│   ├── models.py                    # Pydantic models
│   ├── config.py                    # Configuration
│   ├── policies.yaml                # Policy rules
│   ├── drift_analyzer/              # drift.py module
│   │   ├── drift.py
│   │   └── __init__.py
│   └── README.md
├── config_data/                     # Data directory
│   └── golden_config.db             # SQLite database (all persistent data)
├── docs/                            # ⭐ NEW: Documentation
│   ├── LLM_OUTPUT_FORMAT.md         # LLM format guide
│   └── API_REFERENCE.md             # API documentation
├── tests/                           # ⭐ NEW: Test suite
│   ├── test_llm_format.py           # Unit tests
│   └── test_integration_llm.py      # Integration tests
├── test_pipeline.py                 # End-to-end test script
├── validate_policies.py             # Policy validation
├── POLICY_CUSTOMIZATION_GUIDE.md    # Policy guide
├── .env                             # Environment config
└── README.md                        # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- AWS account with Bedrock access
- GitLab repository access
- AWS credentials configured

### Installation

1. **Clone the repository**
   ```bash
   cd strands-multi-agent-system
   ```

2. **Install dependencies**
   ```bash
   # Install Strands SDK (from parent directory)
   pip install -e ../Strands-agent/sdk-python-main
   pip install -e ../Strands-agent/tools-main
   
   # Install other dependencies
   pip install boto3 gitpython python-dotenv colorlog pyyaml ruamel.yaml
   ```

3. **Configure environment**
   ```bash
   # Copy and edit .env file
   cp .env.example .env
   
   # Edit .env with your values:
   # - AWS_REGION
   # - BEDROCK_MODEL_ID
   # - GITLAB_TOKEN
   # - GITLAB_REPO_URL
   # - GOLDEN_BRANCH
   # - DRIFTED_BRANCH
   ```

4. **Validate setup**
   ```bash
   # Test policies
   python3 validate_policies.py
   
   # Test AWS credentials
   aws sts get-caller-identity
   ```

### Running Validation

#### Option 1: Programmatic (Python)

```python
from Agents.Supervisor.supervisor_agent import run_validation

result = run_validation(
    project_id="myorg/myrepo",
    mr_iid="123",
    repo_url="https://gitlab.verizon.com/saja9l7/golden_config.git",
    golden_branch="gold",
    drift_branch="feature-branch",
    target_folder=""  # Empty = analyze entire repo
)

print(f"Verdict: {result['data']['aggregated_results']['verdict']}")
print(f"Report: {result['data']['report_file']}")
```

#### Option 2: Test Script

```bash
# Edit test_pipeline.py with your repo details
python3 test_pipeline.py
```

#### Option 3: API Server

```bash
# Start the FastAPI server (runs on port 3000 by default, configurable via PORT env var)
python3 main.py

# Trigger validation via POST request
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "main_branch": "main",
    "environment": "prod"
  }'
```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# AWS Configuration
AWS_REGION=us-west-2
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# GitLab Configuration
GITLAB_TOKEN=your-gitlab-token
DEFAULT_REPO_URL=https://gitlab.verizon.com/saja9l7/golden_config.git
DEFAULT_GOLDEN_BRANCH=gold
DEFAULT_DRIFT_BRANCH=drift

# Logging
LOG_LEVEL=INFO
```

### Policy Rules (shared/policies.yaml)

Customize organizational rules:

```yaml
# Environment-specific files (allowed to differ)
env_allow_keys:
  - application-dev.yml
  - values-staging.yaml

# Invariant rules (always enforced)
invariants:
  - name: require_tls_in_production
    locator_contains: ssl.enabled
    forbid_values: [false]
    severity: critical
```

See `POLICY_CUSTOMIZATION_GUIDE.md` for details.

## 📊 Understanding Results

### Verdict Levels

- **✅ PASS**: No drift detected, safe to proceed
- **⚠️ WARN**: Low-risk changes, review recommended
- **🔍 REVIEW_REQUIRED**: Requires human approval
- **🚫 BLOCK**: Critical issues, deployment blocked

### Policy Tags

Changes are tagged based on policy evaluation:

- **`invariant_breach`**: Violates explicit rules → **BLOCKED**
- **`allowed_variance`**: Expected environment difference → **OK**
- **`suspect`**: Requires AI analysis → **CONTEXT-DEPENDENT**

### Output Files

```
config_data/
└── golden_config.db                            # SQLite database containing:
    ├── validation_runs                         # Run metadata
    ├── context_bundles                         # Structured deltas with locators
    ├── config_deltas                           # Individual delta records
    ├── llm_outputs                            # AI analysis + risk categorization
│   └── llm_output_20251005_123456.json          # Adjudicator-friendly format
├── aggregated_results/
│   └── aggregated_20251005_123456.json          # Supervisor aggregation
└── reports/
    └── validation_report_20251005_123456.md     # Final validation report
```

## 🌐 API Endpoints

The system provides RESTful API endpoints for integration:

### **Main Endpoints**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | UI Dashboard |
| `/health` | GET | Service health check |
| `/api/info` | GET | API information |
| `/api/validate` | POST | Trigger validation |
| `/api/latest-results` | GET | Get latest validation results |
| `/api/llm-output` ⭐ | GET | Get LLM output format (NEW) |
| `/api/config` | GET | Get environment config |

### **Usage Examples**

```bash
# Start the server
python main.py

# Trigger validation
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "golden_branch": "gold",
    "drift_branch": "drift"
  }'

# Get LLM output (NEW)
curl http://localhost:3000/api/llm-output

# Get latest results
curl http://localhost:3000/api/latest-results
```

📖 **Full API Documentation**: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

## 🔧 Customization

### Adding Policy Rules

Edit `shared/policies.yaml`:

```yaml
invariants:
  - name: your_custom_rule
    description: What this enforces
    locator_contains: config.key.path
    forbid_values: [value1, value2]
    severity: critical|high|medium|low
```

### Adjusting Agent Behavior

Each agent can be customized:

- **Supervisor**: `Agents/Supervisor/supervisor_agent.py`
- **Config Collector**: `Agents/workers/config_collector/config_collector_agent.py`
- **Diff Engine**: `Agents/workers/diff_policy_engine/diff_engine_agent.py`

### Environment-Specific Settings

Different strictness per environment:

```yaml
environment_rules:
  production:
    strictness: maximum
    require_approvals: true
  staging:
    strictness: high
    require_approvals: false
```

## 🧪 Testing

### Unit Tests ⭐ NEW

```bash
# Run LLM format unit tests
python tests/test_llm_format.py

# Expected output:
# ✅ Passed: 5/5
# ✅ Prompt building
# ✅ Output validation
# ✅ Drift categories
# ✅ Risk levels
# ✅ Sample format
```

### Integration Tests ⭐ NEW

```bash
# Run integration tests
python tests/test_integration_llm.py

# Expected output:
# ✅ Passed: 4/4
# ✅ Prompt generation
# ✅ Structure validation
# ✅ Schema validation
# ✅ Field completeness
```

### Manual Testing

```bash
# Test with your GitLab repos
python3 test_pipeline.py

# Expected output:
# ✅ Pipeline executed
# ✅ Verdict generated
# ✅ Report created
```

### Policy Validation

```bash
# Validate policies.yaml syntax
python3 validate_policies.py

# Expected: 
# ✅ YAML syntax valid
# ✅ 22 invariant rules
# ✅ 28 environment allowlist entries
```

## 📋 Troubleshooting

### Common Issues

1. **AWS Bedrock Access Error**
   ```
   Error: UnrecognizedClientException
   ```
   **Fix**: Request Bedrock model access in AWS Console

2. **Import Error (strands module)**
   ```
   ModuleNotFoundError: No module named 'strands'
   ```
   **Fix**: Install Strands SDK:
   ```bash
   pip install -e ../Strands-agent/sdk-python-main
   ```

3. **GitLab Authentication Failed**
   ```
   Error: 401 Unauthorized
   ```
   **Fix**: Check GITLAB_TOKEN in .env file

4. **Python Version Error**
   ```
   ERROR: Package 'strands-agents' requires Python: 3.10+
   ```
   **Fix**: Use Python 3.11+:
   ```bash
   python3.11 test_pipeline.py
   ```

## 📚 Documentation

- **`POLICY_CUSTOMIZATION_GUIDE.md`**: Complete guide for policy rules
- **`Agents/Supervisor/README.md`**: Supervisor agent details
- **`Agents/workers/config_collector/README.md`**: Config collector details
- **`Agents/workers/diff_policy_engine/README.md`**: Diff engine details
- **`api/README.md`**: API server documentation
- **`shared/README.md`**: Shared utilities documentation

## 🏗️ System Design

### Precision Analysis (drift.py)

The system uses `drift.py` for high-precision analysis:

- **Line-precise locators**: yamlpath, jsonpath, unidiff with exact line numbers
- **Structured deltas**: Each change is a separate, analyzable unit
- **Dependency analysis**: Parses npm, pip, Maven, Go dependencies
- **Specialized detectors**: Spring profiles, Jenkinsfiles, etc.

### Policy Enforcement

Hybrid approach: Explicit rules + AI context

1. **Explicit Rules** (`policies.yaml`): Fast, consistent, auditable
2. **AI Analysis**: Context-aware, handles edge cases
3. **Verdict Generation**: Combines both for intelligent decisions

### Multi-Agent Orchestration

- **Supervisor**: High-level orchestration with Claude 3.5 Sonnet
- **Workers**: Specialized tasks with Claude 3 Haiku (cost-effective)
- **File-Based Communication**: Scalable, provides audit trail

## 🔐 Security Considerations

- Store `.env` file securely (never commit to Git)
- Use IAM roles with minimum required permissions
- Rotate GitLab tokens regularly
- Review policy rules for compliance requirements
- Audit database (`config_data/golden_config.db`) for sensitive data
- Regular database backups recommended for production

## 🚧 Current Status

### ✅ Complete

- Multi-agent architecture (Phases 1-4)
- drift.py precision integration
- Policy-aware analysis
- Intelligent verdict logic
- File-based communication
- Comprehensive reporting
- Policy customization (Phase 6)
- Documentation & cleanup (Phase 7)

### ⏸️ Pending

- **End-to-end testing** (Phase 5 - requires AWS Bedrock access)

### 🔜 Future Enhancements

- MR remediation (auto-fix generation)
- S3 storage for outputs
- Slack/email notifications
- Historical drift tracking
- Dashboard/UI

## 🤝 Contributing

1. Read existing documentation
2. Test changes with `test_pipeline.py`
3. Validate policies with `validate_policies.py`
4. Update relevant README files
5. Follow existing code patterns

## 📝 License

[Add your license information]

## 💡 Support

For issues or questions:
1. Check troubleshooting section above
2. Review documentation in each folder
3. Validate your configuration
4. Test with `test_pipeline.py`

---

**Built with:**
- AWS Strands Multi-Agent Framework
- AWS Bedrock (Claude 3.5 Sonnet & Claude 3 Haiku)
- drift.py precision analysis
- GitLab integration
- Policy-driven validation

**Last Updated:** 2025-10-05
