# Analysis History - Complete Data Flow Verification

## ✅ Data Sources

### 1. **validation_runs table**
- `run_id` - Unique identifier
- `verdict` - PASS/WARN/BLOCK/REVIEW_REQUIRED
- `status` - running/completed/failed
- `created_at` - Timestamp
- `execution_time_ms` - Execution time in milliseconds
- `golden_branch` - Golden branch name
- `drift_branch` - Drift branch name
- `environment` - prod/dev/qa/staging
- `service_name` - Service identifier

### 2. **llm_outputs table**
Accessed via `get_llm_output(run_id)`

Returns structure:
```json
{
  "summary": {
    "total_config_files": 15,
    "files_with_drift": 3,
    "total_drifts": 42,
    "high_risk": 5,
    "medium_risk": 12,
    "low_risk": 20,
    "allowed_variance": 5
  },
  "meta": { ... },
  "overview": { ... },
  "high": [...],
  "medium": [...],
  "low": [...],
  "allowed_variance": [...]
}
```

### 3. **context_bundles table**
Accessed via `get_latest_context_bundle(run_id)`

Returns structure:
```json
{
  "overview": {
    "total_files": 15,
    "files_with_drift": 3,
    "total_deltas": 42,
    "golden_files": 15,
    "candidate_files": 15
  },
  "meta": { ... },
  "deltas": [...]
}
```

### 4. **policy_validations table**
Accessed via `get_policy_validation(run_id)`

Returns structure:
```json
{
  "validation_data": {
    "policy_summary": {
      "total_violations": 8,
      "high": 2,
      "medium": 3,
      "low": 3
    },
    "pii_report": { ... },
    "intent_report": { ... }
  }
}
```

## ✅ API Response Transformation

### Endpoint: `GET /api/services/{service_id}/run-history/{environment}`

#### Metrics Object Construction:

```python
metrics = {
    # From LLM Output (summary)
    'total_drifts': summary.get('total_drifts', 0),           # 42
    'high_risk': summary.get('high_risk', 0),                 # 5
    'medium_risk': summary.get('medium_risk', 0),             # 12
    'low_risk': summary.get('low_risk', 0),                   # 20
    'allowed_variance': summary.get('allowed_variance', 0),   # 5
    'files_with_drift': summary.get('files_with_drift', 0),  # 3
    
    # From Context Bundle (overview)
    'total_deltas': overview.get('total_deltas', 0),         # 42
    
    # From Policy Validation (policy_summary)
    'policy_violations': policy_summary.get('total_violations', 0),  # 8
    
    # Calculated from risk distribution
    'overall_risk_level': 'high' | 'medium' | 'low' | 'unknown'
}
```

#### Complete Run Object:

```python
{
    'run_id': 'run_20251224_123045_cxp_ptg_adapter_prod',
    'verdict': 'WARN',
    'status': 'completed',
    'timestamp': '2025-12-24T12:30:45.123Z',
    'created_at': '2025-12-24T12:30:45.123Z',
    'environment': 'prod',
    'service_name': 'cxp_ptg_adapter',
    'execution_time_seconds': 45.5,  # Converted from execution_time_ms
    'metrics': {
        'files_with_drift': 3,
        'total_deltas': 42,
        'policy_violations': 8,
        'overall_risk_level': 'medium',
        'total_drifts': 42,
        'high_risk': 5,
        'medium_risk': 12,
        'low_risk': 20,
        'allowed_variance': 5
    },
    'branches': {
        'golden_branch': 'golden_prod_20251224_120000_abc123',
        'drift_branch': 'drift_prod_20251224_123045_def456'
    }
}
```

## ✅ UI Display Mapping

### Analysis History Card Shows:

```
Run #5                                           [⚠️ WARN]
Dec 24, 12:30 PM

3 files drifted • 42 changes • 8 violations • Risk: medium

Golden: golden_prod_20251224_120000_abc123
Drift: drift_prod_20251224_123045_def456

⏱️ Execution time: 45.5s

→ Click to view detailed analysis (run_20251224_123045_cxp_ptg...)
```

### Field Mapping:
- **Run number**: Calculated from array index (reversed)
- **Timestamp**: `run.timestamp` → formatted as "Dec 24, 12:30 PM"
- **Verdict badge**: `run.verdict` → Badge component
- **Files drifted**: `metrics.files_with_drift`
- **Changes**: `metrics.total_deltas`
- **Violations**: `metrics.policy_violations`
- **Risk level**: `metrics.overall_risk_level`
- **Golden branch**: `branches.golden_branch`
- **Drift branch**: `branches.drift_branch`
- **Execution time**: `run.execution_time_seconds`
- **Run ID**: `run.run_id`

## ✅ Data Flow Chain

```
1. User runs analysis
   ↓
2. Supervisor creates validation_run
   ↓
3. Drift Detector saves context_bundle
   ↓
4. Guardrails saves policy_validation
   ↓
5. Triaging saves llm_output
   ↓
6. Certification Engine updates validation_run (verdict, execution_time_ms)
   ↓
7. UI calls /api/services/{id}/run-history/{env}
   ↓
8. API fetches:
   - validation_runs (run data)
   - llm_outputs (metrics)
   - context_bundles (deltas)
   - policy_validations (violations)
   ↓
9. API transforms to UI format
   ↓
10. UI displays complete run card
```

## ✅ Fixes Applied

1. **Import Fix**: Added `get_latest_context_bundle` to imports
2. **Function Call Fix**: Changed `get_context_bundle(run_id)` to `get_latest_context_bundle(run_id)`
3. **Data Structure Fix**: Changed `bundle_data.get('total_deltas')` to `overview.get('total_deltas')`
4. **Branch Names Fix**: Changed `'golden': ...` to `'golden_branch': ...`
5. **Execution Time Fix**: Added conversion from `ms` to `seconds`
6. **Risk Level Calculation**: Added logic to determine overall risk from distribution

## ✅ Verification Checklist

- [x] Run ID displays correctly
- [x] Verdict badge shows (PASS/WARN/BLOCK)
- [x] Timestamp formats as "Dec 24, 12:30 PM"
- [x] Files with drift count (from LLM summary or context bundle)
- [x] Total changes/deltas count (from context bundle overview)
- [x] Policy violations count (from policy validation)
- [x] Overall risk level (calculated from LLM risk distribution)
- [x] Golden branch name (from validation_runs)
- [x] Drift branch name (from validation_runs)
- [x] Execution time in seconds (converted from ms)
- [x] Click to view opens run details

All data should now populate correctly! 🎉

