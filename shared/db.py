"""
Database module for Golden Config AI System
Uses SQLite for persistent storage of all validation data.
"""

import sqlite3
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database file location
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "config_data" / "golden_config.db"

# Database connection settings for multi-user access
DB_TIMEOUT = 30.0  # Timeout in seconds (increased from default 5.0)
MAX_RETRIES = 5  # Maximum number of retries for locked database
RETRY_DELAY_BASE = 0.1  # Base delay for exponential backoff (seconds)


@contextmanager
def get_db_connection(retries: int = MAX_RETRIES):
    """
    Get database connection with context manager.
    
    Features:
    - Increased timeout (30 seconds) for busy database
    - WAL (Write-Ahead Logging) mode enabled for better concurrency
    - Automatic retry with exponential backoff on database locked errors
    - busy_timeout PRAGMA for additional lock handling
    
    Args:
        retries: Number of retry attempts for locked database (default: MAX_RETRIES)
    """
    last_error = None
    
    for attempt in range(retries + 1):
        conn = None
        try:
            # Connect with increased timeout for multi-user scenarios
            conn = sqlite3.connect(
                str(DB_PATH),
                timeout=DB_TIMEOUT,
                check_same_thread=False  # Allow connections from different threads
            )
            conn.row_factory = sqlite3.Row  # Enable column access by name
            
            # Enable WAL mode for better concurrency (allows multiple readers + 1 writer)
            # This is critical for multi-user access on the same database file
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Set busy timeout at SQLite level (in milliseconds)
            # This provides additional protection beyond the connection timeout
            conn.execute(f"PRAGMA busy_timeout={int(DB_TIMEOUT * 1000)}")
            
            # Yield the connection to the caller
            try:
                yield conn
                conn.commit()
                return  # Success - exit function
                
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if ("database is locked" in error_msg or "database is busy" in error_msg) and attempt < retries:
                    # Database locked - retry with backoff
                    conn.rollback()
                    last_error = e
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"Database locked (attempt {attempt + 1}/{retries + 1}), "
                        f"retrying in {delay:.2f}s... Error: {e}"
                    )
                    time.sleep(delay)
                    # Continue to next iteration
                else:
                    # Not a locking issue or out of retries
                    conn.rollback()
                    raise
                    
            except Exception as e:
                # Non-locking error - rollback and re-raise immediately
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise
                
        except sqlite3.OperationalError as e:
            # Error during connection establishment
            error_msg = str(e).lower()
            if ("database is locked" in error_msg or "database is busy" in error_msg) and attempt < retries:
                last_error = e
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    f"Database locked during connection (attempt {attempt + 1}/{retries + 1}), "
                    f"retrying in {delay:.2f}s... Error: {e}"
                )
                time.sleep(delay)
                # Continue to next iteration
            else:
                # Not a locking issue or out of retries
                logger.error(f"Database connection error: {e}")
                raise
                
        except Exception as e:
            # Unexpected error during connection
            logger.error(f"Unexpected database error: {e}")
            raise
            
        finally:
            # Always close the connection when exiting the context
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
    
    # If we get here, all retries failed
    if last_error:
        logger.error(f"Database locked after {retries + 1} attempts. Last error: {last_error}")
        raise last_error
    else:
        raise sqlite3.OperationalError("Database connection failed after all retries")


