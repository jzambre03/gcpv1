# Database Schema Documentation

## Overview

The Golden Config AI system uses SQLite for persistent storage of all validation data. The database is located at `config_data/golden_config.db`.

## Database Tables

### 1. validation_runs

Stores metadata for each validation run.

**Columns:**
- `run_id` (TEXT, PRIMARY KEY) - Unique run identifier
- `service` (TEXT, NOT NULL) - Service name
- `environment` (TEXT, NOT NULL) - Environment (prod, dev, qa, etc.)
- `status` (TEXT, NOT NULL) - Run status (running, success, failed)
- `start_time` (TEXT, NOT NULL) - ISO 8601 timestamp
- `end_time` (TEXT) - ISO 8601 timestamp
- `duration_seconds` (REAL) - Duration in seconds
- `repo_url` (TEXT) - Git repository URL
- `golden_branch` (TEXT) - Golden branch name
- `drift_branch` (TEXT) - Drift branch name
- `summary` (TEXT) - JSON summary data
- `verdict` (TEXT) - Final verdict
- `overall_risk_level` (TEXT) - HIGH/MEDIUM/LOW/ALLOWED
- `confidence_score` (REAL) - Certification confidence (0-100)
- `certification_decision` (TEXT) - AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE
- `raw_request` (TEXT) - JSON of original request

**Example Query:**
```sql
SELECT run_id, service, environment, status, certification_decision, confidence_score
FROM validation_runs
WHERE environment = 'prod'
ORDER BY start_time DESC
LIMIT 10;
```

---

### 2. context_bundles

Stores the full context bundle output from the Drift Detector Agent.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `bundle_file_path` (TEXT) - Original file path (legacy)
- `bundle_data` (TEXT) - JSON of full context bundle
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Example Query:**
```sql
SELECT run_id, json_extract(bundle_data, '$.summary.total_deltas') as total_deltas
FROM context_bundles
WHERE run_id = 'run_20241205_123456';
```

---

### 3. config_deltas

Stores individual configuration deltas extracted from context bundles.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `delta_id` (TEXT, NOT NULL) - Unique delta identifier
- `file_path` (TEXT, NOT NULL) - File path
- `delta_type` (TEXT, NOT NULL) - added/removed/modified/renamed
- `locator` (TEXT) - YAMLPath/JSONPath/KeyPath/LineRange
- `old_value` (TEXT) - Previous value (JSON)
- `new_value` (TEXT) - New value (JSON)
- `metadata` (TEXT) - JSON metadata
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Example Query:**
```sql
SELECT file_path, delta_type, locator
FROM config_deltas
WHERE run_id = 'run_20241205_123456'
  AND delta_type = 'modified'
ORDER BY file_path;
```

---

### 4. llm_outputs

Stores LLM analysis output from the Triaging-Routing Agent.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `llm_output_data` (TEXT, NOT NULL) - JSON of full LLM output
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Structure of `llm_output_data` JSON:**
```json
{
  "meta": {
    "golden": "golden_branch",
    "candidate": "drift_branch",
    "generated_at": "2024-12-05T12:34:56Z"
  },
  "overview": {
    "total_files": 5,
    "drifted_files": 2,
    "total_deltas": 37
  },
  "high": [...],
  "medium": [...],
  "low": [...],
  "allowed_variance": [...]
}
```

**Example Query:**
```sql
SELECT run_id, 
       json_extract(llm_output_data, '$.overview.total_deltas') as total_deltas,
       json_extract(llm_output_data, '$.summary.critical_count') as critical
FROM llm_outputs
WHERE run_id = 'run_20241205_123456';
```

---

### 5. policy_validations

Stores policy validation output from the Guardrails & Policy Agent.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `policy_data` (TEXT, NOT NULL) - JSON of full policy validation
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Structure of `policy_data` JSON:**
```json
{
  "deltas": [...],
  "pii_report": {
    "total_scanned": 37,
    "pii_found": 2,
    "detections": [...]
  },
  "intent_report": {
    "total_scanned": 37,
    "malicious_found": 0,
    "detections": []
  },
  "policy_summary": {
    "total_deltas": 37,
    "policy_violations": 3,
    "allowed_by_policy": 5
  }
}
```

---

### 6. certifications

Stores certification decisions from the Certification Engine Agent.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `confidence_score` (REAL, NOT NULL) - Score (0-100)
- `certification_decision` (TEXT, NOT NULL) - AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE
- `snapshot_branch` (TEXT) - Created snapshot branch name
- `certification_data` (TEXT, NOT NULL) - JSON of full certification result
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Example Query:**
```sql
SELECT run_id, confidence_score, certification_decision, snapshot_branch
FROM certifications
WHERE confidence_score >= 80
  AND certification_decision = 'AUTO_MERGE'
ORDER BY created_at DESC;
```

