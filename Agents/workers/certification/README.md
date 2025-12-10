# Certification Engine Agent

## Overview

The **Certification Engine Agent** makes the final certification decision based on all previous analysis and calculates confidence scores for auto-merge decisions.

## Responsibilities

1. **Confidence Score Calculation**
   - Calculate 0-100 confidence score
   - Factor in policy violations, risk levels, evidence
   - Apply environment-specific modifiers

2. **Certification Decision**
   - AUTO_MERGE: Score ≥ 75 (or 85 for production)
   - HUMAN_REVIEW: Score 50-74 (or 60-84 for production)
   - BLOCK_MERGE: Score < 50 (or < 60 for production)

3. **Snapshot Creation**
   - Create certified snapshot branch if AUTO_MERGE
   - Include certification metadata
   - Tag snapshot with confidence score

4. **Report Generation**
   - Generate certification report
   - Include score breakdown
   - Document decision rationale

## Input

**From:** Guardrails & Policy Engine Agent

**Format:** `policy_validated_deltas.json`

## Output

**To:** Supervisor Agent (final aggregation)

**Format:** `certification_result.json`
```json
{
  "meta": {
    "certified_at": "2025-12-01T10:54:00Z",
    "certification_id": "cert_20251201_105400",
    "run_id": "run_20251201_105000"
  },
  "confidence_score": 85,
  "confidence_breakdown": {
    "base_score": 100,
    "policy_deductions": -10,
    "risk_deductions": -5,
    "evidence_bonus": 0,
    "final_score": 85
  },
  "certification_decision": "AUTO_MERGE",
  "decision_details": {
    "action": "build",
    "gitlab_status": "success",
    "auto_merge_eligible": true,
    "threshold_used": 75,
    "reason": "High confidence - all checks passed, no critical violations"
  },
  "snapshot_branch": "snapshot_gcp_prod_20251201_cert85",
  "summary": {
    "total_deltas": 125,
    "policy_violations": 0,
    "critical_violations": 0,
    "high_risk": 0,
    "medium_risk": 15,
    "low_risk": 110
  }
}
```

## Processing Steps

1. **Load Policy-Validated Deltas**
   - Read output from Guardrails & Policy Engine
   - Extract policy violations and risk levels

2. **Calculate Confidence Score**
   - Start with base score: 100
   - Deduct for policy violations
   - Deduct for risk levels
   - Add bonuses for evidence completeness
   - Apply environment modifiers

3. **Make Certification Decision**
   - Compare score to environment thresholds
   - Generate decision (AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE)
   - Determine GitLab action (build/review/break)

4. **Create Snapshot (if AUTO_MERGE)**
   - Generate snapshot branch name
   - Create branch from golden branch
   - Add certification metadata file
   - Push to remote

5. **Generate Report**
   - Create certification record
   - Save to certification history
   - Return to Supervisor

## Confidence Score Calculation

### Base Score: 100 points

### Deductions:
- **Critical Policy Violation**: -30 points each
- **High Severity Violation**: -15 points each
- **Medium Severity Violation**: -5 points each
- **Critical Risk Level**: -40 points
- **High Risk Level**: -25 points
- **Medium Risk Level**: -10 points
- **Missing Evidence**: -20 points
- **Incomplete Testing**: -10 points

### Bonuses:
- **All Evidence Present**: +20 points
- **Historical Approval Pattern**: +10 points
- **Automated Test Pass**: +10 points

### Environment Modifiers:
- **Production**: Stricter thresholds (85+ for auto-merge)
- **Staging**: Standard thresholds (75+ for auto-merge)
- **Development**: Lenient thresholds (65+ for auto-merge)

## Decision Thresholds

### Production Environment
- **85-100**: AUTO_MERGE ✅
- **60-84**: HUMAN_REVIEW ⚠️
- **0-59**: BLOCK_MERGE 🚫

### Staging Environment
- **75-100**: AUTO_MERGE ✅
- **50-74**: HUMAN_REVIEW ⚠️
- **0-49**: BLOCK_MERGE 🚫

### Development Environment
- **65-100**: AUTO_MERGE ✅
- **40-64**: HUMAN_REVIEW ⚠️
- **0-39**: BLOCK_MERGE 🚫

## Snapshot Creation

When AUTO_MERGE is approved:

1. **Branch Naming**: `snapshot_{service}_{env}_{YYYYMMDD_HHMMSS}_cert{score}`
   - Example: `snapshot_gcp_prod_20251201_105400_cert85`

2. **Metadata File**: `.golden-config-certification.json`
   ```json
   {
     "certified_at": "2025-12-01T10:54:00Z",
     "certification_id": "cert_20251201_105400",
     "confidence_score": 85,
     "decision": "AUTO_MERGE",
     "source_golden_branch": "golden_prod_20251201",
     "validation_run_id": "run_20251201_105000"
   }
   ```

3. **Git Tag**: `certified-{YYYYMMDD}-{score}`
   - Example: `certified-20251201-85`

## Certification History

All certifications are stored in:
- `config_data/certification_history.json`
- `config_data/snapshots.json`

## Error Handling

- Score calculation failure: Default to HUMAN_REVIEW (safe)
- Snapshot creation failure: Log error, continue without snapshot
- GitLab API failure: Retry up to 3 times

## Performance

- Typical processing time: 2-5 seconds
- Snapshot creation: 10-30 seconds (async, doesn't block)
- Very fast decision making

## Dependencies

- `shared.confidence_scorer` - Score calculation
- `shared.git_operations` - Snapshot creation
- `shared.certification_history` - History tracking
- `json` - Data serialization

