# 🔧 ANALYSIS HISTORY FIX - TESTING CHECKLIST

## ✅ Changes Made

### Backend (`main.py`)
1. ✅ Changed endpoint from `/api/services/{service_id}/run-history/{environment}` to `/api/services/{service_id}/run-history`
2. ✅ Made `environment` parameter optional (query parameter)
3. ✅ Updated filtering logic to handle optional environment
4. ✅ Updated response format

### Frontend (`api/templates/branch_env.html`)
1. ✅ Changed state from `runHistory` to `allRunHistory`
2. ✅ Changed API URL to remove environment from path
3. ✅ Added client-side filtering with `useMemo`
4. ✅ Added "All Environments" dropdown option
5. ✅ Changed `selectedEnv` default from `'prod'` to `'all'`
6. ✅ Updated UI to use `filteredRunHistory`
7. ✅ Added environment badges when viewing all
8. ✅ Updated dependency array (removed `selectedEnv`)

---

## 🧪 Testing Steps

### Step 1: Start the Server
```bash
cd /Users/jayeshzambre/Documents/GitHub/gcpv1
python3 main.py
```

**Expected**: Server starts on `http://localhost:8000`

**If you get `ModuleNotFoundError: No module named 'apscheduler'`:**
```bash
pip install apscheduler watchdog python-dotenv fastapi uvicorn
```

---

### Step 2: Open Browser Console
1. Open your browser
2. Go to `http://localhost:8000`
3. Open Developer Tools (F12)
4. Go to Console tab

---

### Step 3: Navigate to a Service
1. Click on any service (e.g., `cxp-ptg-adapter`)
2. Click on "Analysis History" tab

---

### Step 4: Check Console Logs

**You should see**:
```
📊 HistoryTab: Loading ALL run history for <service-id>
   Fetching: /api/services/<service-id>/run-history
   Response status: 200 OK
   Response data: {service_id: "...", all_environments: true, runs: [...]}
   Number of runs: X
   Loading complete
```

**If you see an error**, note what it says and share it.

---

### Step 5: Check What's Displayed

#### If runs exist:
- ✅ Should show: "Analysis History (X runs)"
- ✅ Dropdown should show: "All Environments" (selected)
- ✅ Each run should have an environment badge (PROD, BETA2, etc.)
- ✅ Runs from all environments should be visible

#### If no runs exist:
- ✅ Should show: "No analysis runs yet for any environment"
- ✅ Should show "Run Analysis Now" button

---

### Step 6: Test Filtering

1. **Click dropdown** → Select specific environment (e.g., BETA2)
2. **Should be instant** (no loading spinner)
3. **Should show only runs** for that environment
4. **Environment badges should disappear** (since all are same env)
5. **Count should update** (e.g., "Analysis History (3 runs)")

1. **Click dropdown** → Select "All Environments"
2. **Should show all runs again**
3. **Environment badges should reappear**

---

## 🐛 Common Issues & Fixes

### Issue 1: "Loading forever"
**Symptom**: Tab shows "Loading analysis history..." forever

**Check**:
1. Is the server running?
2. Open browser console - any errors?
3. Open Network tab - is the request completing?

**Fix**: Check server logs for errors

---

### Issue 2: "No runs" but runs exist
**Symptom**: Shows "No runs" even though database has runs

**Check**:
1. Browser console - what does the API response show?
2. Server logs - what does it say about filtered runs?

**Debug**:
```bash
cd /Users/jayeshzambre/Documents/GitHub/gcpv1
python3 -c "
from shared.db import get_all_validation_runs
runs = get_all_validation_runs()
print(f'Total runs: {len(runs)}')
for run in runs[:5]:
    print(f'  {run[\"service_name\"]} / {run[\"environment\"]} - {run[\"run_id\"][:30]}')
"
```

---

### Issue 3: "404 Not Found"
**Symptom**: Console shows 404 error for `/api/services/X/run-history`

**Fix**: Server not restarted after code changes. Restart server:
```bash
# Find and kill existing process
ps aux | grep "python3 main.py"
kill -9 <PID>

# Start again
python3 main.py
```

---

### Issue 4: Dropdown doesn't show "All Environments"
**Symptom**: Dropdown only shows PROD, BETA2, etc., no "All" option

**Check**: `branch_env.html` line 2193-2194:
```javascript
const envOptions = ['all', ...availableEnvironments];
```

---

### Issue 5: Environment badges don't show
**Symptom**: No badges even when "All Environments" is selected

**Check**: Line 2387 in `branch_env.html`:
```javascript
selectedEnv === 'all' && e('span', {...}, run.environment)
```

---

## 📊 Backend Endpoint Testing

### Test 1: Get all runs
```bash
curl http://localhost:8000/api/services/cxp-ptg-adapter/run-history
```

**Expected response**:
```json
{
  "service_id": "cxp-ptg-adapter",
  "all_environments": true,
  "runs": [...]
}
```

### Test 2: Get filtered runs
```bash
curl "http://localhost:8000/api/services/cxp-ptg-adapter/run-history?environment=beta2"
```

**Expected response**:
```json
{
  "service_id": "cxp-ptg-adapter",
  "environment": "beta2",
  "runs": [...]
}
```

---

## 🔍 Key Files to Check

1. **`/Users/jayeshzambre/Documents/GitHub/gcpv1/main.py`**
   - Line 1491: Endpoint definition
   - Line 1492: Function signature with optional `environment`
   - Line 1525: Filtering logic

2. **`/Users/jayeshzambre/Documents/GitHub/gcpv1/api/templates/branch_env.html`**
   - Line 2176: HistoryTab function
   - Line 2180: selectedEnv default = 'all'
   - Line 2193: envOptions with 'all'
   - Line 2196: filteredRunHistory useMemo
   - Line 2216: API URL without environment
   - Line 2241: useEffect dependency (no selectedEnv)
   - Line 2387: Environment badge

---

## ✅ What Should Work Now

1. ✅ Analysis History tab shows **ALL runs from ALL environments** by default
2. ✅ Dropdown has "All Environments" option (selected by default)
3. ✅ Each run shows environment badge when viewing all
4. ✅ Can filter to specific environment (instant, client-side)
5. ✅ Badges disappear when filtered to specific environment
6. ✅ Count updates correctly
7. ✅ Only ONE API call on page load (no refetch on filter change)

---

## 📝 What to Share if Still Not Working

1. **Browser console output** (screenshot or copy-paste)
2. **Server terminal output** (what does it log?)
3. **Network tab** (does the request succeed? what's the response?)
4. **Specific behavior** (what do you see vs what you expect?)

---

## 🎯 Quick Verification

Run this to see if endpoint signature is correct:
```bash
grep -A 2 "@app.get.*run-history" /Users/jayeshzambre/Documents/GitHub/gcpv1/main.py
```

Should show:
```python
@app.get("/api/services/{service_id}/run-history")
async def get_run_history(service_id: str, environment: str = None):
```

Run this to see if frontend URL is correct:
```bash
grep "const url.*run-history" /Users/jayeshzambre/Documents/GitHub/gcpv1/api/templates/branch_env.html
```

Should show:
```javascript
const url = `/api/services/${serviceId}/run-history`;  // ✅ No environment parameter
```

---

## 💡 Final Notes

- Make sure to **hard refresh** the browser (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows)
- Check that server was **restarted** after code changes
- Check browser console for **JavaScript errors**
- Check server logs for **API errors**

