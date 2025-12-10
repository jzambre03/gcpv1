"""
Database module for Golden Config AI System
Uses SQLite for persistent storage of all validation data.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database file location
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "config_data" / "golden_config.db"


@contextmanager
def get_db_connection():
    """Get database connection with context manager."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database with all required tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Table 1: Validation Runs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_runs (
                run_id TEXT PRIMARY KEY,
                service_name TEXT NOT NULL,
                environment TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                execution_time_ms INTEGER,
                verdict TEXT,
                summary TEXT,
                repo_url TEXT,
                golden_branch TEXT,
                drift_branch TEXT,
                project_id TEXT,
                mr_iid TEXT
            )
        """)
        
        # Table 2: Context Bundles (from Drift Detector)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_bundles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                bundle_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                golden_branch TEXT,
                drift_branch TEXT,
                total_files INTEGER,
                files_with_drift INTEGER,
                total_deltas INTEGER,
                bundle_data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Table 3: Configuration Deltas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_deltas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                delta_id TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                locator_type TEXT,
                locator_value TEXT,
                old_value TEXT,
                new_value TEXT,
                drift_category TEXT,
                risk_level TEXT,
                line_number_range TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id),
                FOREIGN KEY (bundle_id) REFERENCES context_bundles(bundle_id)
            )
        """)
        
        # Table 4: LLM Output (from Triaging-Routing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                golden_ref TEXT,
                candidate_ref TEXT,
                total_files INTEGER,
                drifted_files INTEGER,
                total_deltas INTEGER,
                high_risk_count INTEGER,
                medium_risk_count INTEGER,
                low_risk_count INTEGER,
                allowed_count INTEGER,
                llm_data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Table 5: Policy Validated Deltas (from Guardrails & Policy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pii_findings_count INTEGER,
                intent_violations_count INTEGER,
                policy_violations_count INTEGER,
                policy_warnings_count INTEGER,
                validation_data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Table 6: Certification Results (from Certification Engine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS certifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence_score INTEGER,
                decision TEXT,
                environment TEXT,
                violations_count INTEGER,
                high_risk_count INTEGER,
                certified_snapshot_branch TEXT,
                certification_data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Table 7: Golden Branches
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS golden_branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                environment TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                branch_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                certification_score INTEGER,
                metadata JSON,
                UNIQUE(service_name, environment, branch_name, branch_type)
            )
        """)
        
        # Table 8: Aggregated Results (from Supervisor)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aggregated_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                service_name TEXT,
                environment TEXT,
                overall_status TEXT,
                files_analyzed INTEGER,
                total_deltas INTEGER,
                policy_violations INTEGER,
                confidence_score INTEGER,
                final_decision TEXT,
                aggregated_data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Table 9: Reports (Markdown reports from Supervisor)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                report_type TEXT DEFAULT 'validation',
                report_content TEXT NOT NULL,
                report_path TEXT,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_service_env ON validation_runs(service_name, environment)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON validation_runs(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deltas_run ON config_deltas(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deltas_risk ON config_deltas(risk_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_branches_active ON golden_branches(is_active)")
        
        conn.commit()
        logger.info(f"✅ Database initialized at {DB_PATH}")


# ============================================================================
# Validation Runs
# ============================================================================

def save_validation_run(run_data: Dict[str, Any]) -> None:
    """Save or update a validation run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO validation_runs (
                run_id, service_name, environment, status, created_at, 
                completed_at, execution_time_ms, verdict, summary, 
                repo_url, golden_branch, drift_branch, project_id, mr_iid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_data.get('run_id'),
            run_data.get('service_name'),
            run_data.get('environment'),
            run_data.get('status', 'running'),
            run_data.get('created_at', datetime.now().isoformat()),
            run_data.get('completed_at'),
            run_data.get('execution_time_ms'),
            run_data.get('verdict'),
            run_data.get('summary'),
            run_data.get('repo_url'),
            run_data.get('golden_branch'),
            run_data.get('drift_branch'),
            run_data.get('project_id'),
            run_data.get('mr_iid')
        ))
        logger.info(f"Saved validation run: {run_data.get('run_id')}")