---

### 7. golden_branches

Stores metadata for golden and drift branches.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `service_name` (TEXT, NOT NULL)
- `environment` (TEXT, NOT NULL)
- `branch_name` (TEXT, NOT NULL)
- `branch_type` (TEXT, NOT NULL) - 'golden' or 'drift'
- `is_active` (INTEGER, NOT NULL, DEFAULT 1) - Boolean (0 or 1)
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp
- `certification_score` (REAL) - Score from certification
- `metadata` (TEXT) - JSON metadata

**Example Query:**
```sql
SELECT service_name, environment, branch_name, certification_score
FROM golden_branches
WHERE branch_type = 'golden'
  AND is_active = 1
ORDER BY created_at DESC;
```

---

### 8. aggregated_results

Stores aggregated results from the Supervisor Agent.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `aggregated_data` (TEXT, NOT NULL) - JSON of full aggregated result
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

---

### 9. reports

Stores final validation reports in Markdown format.

**Columns:**
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
- `run_id` (TEXT, NOT NULL, FOREIGN KEY → validation_runs.run_id)
- `report_content` (TEXT, NOT NULL) - Full Markdown report
- `created_at` (TEXT, NOT NULL) - ISO 8601 timestamp

**Example Query:**
```sql
SELECT run_id, substr(report_content, 1, 200) as preview
FROM reports
ORDER BY created_at DESC
LIMIT 5;
```

---

## Initialization

Run the initialization script to create all tables:

```bash
python init_db.py
```

This will:
1. Create the database file at `config_data/golden_config.db`
2. Create all 9 tables with proper foreign key relationships
3. Display statistics showing 0 records initially

---

## Database Operations

### Accessing the Database

Using Python:
```python
from shared.db import get_db_connection, get_run_by_id

# Get a specific run
run_data = get_run_by_id("run_20241205_123456")

# Use context manager for custom queries
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM validation_runs WHERE status = ?", ("success",))
    rows = cursor.fetchall()
```

Using SQLite CLI:
```bash
sqlite3 config_data/golden_config.db
sqlite> .schema validation_runs
sqlite> SELECT run_id, status FROM validation_runs LIMIT 5;
```

---

## Backup and Maintenance

### Creating Backups

```bash
# Simple copy
cp config_data/golden_config.db config_data/golden_config_backup_$(date +%Y%m%d).db

# Using SQLite backup command
sqlite3 config_data/golden_config.db ".backup config_data/backup.db"
```

### Database Size Management

```bash
# Check database size
ls -lh config_data/golden_config.db

# Vacuum to reclaim space after deletions
sqlite3 config_data/golden_config.db "VACUUM;"
```

### Cleaning Old Records

```python
from shared.db import get_db_connection
from datetime import datetime, timedelta

# Delete runs older than 90 days
cutoff_date = (datetime.now() - timedelta(days=90)).isoformat()

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM validation_runs 
        WHERE start_time < ?
    """, (cutoff_date,))
    print(f"Deleted {cursor.rowcount} old runs")
```

---

## Migration from JSON Files

If you have existing JSON files from before the database migration, you can manually import them using the database functions:

```python
import json
from shared.db import save_validation_run, save_context_bundle, save_llm_output

# Example: Import a context bundle
with open("config_data/context_bundles/context_bundle_old.json", "r") as f:
    bundle_data = json.load(f)
    save_context_bundle(
        run_id="run_legacy_001",
        bundle_file_path="config_data/context_bundles/context_bundle_old.json",
        bundle_data=bundle_data
    )
```

---

## Performance Considerations

1. **Indexes**: The database automatically creates indexes on foreign keys and primary keys.

2. **JSON Queries**: SQLite's `json_extract()` function allows querying JSON columns:
   ```sql
   SELECT run_id, json_extract(bundle_data, '$.summary.total_deltas')
   FROM context_bundles;
   ```

3. **Concurrency**: SQLite uses file-level locking. For high-concurrency scenarios, consider PostgreSQL migration.

4. **Transaction Safety**: All write operations use transactions to ensure data integrity.

---

## Future Enhancements

- [ ] Add indexes for frequently queried columns
- [ ] Implement automatic cleanup of old records
- [ ] Add database migration scripts for schema changes
- [ ] Consider PostgreSQL migration for production scale
- [ ] Add database encryption at rest
- [ ] Implement read replicas for analytics queries

