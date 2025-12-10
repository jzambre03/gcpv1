# Database Schema Fix - policy_validations Table

**Date:** December 10, 2024  
**Issue:** Schema mismatch between Guardrails & Policy Agent output and database storage  
**Status:** ✅ RESOLVED

---

## 🔴 Problem Identified

The `save_policy_validation()` function in `shared/db.py` was expecting different field names than what the Guardrails & Policy Agent was actually producing, causing all count columns to be stored as `0` in the database.

### Field Name Mismatches

| Database Column | Expected Field | Actual Agent Field | Impact |
|-----------------|----------------|-------------------|--------|
| `pii_findings_count` | `pii_report.total_findings` | `pii_report.instances_found` | ❌ Always 0 |
| `intent_violations_count` | `intent_report.violations_count` | `intent_report.total_findings` | ❌ Always 0 |
| `policy_violations_count` | `policy_summary.violations` | `policy_summary.total_violations` | ❌ Always 0 |
| `policy_warnings_count` | `policy_summary.warnings` | `policy_summary.medium + low` | ❌ Always 0 |

---

## ✅ Solution Implemented

**File Modified:** `shared/db.py` (lines 445-479)

**Approach:** Modified the database save function to correctly map agent output fields to database schema columns.

### Code Changes

```python
def save_policy_validation(run_id: str, validation_data: Dict[str, Any]) -> None:
    """
    Save policy validation results.
    
    Maps agent output field names to database schema:
    - pii_report.instances_found → pii_findings_count
    - intent_report.total_findings → intent_violations_count
    - policy_summary.total_violations → policy_violations_count
    - policy_summary.medium + low → policy_warnings_count
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Extract data with correct field mappings
        pii_report = validation_data.get('pii_report', {})
        intent_report = validation_data.get('intent_report', {})
        policy_summary = validation_data.get('policy_summary', {})
        
        # Calculate warnings count (medium + low severity violations)
        warnings_count = policy_summary.get('medium', 0) + policy_summary.get('low', 0)
        
        cursor.execute("""
            INSERT INTO policy_validations (
                run_id, pii_findings_count, intent_violations_count,
                policy_violations_count, policy_warnings_count, validation_data
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            pii_report.get('instances_found', 0),        # ✅ Fixed
            intent_report.get('total_findings', 0),      # ✅ Fixed
            policy_summary.get('total_violations', 0),   # ✅ Fixed
            warnings_count,                              # ✅ Fixed
            json.dumps(validation_data)
        ))
```

---

## 🧪 Verification

**Test Results:** ✅ ALL TESTS PASSED

Sample test data:
- `pii_report.instances_found: 5` → `pii_findings_count: 5` ✅
- `intent_report.total_findings: 3` → `intent_violations_count: 3` ✅
- `policy_summary.total_violations: 8` → `policy_violations_count: 8` ✅
- `policy_summary.medium (2) + low (1)` → `policy_warnings_count: 3` ✅

---

## 📊 Impact Analysis

### Before Fix
```sql
SELECT * FROM policy_validations WHERE run_id = 'example';
-- Result:
-- pii_findings_count: 0 ❌
-- intent_violations_count: 0 ❌
-- policy_violations_count: 0 ❌
-- policy_warnings_count: 0 ❌
```

### After Fix
```sql
SELECT * FROM policy_validations WHERE run_id = 'example';
-- Result:
-- pii_findings_count: 5 ✅ (correct value from agent)
-- intent_violations_count: 3 ✅ (correct value from agent)
-- policy_violations_count: 8 ✅ (correct value from agent)
-- policy_warnings_count: 3 ✅ (medium 2 + low 1)
```

---

## 🎯 Why This Approach?

### ✅ Advantages
1. **Single file change** - Only `shared/db.py` modified
2. **Clean agent code** - Agent output remains semantically correct
3. **No duplication** - Avoids maintaining redundant fields
4. **Proper layering** - Database adapts to domain model (not vice versa)
5. **Low risk** - Isolated change in storage layer

### 📝 Design Principle
The database save function acts as an **adapter/mapper** between the domain model (agent output) and the storage schema. This is the correct architectural pattern.

---

## 🔄 Related Files

### Modified
- `shared/db.py` - Database save function fixed

### Verified Compatible
- `Agents/workers/guardrails_policy/guardrails_policy_agent.py` - No changes needed
- `Agents/workers/pii_redactor.py` - No changes needed
- `Agents/workers/intent_guard.py` - No changes needed

---

## 📚 Agent Output Schema (for reference)

The Guardrails & Policy Agent produces this structure:

```python
{
    "meta": {
        "validated_at": "ISO timestamp",
        "pii_found": bool,
        "pii_redacted_count": int,
        "policy_violations": int,
        "suspicious_patterns": int,
        "environment": str
    },
    "pii_report": {
        "instances_found": int,      # ← Maps to pii_findings_count
        "types": [str],
        "redacted": bool
    },
    "intent_report": {
        "suspicious_patterns": [str],
        "total_findings": int,       # ← Maps to intent_violations_count
        "critical_findings": int,
        "safe": bool
    },
    "policy_summary": {
        "total_violations": int,     # ← Maps to policy_violations_count
        "critical": int,
        "high": int,
        "medium": int,              # ← medium + low = warnings_count
        "low": int                  # ← medium + low = warnings_count
    },
    "validated_deltas": [...],
    "llm_summary": {...},
    "overview": {...}
}
```

---

## ✅ Validation Checklist

- [x] Database schema remains unchanged
- [x] Agent output format remains unchanged
- [x] All field mappings are correct
- [x] Warnings count calculation is correct (medium + low)
- [x] Full data preserved in JSON column
- [x] No linting errors
- [x] Test verification passed
- [x] Documentation updated

---

## 🚀 Deployment Notes

- **No database migration required** - Schema unchanged
- **No agent code changes required** - Only DB layer modified
- **Backward compatible** - Existing data unaffected
- **Safe to deploy immediately** - Low risk change

---

**Resolution Date:** December 10, 2024  
**Verified By:** Automated test suite  
**Status:** ✅ PRODUCTION READY

