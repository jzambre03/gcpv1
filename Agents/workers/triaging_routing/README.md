# Triaging-Routing Agent

## Overview

The **Triaging-Routing Agent** uses AI (Claude Haiku) to analyze and categorize configuration deltas with intelligent risk assessment.

## Responsibilities

1. **LLM-Based Analysis**
   - Analyze each delta using Claude AI
   - Understand semantic meaning of changes
   - Generate human-readable explanations

2. **Hard Fail Detection**
   - Identify critical violations immediately
   - Flag security risks (SSL disabled, hardcoded credentials)
   - Detect breaking changes

3. **Risk Categorization**
   - HIGH: Critical issues requiring immediate attention
   - MEDIUM: Moderate risks requiring review
   - LOW: Minor changes, low impact
   - ALLOWED: Expected variance (environment-specific)

4. **Verdict Assignment**
   - NO_DRIFT: No meaningful changes
   - NEW_BUILD_OK: Safe new configuration
   - DRIFT_WARN: Changes need review
   - DRIFT_BLOCKING: Critical violations, block deployment

## Input

**From:** Drift Detector Agent

**Format:** `context_bundle.json`

## Output

**To:** Guardrails & Policy Engine Agent

**Format:** `triaged_deltas.json`
```json
{
  "meta": {
    "triaged_at": "2025-12-01T10:52:00Z",
    "total_deltas_analyzed": 125,
    "llm_model": "claude-3-haiku-20240307"
  },
  "triaged_deltas": [
    {
      "id": "cfg~application.yml.server.port",
      "category": "config",
      "file": "application.yml",
      "locator": {...},
      "old": 8080,
      "new": 9090,
      "ai_analysis": {
        "risk_level": "LOW",
        "verdict": "DRIFT_WARN",
        "explanation": "Port change from 8080 to 9090. Low risk if firewall rules updated.",
        "impact": "Service will listen on different port, requires infrastructure update",
        "hard_fail": false
      }
    }
  ],
  "hard_fails": [...],
  "risk_summary": {
    "high": 3,
    "medium": 15,
    "low": 107
  }
}
```

## Processing Steps

1. **Load Context Bundle**
   - Read deltas from Drift Detector output
   - Group deltas by file for batch processing

2. **Batch AI Analysis**
   - Process up to 10 deltas per file at once
   - Call Claude API with specialized prompts
   - Parse JSON responses

3. **Risk Assessment**
   - Evaluate each delta's impact
   - Assign risk level based on change type
   - Detect hard failures (critical violations)

4. **Generate Verdicts**
   - Apply verdict logic per delta
   - Consider environment context
   - Flag blocking issues

5. **Create Output**
   - Structure triaged deltas
   - Add AI insights
   - Save to triaged_deltas.json

## LLM Prompts

Uses specialized prompts from `prompts/triaging_prompt.py`:

- **Configuration Change Analysis**: Understand config modifications
- **Dependency Update Analysis**: Assess version changes
- **Security Impact Analysis**: Identify security implications
- **Breaking Change Detection**: Find incompatible changes

## Hard Fail Criteria

Automatically flagged as hard fails:
- SSL/TLS disabled in production
- Hardcoded passwords/secrets
- Security headers removed
- Authentication disabled
- Debug mode in production

## Risk Level Logic

**HIGH Risk:**
- Security configuration changes
- Database connection changes
- Authentication/authorization changes
- Production-specific changes

**MEDIUM Risk:**
- Timeout/retry configuration
- Dependency version updates
- Resource limit changes
- Logging level changes

**LOW Risk:**
- Comment updates
- Whitespace changes
- Non-critical property changes
- Development-only changes

## Configuration

```yaml
# triaging_config.yaml
llm_model: "claude-3-haiku-20240307"
batch_size: 10
max_tokens: 4096
temperature: 0.3
timeout_seconds: 30
```

## Error Handling

- API failures: Retry up to 3 times with exponential backoff
- Parse errors: Mark as "requires_manual_review"
- Timeout: Skip to next batch, log warning

## Performance

- Typical processing time: 15-30 seconds for 100 deltas
- Uses batch processing for efficiency
- Parallel processing for multiple files

## Dependencies

- `strands` - Agent framework
- `anthropic` / `boto3` - LLM API
- `shared.model_factory` - Model configuration