def update_validation_run(run_id: str, updates: Dict[str, Any]) -> None:
    """Update specific fields of a validation run."""
    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    values.append(run_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE validation_runs 
            SET {', '.join(set_clauses)}
            WHERE run_id = ?
        """, values)
        logger.info(f"Updated validation run: {run_id}")


def get_run_by_id(run_id: str) -> Optional[Dict[str, Any]]:
    """Get validation run by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM validation_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_runs_by_service(service_name: str, environment: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get validation runs for a service/environment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if environment:
            cursor.execute("""
                SELECT * FROM validation_runs 
                WHERE service_name = ? AND environment = ?
                ORDER BY created_at DESC LIMIT ?
            """, (service_name, environment, limit))
        else:
            cursor.execute("""
                SELECT * FROM validation_runs 
                WHERE service_name = ?
                ORDER BY created_at DESC LIMIT ?
            """, (service_name, limit))
        
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# Context Bundles
# ============================================================================

def save_context_bundle(run_id: str, bundle_data: Dict[str, Any]) -> str:
    """Save context bundle and return bundle_id."""
    bundle_id = f"bundle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO context_bundles (
                run_id, bundle_id, golden_branch, drift_branch,
                total_files, files_with_drift, total_deltas, bundle_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            bundle_id,
            bundle_data.get('meta', {}).get('golden_branch'),
            bundle_data.get('meta', {}).get('drift_branch'),
            bundle_data.get('overview', {}).get('total_files', 0),
            bundle_data.get('overview', {}).get('files_with_drift', 0),
            bundle_data.get('overview', {}).get('total_deltas', 0),
            json.dumps(bundle_data)
        ))
        
        # Save individual deltas in the same connection
        for delta in bundle_data.get('deltas', []):
            # Handle locator - can be string or dict
            locator = delta.get('locator')
            if isinstance(locator, dict):
                locator_type = locator.get('type')
                locator_value = locator.get('value')
            elif isinstance(locator, str):
                locator_type = 'path'
                locator_value = locator
            else:
                locator_type = None
                locator_value = None
            
            cursor.execute("""
                INSERT OR REPLACE INTO config_deltas (
                    run_id, bundle_id, delta_id, file_path, locator_type, locator_value,
                    old_value, new_value, drift_category, risk_level, line_number_range
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                bundle_id,
                delta.get('id'),
                delta.get('file'),
                locator_type,
                locator_value,
                json.dumps(delta.get('old')),
                json.dumps(delta.get('new')),
                delta.get('drift_category'),
                delta.get('risk_level'),
                json.dumps(delta.get('line_number_range'))
            ))
        
        logger.info(f"Saved context bundle: {bundle_id}")
        return bundle_id


def get_context_bundle(bundle_id: str) -> Optional[Dict[str, Any]]:
    """Get context bundle by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bundle_data FROM context_bundles WHERE bundle_id = ?", (bundle_id,))
        row = cursor.fetchone()
        return json.loads(row['bundle_data']) if row else None


def get_latest_context_bundle(run_id: str) -> Optional[Dict[str, Any]]:
    """Get latest context bundle for a run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT bundle_data FROM context_bundles 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        return json.loads(row['bundle_data']) if row else None


# ============================================================================
# Config Deltas
# ============================================================================

def save_config_delta(run_id: str, bundle_id: str, delta: Dict[str, Any]) -> None:
    """Save a configuration delta."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Handle locator - can be string or dict
        locator = delta.get('locator')
        if isinstance(locator, dict):
            locator_type = locator.get('type')
            locator_value = locator.get('value')
        elif isinstance(locator, str):
            locator_type = 'path'
            locator_value = locator
        else:
            locator_type = None
            locator_value = None
        
        cursor.execute("""
            INSERT OR REPLACE INTO config_deltas (
                run_id, bundle_id, delta_id, file_path, locator_type, locator_value,
                old_value, new_value, drift_category, risk_level, line_number_range
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            bundle_id,
            delta.get('id'),
            delta.get('file'),
            locator_type,
            locator_value,
            json.dumps(delta.get('old')),
            json.dumps(delta.get('new')),
            delta.get('drift_category'),
            delta.get('risk_level'),
            json.dumps(delta.get('line_number_range'))
        ))


def get_deltas_by_risk(run_id: str, risk_level: str) -> List[Dict[str, Any]]:
    """Get deltas filtered by risk level."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM config_deltas 
            WHERE run_id = ? AND risk_level = ?
            ORDER BY id
        """, (run_id, risk_level))
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# LLM Output
# ============================================================================

def save_llm_output(run_id: str, llm_data: Dict[str, Any]) -> None:
    """Save LLM output."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO llm_outputs (
                run_id, golden_ref, candidate_ref, total_files, drifted_files,
                total_deltas, high_risk_count, medium_risk_count, low_risk_count,
                allowed_count, llm_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            llm_data.get('meta', {}).get('golden'),
            llm_data.get('meta', {}).get('candidate'),
            llm_data.get('overview', {}).get('total_files', 0),
            llm_data.get('overview', {}).get('drifted_files', 0),
            llm_data.get('overview', {}).get('total_deltas', 0),
            len(llm_data.get('high', [])),
            len(llm_data.get('medium', [])),
            len(llm_data.get('low', [])),
            len(llm_data.get('allowed_variance', [])),
            json.dumps(llm_data)
        ))
        logger.info(f"Saved LLM output for run: {run_id}")


