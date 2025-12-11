# Guardrails & Policy Engine Agent

## Overview

The **Guardrails & Policy Engine Agent** enforces security guardrails and organizational policies before final certification.

## Responsibilities

1. **PII Redaction**
   - Detect personally identifiable information
   - Detect credentials and secrets
   - Redact sensitive data before further processing
   - Generate PII compliance report

2. **Intent Guard**
   - Detect malicious patterns (SQL injection, command injection)
   - Identify suspicious configurations
   - Flag backdoor attempts
   - Validate against security best practices

3. **Policy Validation**
   - Enforce rules from `policies.yaml`
   - Apply policy tags (invariant_breach, allowed_variance, suspect)
   - Check environment-specific allowlists
   - Validate against compliance requirements

4. **Compliance Checking**
   - Ensure required evidence exists
   - Validate approval workflows
   - Check for required documentation
   - Audit trail completeness

## Input

**From:** Drift Detector Agent

**Format:** 
- `context_bundle` from Drift Detector Agent (loaded from database via `run_id`)
- Original deltas with old/new values (raw, before PII redaction)

**Note:** This agent runs **BEFORE** Triaging-Routing Agent, so no LLM output is available yet.

## Output

**To:** Certification Engine Agent

**Format:** `policy_validated_deltas.json`
```json
{
  "meta": {
    "validated_at": "2025-12-01T10:53:00Z",
    "pii_found": true,
    "pii_redacted_count": 3,
    "policy_violations": 2,
    "suspicious_patterns": 0
  },
  "validated_deltas": [
    {
      "id": "cfg~application.yml.database.password",
      "category": "config",
      "file": "application.yml",
      "locator": {...},
      "old": "[REDACTED_PASSWORD]",
      "new": "[REDACTED_PASSWORD]",
      "pii_redacted": true,
      "pii_types": ["password"],
      "policy": {
        "tag": "invariant_breach",
        "rule": "no_hardcoded_passwords",
        "severity": "critical",
        "violation": true,
        "reason": "Passwords must use environment variables"
      },
      "intent_guard": {
        "suspicious": false,
        "patterns_detected": []
      },
      "ai_analysis": {...}
    }
  ],
  "pii_report": {
    "instances_found": 3,
    "types": ["password", "api_key", "email"],
    "redacted": true
  },
  "intent_report": {
    "suspicious_patterns": [],
    "safe": true
  },
  "policy_summary": {
    "total_violations": 2,
    "critical": 1,
    "high": 1,
    "medium": 0,
    "low": 0
  }
}
```

## Processing Steps

1. **Load Input Data**
   - Load `context_bundle` from database using `run_id` (from Drift Detector Agent)
   - Extract deltas with original old/new values (raw, unredacted)

2. **PII Detection & Redaction**
   - Scan all delta values for PII patterns
   - Detect: emails, phones, SSNs, credit cards
   - Detect: API keys, passwords, tokens, private keys
   - Detect: Cloud provider credentials (AWS, GCP, Azure)
   - Redact sensitive data: `[REDACTED_PASSWORD]`

3. **Intent Guard Scanning**
   - Check for SQL injection patterns
   - Check for command injection attempts
   - Detect suspicious port numbers (4444, 31337)
   - Flag debug mode in production

4. **Policy Validation**
   - Load rules from `shared/policies.yaml`
   - Apply invariant rules (always enforced)
   - Check environment allowlists
   - Tag each delta with policy status

5. **Generate Reports**
   - Create PII report
   - Create intent guard report
   - Create policy violation summary
   - Save validated deltas

## PII Patterns Detected

### Personal Information
- Email addresses
- US phone numbers: `(555) 123-4567`
- International phones: `+1-555-123-4567`
- SSN: `123-45-6789`

### Financial
- Credit cards: `4111-1111-1111-1111`
- IBAN: `DE89370400440532013000`

### Credentials & Secrets
- API keys: `api_key=sk_live_abc123xyz`
- Passwords: `password=P@ssw0rd!`
- JWT tokens: `eyJhbGciOiJIUzI1Ni...`
- Private keys: `-----BEGIN RSA PRIVATE KEY-----`

### Cloud Provider Keys
- AWS Access Key: `AKIA[A-Z0-9]{16}`
- AWS Secret: `[A-Za-z0-9/+=]{40}`
- GCP API Key: `AIza[A-Za-z0-9_-]{35}`
- Azure Key: `[a-f0-9]{64}`
- GitLab Token: `glpat-[A-Za-z0-9_-]{20}`
- GitHub Token: `ghp_[A-Za-z0-9]{36}`

## Intent Guard Patterns

### SQL Injection
```sql
'; DROP TABLE users; --
' OR '1'='1
UNION SELECT * FROM passwords
```

### Command Injection
```bash
; rm -rf /
&& cat /etc/passwd
$(malicious_command)
```

### Backdoor Ports
- 4444 (Metasploit)
- 31337 (Elite/leet)
- 1337 (Leet)

### Security Misconfigurations
- `debug: true` in production
- `DEBUG_MODE=true` in prod config
- Wildcard CORS: `allowed-origins: "*"`

## Policy Rules (from policies.yaml)

### Environment Allowlist
Files expected to differ per environment:
- `application-dev.yml`
- `application-staging.yml`
- `values-prod.yaml`
- Kubernetes overlays

### Invariant Rules (Always Enforced)

**Critical Severity:**
- SSL/TLS must be enabled in production
- No hardcoded passwords
- Authentication must be enabled
- Encryption at rest required

**High Severity:**
- Database SSL required
- Security headers configured
- Actuator endpoints protected
- CORS properly restricted

**Medium Severity:**
- Session timeouts configured
- Audit logging enabled
- Rate limiting configured

## Configuration

```yaml
# guardrails_config.yaml
pii_detection:
  enabled: true
  redaction_enabled: true
  block_on_detection: false  # Just redact, don't block

intent_guard:
  enabled: true
  block_on_suspicious: true  # Block suspicious patterns
  patterns: "strict"  # strict | moderate | lenient

policy_validation:
  enabled: true
  policies_file: "shared/policies.yaml"
  strict_mode: true  # Fail on any violation
```

## Error Handling

- Parse errors: Mark delta as "manual_review_required"
- Missing policies.yaml: Use default safe policies
- PII detection failure: Log error, continue (safe default)
- Policy validation failure: Block deployment (fail-safe)

## Performance

- Typical processing time: 5-10 seconds for 100 deltas
- PII scanning: ~20ms per delta
- Policy validation: ~5ms per delta
- Regex-based, very fast

## Dependencies

- `re` - Regex pattern matching
- `shared.policies` - Policy loader
- `json` - Data serialization

