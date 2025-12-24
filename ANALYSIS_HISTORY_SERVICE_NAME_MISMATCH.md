# ANALYSIS HISTORY - SERVICE NAME MATCHING ISSUE

## 🔍 Problem: History Shows for Some Services But Not Others

### Root Cause Analysis

#### How Service Names Work:

1. **When Analysis is Triggered** (main.py:780):
   ```python
   project_id = f"{service_id}_{environment}"
   # Example: "cxp_ptg_adapter_beta2"
   ```

2. **When Validation Run is Created** (supervisor_agent.py:116):
   ```python
   service_name = project_id.rsplit('_', 1)[0]
   # Extracts: "cxp_ptg_adapter" from "cxp_ptg_adapter_beta2"
   ```

3. **When History is Fetched** (main.py:1517):
   ```python
   filtered_runs = [run for run in all_runs 
                    if run.get('service_name') == service_id 
                    and run.get('environment') == environment]
   # Looks for: service_name = "cxp_ptg_adapter" AND environment = "beta2"
   ```

### ✅ This Should Work!

The logic is correct:
- Analysis for `cxp_ptg_adapter/beta2` creates run with `service_name='cxp_ptg_adapter'`
- History tab filters by `service_name='cxp_ptg_adapter'`
- **Should match perfectly!**

### ❌ But Why Doesn't It Show?

**Possible Issues**:

1. **VSAT Prefix in Service ID**:
   - Service ID might be: `saja9l7_cxp_ptg_adapter`
   - Run service_name is: `saja9l7_cxp_ptg_adapter_beta2` → extracts to `saja9l7_cxp_ptg_adapter`
   - But service page uses ID: `cxp_ptg_adapter` (without VSAT prefix)
   - **MISMATCH**: Looking for `cxp_ptg_adapter` but DB has `saja9l7_cxp_ptg_adapter`!

2. **Old Runs with Different Naming**:
   - Runs created before service table was populated
   - Runs from test/verification scripts
   - Runs with manually set service names

3. **Case Sensitivity**:
   - Service ID: `CXP_PTG_Adapter`
   - Run service_name: `cxp_ptg_adapter`
   - **MISMATCH**: Different cases!

## ✅ Fix Applied

Updated filtering logic to handle these cases:

```python
for run in all_runs:
    run_service = run.get('service_name', '')
    run_env = run.get('environment', '')
    
    # 1. Exact match
    if run_service == service_id and run_env == environment:
        filtered_runs.append(run)
    
    # 2. VSAT prefix: run has "vsat_service", page uses "service"
    elif run_service.endswith(f"_{service_id}") and run_env == environment:
        filtered_runs.append(run)
    
    # 3. VSAT prefix reversed: page has "vsat_service", run has "service"
    elif service_id.endswith(f"_{run_service}") and run_env == environment:
        filtered_runs.append(run)
```

## 🧪 Debug Steps

### Check Your Actual Data:

```python
# Run this to see actual service IDs and run service names
python3 -c "
from shared.db import get_all_services, get_all_validation_runs

print('Services:')
for s in get_all_services(active_only=True, with_branches_only=False):
    print(f'  ID: {s[\"service_id\"]}')

print('\nRuns:')
for r in get_all_validation_runs():
    print(f'  service_name: {r[\"service_name\"]}, env: {r[\"environment\"]}')
"
```

### Check Browser Console:

When you open Analysis History tab, you'll see:
```
📊 HistoryTab: Loading run history for SERVICE_ID/ENV
   Unique service names in database: ['...', '...']
   Looking for service_id: 'YOUR_SERVICE_ID'
      Checking run: service_name='...', env='...'
         ✅ MATCHED (exact/suffix/prefix)
```

### Check Server Logs:

Look for lines like:
```
📊 Run history request: service_id=..., environment=...
   Total runs in database: N
   Unique service names in database: [...]
   Looking for service_id: '...'
   Filtered runs for .../...: N
```

## 🎯 Most Likely Causes

### If Some Services Show History But Others Don't:

1. **VSAT Prefix Mismatch**:
   - Check if service IDs in the services table have VSAT prefix
   - Check if runs in database have VSAT prefix
   - The new filtering logic should handle this

2. **No Runs Actually Exist**:
   - Check database: Are there runs for that service_id/environment?
   - Run may have failed before saving
   - Run may be saved with different service name

3. **Service Was Renamed**:
   - Old runs have old name
   - New service table has new name
   - Won't match unless you update old runs

## ✅ What to Do Now

1. **Check the logs** (browser console and server logs)
2. **Look for the mismatch** between service_id and run service_name
3. **Let me know what you find**, and I can provide a more specific fix

The enhanced logging will tell you exactly why runs aren't matching!