def get_latest_llm_output(run_id: str = None, environment: str = None) -> Optional[Dict[str, Any]]:
    """Get latest LLM output."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if run_id:
            cursor.execute("""
                SELECT llm_data FROM llm_outputs 
                WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
            """, (run_id,))
        else:
            cursor.execute("""
                SELECT lo.llm_data FROM llm_outputs lo
                JOIN validation_runs vr ON lo.run_id = vr.run_id
                WHERE vr.environment = ?
                ORDER BY lo.created_at DESC LIMIT 1
            """, (environment,))
        
        row = cursor.fetchone()
        return json.loads(row['llm_data']) if row else None


# ============================================================================
# Policy Validations
# ============================================================================

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
            pii_report.get('instances_found', 0),        # Fixed: Use correct field name
            intent_report.get('total_findings', 0),      # Fixed: Use correct field name
            policy_summary.get('total_violations', 0),   # Fixed: Use correct field name
            warnings_count,                              # Fixed: Calculate from medium + low
            json.dumps(validation_data)
        ))
        logger.info(f"Saved policy validation for run: {run_id}")


def get_latest_policy_validation(run_id: str) -> Optional[Dict[str, Any]]:
    """Get latest policy validation for a run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT validation_data FROM policy_validations 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        return json.loads(row['validation_data']) if row else None


# ============================================================================
# Certifications
# ============================================================================

def save_certification(run_id: str, cert_data: Dict[str, Any]) -> None:
    """Save certification result."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO certifications (
                run_id, confidence_score, decision, environment,
                violations_count, high_risk_count, certified_snapshot_branch,
                certification_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            cert_data.get('confidence_score'),
            cert_data.get('decision'),
            cert_data.get('environment'),
            cert_data.get('violations_count', 0),
            cert_data.get('high_risk_count', 0),
            cert_data.get('certified_snapshot_branch'),
            json.dumps(cert_data)
        ))
        logger.info(f"Saved certification for run: {run_id}")


def get_latest_certification(run_id: str) -> Optional[Dict[str, Any]]:
    """Get latest certification for a run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT certification_data FROM certifications 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        return json.loads(row['certification_data']) if row else None


# ============================================================================
# Golden Branches
# ============================================================================

def save_golden_branch(service_name: str, environment: str, branch_name: str, 
                       branch_type: str, certification_score: int = None,
                       metadata: Dict[str, Any] = None) -> None:
    """Save golden/drift branch info."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO golden_branches (
                service_name, environment, branch_name, branch_type,
                certification_score, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            service_name,
            environment,
            branch_name,
            branch_type,
            certification_score,
            json.dumps(metadata) if metadata else None
        ))
        logger.info(f"Saved {branch_type} branch: {branch_name}")


def get_active_golden_branch(service_name: str, environment: str) -> Optional[str]:
    """Get active golden branch for service/environment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT branch_name FROM golden_branches 
            WHERE service_name = ? AND environment = ? 
            AND branch_type = 'golden' AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
        """, (service_name, environment))
        row = cursor.fetchone()
        return row['branch_name'] if row else None


def deactivate_branches(service_name: str, environment: str, branch_type: str) -> None:
    """Deactivate all branches of a type for service/environment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE golden_branches SET is_active = 0
            WHERE service_name = ? AND environment = ? AND branch_type = ?
        """, (service_name, environment, branch_type))
        logger.info(f"Deactivated {branch_type} branches for {service_name}/{environment}")


# ============================================================================
# Aggregated Results
# ============================================================================

def save_aggregated_results(run_id: str, aggregated_data: Dict[str, Any]) -> None:
    """Save aggregated results from supervisor."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO aggregated_results (
                run_id, service_name, environment, overall_status,
                files_analyzed, total_deltas, policy_violations,
                confidence_score, final_decision, aggregated_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            aggregated_data.get('service_name'),
            aggregated_data.get('environment'),
            aggregated_data.get('overall_status'),
            aggregated_data.get('files_analyzed', 0),
            aggregated_data.get('total_deltas', 0),
            aggregated_data.get('policy_violations', 0),
            aggregated_data.get('confidence_score'),
            aggregated_data.get('final_decision'),
            json.dumps(aggregated_data)
        ))
        logger.info(f"Saved aggregated results for run: {run_id}")