def init_db():
    """
    Initialize database with all required tables.
    
    Enables WAL mode for better multi-user concurrency support.
    This function automatically enables WAL mode if not already enabled.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Ensure WAL mode is enabled (critical for multi-user access)
        cursor.execute("PRAGMA journal_mode=WAL")
        wal_mode = cursor.fetchone()[0]
        if wal_mode.upper() != 'WAL':
            logger.warning(f"⚠️  WAL mode not enabled, current mode: {wal_mode}")
            logger.warning("Attempting to enable WAL mode...")
            # Try again with explicit mode change
            cursor.execute("PRAGMA journal_mode=WAL")
            wal_mode = cursor.fetchone()[0]
            if wal_mode.upper() == 'WAL':
                logger.info("✅ Successfully enabled WAL mode for better concurrency")
            else:
                logger.error(f"❌ Failed to enable WAL mode. Current mode: {wal_mode}")
        else:
            logger.info("✅ WAL mode enabled - database ready for multi-user access")
        
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
        
        # Table 10: Services Configuration (NEW)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT UNIQUE NOT NULL,
                service_name TEXT NOT NULL,
                repo_url TEXT NOT NULL,
                main_branch TEXT NOT NULL DEFAULT 'main',
                environments JSON NOT NULL,
                config_paths JSON,
                vsat TEXT DEFAULT 'saja9l7',
                vsat_url TEXT DEFAULT 'https://gitlab.verizon.com/saja9l7',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                metadata JSON
            )
        """)
        
        # Table 11: System Logs (NEW)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                log_level TEXT NOT NULL,
                logger_name TEXT NOT NULL,
                message TEXT NOT NULL,
                module TEXT,
                function_name TEXT,
                line_number INTEGER,
                log_type TEXT DEFAULT 'system',
                run_id TEXT,
                service_name TEXT,
                environment TEXT,
                vsat TEXT,
                metadata JSON,
                FOREIGN KEY (run_id) REFERENCES validation_runs(run_id)
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_service_env ON validation_runs(service_name, environment)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON validation_runs(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deltas_run ON config_deltas(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deltas_risk ON config_deltas(risk_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_branches_active ON golden_branches(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_active ON services(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_id ON services(service_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(log_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_type ON logs(log_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service_name, environment)")
        
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


def update_context_bundle_deltas(run_id: str, redacted_deltas: List[Dict[str, Any]]) -> None:
    """
    Update context bundle with PII-redacted deltas.
    
    CRITICAL SECURITY: This function updates the context_bundle with redacted deltas
    so that downstream agents (Triaging LLM) only see sanitized data.
    
    Args:
        run_id: Validation run ID
        redacted_deltas: List of deltas with PII redacted
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get existing context bundle
        cursor.execute("""
            SELECT bundle_data FROM context_bundles 
            WHERE run_id = ? ORDER BY created_at DESC LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        
        if not row:
            logger.error(f"No context bundle found for run_id: {run_id}")
            return
        
        # Update deltas in bundle_data
        bundle_data = json.loads(row['bundle_data'])
        bundle_data['deltas'] = redacted_deltas
        bundle_data['pii_redacted'] = True  # Flag that PII has been redacted
        bundle_data['redacted_at'] = datetime.now().isoformat()
        
        # Update the database
        cursor.execute("""
            UPDATE context_bundles 
            SET bundle_data = ?
            WHERE run_id = ?
        """, (json.dumps(bundle_data), run_id))
        
        logger.info(f"✅ Updated context bundle with {len(redacted_deltas)} redacted deltas for run: {run_id}")


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


def service_has_golden_branches(service_id: str) -> bool:
    """
    Check if a service has at least one golden branch.
    Used to filter dashboard display - only show services with config files.
    
    Args:
        service_id: Service identifier
        
    Returns:
        True if service has at least one golden branch, False otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM golden_branches 
            WHERE service_name = ? AND branch_type = 'golden'
        """, (service_id,))
        count = cursor.fetchone()['count']
        return count > 0


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
            aggregated_data.get('policy_violations_count', 0),  # Use count, not list
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


# ============================================================================
# Services Configuration (NEW)
# ============================================================================

def _extract_vsat_from_url(repo_url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract VSAT and VSAT URL from repository URL.
    
    Examples:
        "https://gitlab.verizon.com/saja9l7/cxp-ptg-adapter.git"
        -> vsat="saja9l7", vsat_url="https://gitlab.verizon.com/saja9l7"
        
        "https://gitlab.verizon.com/another_team/repo.git"
        -> vsat="another_team", vsat_url="https://gitlab.verizon.com/another_team"
        
        "https://github.com/org/repo.git"
        -> vsat=None, vsat_url=None
    
    Args:
        repo_url: Git repository URL
        
    Returns:
        Tuple of (vsat, vsat_url) or (None, None) if cannot be extracted
    """
    import re
    
    # Pattern to match GitLab URLs: https://gitlab.verizon.com/VSAT/repo.git
    pattern = r'https?://([^/]+)/([^/]+)/[^/]+\.git'
    match = re.match(pattern, repo_url)
    
    if match:
        base_domain = match.group(1)  # e.g., gitlab.verizon.com
        vsat = match.group(2)          # e.g., saja9l7 or another_team
        vsat_url = f"https://{base_domain}/{vsat}"
        return vsat, vsat_url
    
    return None, None


def add_service(
    service_id: str,
    service_name: str,
    repo_url: str,
    main_branch: str,
    environments: List[str],
    config_paths: Optional[List[str]] = None,
    vsat: Optional[str] = None,
    vsat_url: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Add a new service to the database.
    
    Args:
        service_id: Unique service identifier (e.g., "cxp_ptg_adapter")
        service_name: Human-readable service name
        repo_url: Git repository URL
        main_branch: Main branch name (default: "main")
        environments: List of environments (e.g., ["prod", "alpha", "beta1"])
        config_paths: List of config file patterns
        vsat: VSAT group identifier (auto-extracted from repo_url if not provided)
        vsat_url: VSAT group URL (auto-extracted from repo_url if not provided)
        description: Service description
        metadata: Additional metadata
    """
    # Auto-extract VSAT from repo_url if not provided
    if vsat is None or vsat_url is None:
        extracted_vsat, extracted_vsat_url = _extract_vsat_from_url(repo_url)
        if vsat is None:
            vsat = extracted_vsat
        if vsat_url is None:
            vsat_url = extracted_vsat_url
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO services (
                service_id, service_name, repo_url, main_branch,
                environments, config_paths, vsat, vsat_url, description, metadata, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            service_id,
            service_name,
            repo_url,
            main_branch,
            json.dumps(environments),
            json.dumps(config_paths) if config_paths else None,
            vsat,
            vsat_url,
            description,
            json.dumps(metadata) if metadata else None
        ))
        logger.info(f"✅ Added/updated service: {service_id} (VSAT: {vsat})")


def get_all_services(active_only: bool = True, with_branches_only: bool = False) -> List[Dict[str, Any]]:
    """
    Get all services from database.
    
    Args:
        active_only: If True, only return active services
        with_branches_only: If True, only return services that have golden branches
        
    Returns:
        List of service dictionaries
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if with_branches_only:
            # Join with golden_branches to only get services with branches
            query = """
                SELECT DISTINCT s.* FROM services s
                INNER JOIN golden_branches gb ON s.service_id = gb.service_name
                WHERE gb.branch_type = 'golden'
            """
            if active_only:
                query += " AND s.is_active = 1"
            query += " ORDER BY s.service_id"
            cursor.execute(query)
        else:
            # Standard query
            if active_only:
                cursor.execute("""
                    SELECT * FROM services WHERE is_active = 1 ORDER BY service_id
                """)
            else:
                cursor.execute("SELECT * FROM services ORDER BY service_id")
        
        rows = cursor.fetchall()
        services = []
        for row in rows:
            service = dict(row)
            # Parse JSON fields
            service['environments'] = json.loads(service['environments'])
            if service['config_paths']:
                service['config_paths'] = json.loads(service['config_paths'])
            if service['metadata']:
                service['metadata'] = json.loads(service['metadata'])
            services.append(service)
        
        return services


def get_service_by_id(service_id: str) -> Optional[Dict[str, Any]]:
    """
    Get service configuration by service_id.
    
    Args:
        service_id: Service identifier
        
    Returns:
        Service dict or None
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM services WHERE service_id = ?", (service_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        service = dict(row)
        # Parse JSON fields
        service['environments'] = json.loads(service['environments'])
        if service['config_paths']:
            service['config_paths'] = json.loads(service['config_paths'])
        if service['metadata']:
            service['metadata'] = json.loads(service['metadata'])
        
        return service


def update_service(service_id: str, updates: Dict[str, Any]) -> None:
    """
    Update specific fields of a service.
    
    Args:
        service_id: Service identifier
        updates: Dict of fields to update
    """
    # Handle JSON fields
    if 'environments' in updates and isinstance(updates['environments'], list):
        updates['environments'] = json.dumps(updates['environments'])
    if 'config_paths' in updates and isinstance(updates['config_paths'], list):
        updates['config_paths'] = json.dumps(updates['config_paths'])
    if 'metadata' in updates and isinstance(updates['metadata'], dict):
        updates['metadata'] = json.dumps(updates['metadata'])
    
    updates['updated_at'] = datetime.now().isoformat()
    
    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    values.append(service_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE services 
            SET {', '.join(set_clauses)}
            WHERE service_id = ?
        """, values)
        logger.info(f"✅ Updated service: {service_id}")


def deactivate_service(service_id: str) -> None:
    """Mark service as inactive (soft delete)."""
    update_service(service_id, {'is_active': 0})
    logger.info(f"⚠️ Deactivated service: {service_id}")


def activate_service(service_id: str) -> None:
    """Mark service as active."""
    update_service(service_id, {'is_active': 1})
    logger.info(f"✅ Activated service: {service_id}")


def delete_service(service_id: str) -> None:
    """Permanently delete service from database (use with caution)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services WHERE service_id = ?", (service_id,))
        logger.warning(f"🗑️ Permanently deleted service: {service_id}")


# ============================================================================
# Logs Management
# ============================================================================

def save_log(
    log_level: str,
    logger_name: str,
    message: str,
    module: Optional[str] = None,
    function_name: Optional[str] = None,
    line_number: Optional[int] = None,
    log_type: str = 'system',
    run_id: Optional[str] = None,
    service_name: Optional[str] = None,
    environment: Optional[str] = None,
    vsat: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Save a log entry to the database.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: Name of the logger
        message: Log message
        module: Module name where log originated
        function_name: Function name where log originated
        line_number: Line number where log originated
        log_type: Type of log (system, vsat_sync, analysis, git, etc.)
        run_id: Associated validation run ID (if applicable)
        service_name: Associated service name (if applicable)
        environment: Associated environment (if applicable)
        vsat: Associated VSAT (if applicable)
        metadata: Additional metadata as JSON
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (
                    log_level, logger_name, message, module, function_name, 
                    line_number, log_type, run_id, service_name, environment, 
                    vsat, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_level,
                logger_name,
                message,
                module,
                function_name,
                line_number,
                log_type,
                run_id,
                service_name,
                environment,
                vsat,
                json.dumps(metadata) if metadata else None
            ))
    except Exception as e:
        # Don't let logging failures break the application
        print(f"⚠️ Failed to save log to database: {e}")


def get_logs(
    log_level: Optional[str] = None,
    log_type: Optional[str] = None,
    run_id: Optional[str] = None,
    service_name: Optional[str] = None,
    environment: Optional[str] = None,
    vsat: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Query logs from database with optional filters.
    
    Args:
        log_level: Filter by log level
        log_type: Filter by log type
        run_id: Filter by run ID
        service_name: Filter by service name
        environment: Filter by environment
        vsat: Filter by VSAT
        start_time: Filter logs after this timestamp
        end_time: Filter logs before this timestamp
        limit: Maximum number of logs to return
        
    Returns:
        List of log entries
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        
        if log_level:
            query += " AND log_level = ?"
            params.append(log_level)
        
        if log_type:
            query += " AND log_type = ?"
            params.append(log_type)
        
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        
        if service_name:
            query += " AND service_name = ?"
            params.append(service_name)
        
        if environment:
            query += " AND environment = ?"
            params.append(environment)
        
        if vsat:
            query += " AND vsat = ?"
            params.append(vsat)
        
        if start_time:
            query += " AND created_at >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND created_at <= ?"
            params.append(end_time)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        logs = []
        for row in rows:
            log_entry = dict(row)
            if log_entry.get('metadata'):
                log_entry['metadata'] = json.loads(log_entry['metadata'])
            logs.append(log_entry)
        
        return logs


def delete_old_logs(days: int = 30) -> int:
    """
    Delete logs older than specified days.
    
    Args:
        days: Delete logs older than this many days
        
    Returns:
        Number of logs deleted
    """
    from datetime import timedelta
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs WHERE created_at < ?", (cutoff_date,))
        deleted_count = cursor.rowcount
        logger.info(f"🗑️ Deleted {deleted_count} logs older than {days} days")
        return deleted_count


def get_log_stats() -> Dict[str, Any]:
    """
    Get statistics about logs in the database.
    
    Returns:
        Dictionary with log statistics
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Total logs
        cursor.execute("SELECT COUNT(*) as total FROM logs")
        total = cursor.fetchone()['total']
        
        # Logs by level
        cursor.execute("""
            SELECT log_level, COUNT(*) as count 
            FROM logs 
            GROUP BY log_level
        """)
        by_level = {row['log_level']: row['count'] for row in cursor.fetchall()}
        
        # Logs by type
        cursor.execute("""
            SELECT log_type, COUNT(*) as count 
            FROM logs 
            GROUP BY log_type
        """)
        by_type = {row['log_type']: row['count'] for row in cursor.fetchall()}
        
        # Recent logs (last 24 hours)
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cursor.execute("SELECT COUNT(*) as count FROM logs WHERE created_at >= ?", (yesterday,))
        recent_count = cursor.fetchone()['count']
        
        return {
            'total_logs': total,
            'by_level': by_level,
            'by_type': by_type,
            'last_24_hours': recent_count
        }