def get_latest_aggregated_results(service_name: str, environment: str) -> Optional[Dict[str, Any]]:
    """Get latest aggregated results for service/environment."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT aggregated_data FROM aggregated_results 
            WHERE service_name = ? AND environment = ?
            ORDER BY created_at DESC LIMIT 1
        """, (service_name, environment))
        row = cursor.fetchone()
        return json.loads(row['aggregated_data']) if row else None


# ============================================================================
# Reports
# ============================================================================

def save_report(run_id: str, report_content: str, report_path: str = None, 
                report_type: str = 'validation') -> None:
    """Save validation report."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reports (run_id, report_type, report_content, report_path)
            VALUES (?, ?, ?, ?)
        """, (run_id, report_type, report_content, report_path))
        logger.info(f"Saved report for run: {run_id}")


def get_latest_report(run_id: str) -> Optional[str]:
    """Get latest report for a run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT report_content FROM reports 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        return row['report_content'] if row else None


# ============================================================================
# Utility Functions
# ============================================================================

def get_db_stats() -> Dict[str, int]:
    """Get database statistics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        stats = {}
        
        tables = [
            'validation_runs', 'context_bundles', 'config_deltas',
            'llm_outputs', 'policy_validations', 'certifications',
            'golden_branches', 'aggregated_results', 'reports'
        ]
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            stats[table] = cursor.fetchone()['count']
        
        return stats


def vacuum_db():
    """Vacuum database to reclaim space."""
    with get_db_connection() as conn:
        conn.execute("VACUUM")
        logger.info("Database vacuumed")


def export_to_json(output_dir: Path = None):
    """Export all database data to JSON files (backup)."""
    if not output_dir:
        output_dir = PROJECT_ROOT / "config_data" / "db_backup"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        tables = cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table'
        """).fetchall()
        
        for table in tables:
            table_name = table['name']
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = [dict(row) for row in cursor.fetchall()]
            
            output_file = output_dir / f"{table_name}.json"
            with open(output_file, 'w') as f:
                json.dump(rows, f, indent=2)
            
            logger.info(f"Exported {table_name} to {output_file}")


# ============================================================================
# Wrapper/Alias Functions for Backward Compatibility
# ============================================================================

def get_all_validation_runs(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all validation runs (wrapper for backward compatibility)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM validation_runs 
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_llm_output(run_id: str) -> Optional[Dict[str, Any]]:
    """Get LLM output by run_id (wrapper for get_latest_llm_output)."""
    return get_latest_llm_output(run_id=run_id)


def get_policy_validation(run_id: str) -> Optional[Dict[str, Any]]:
    """Get policy validation by run_id (wrapper for get_latest_policy_validation)."""
    return get_latest_policy_validation(run_id)


def get_certification(run_id: str) -> Optional[Dict[str, Any]]:
    """Get certification by run_id (wrapper for get_latest_certification)."""
    return get_latest_certification(run_id)


def get_report(run_id: str) -> Optional[str]:
    """Get report by run_id (wrapper for get_latest_report)."""
    return get_latest_report(run_id)


def get_aggregated_results(run_id: str) -> Optional[Dict[str, Any]]:
    """Get aggregated results by run_id (wrapper for get_latest_aggregated_results)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT aggregated_data FROM aggregated_results 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        return json.loads(row['aggregated_data']) if row else None

