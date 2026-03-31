#!/usr/bin/env python3.11
"""
Create service result files for demo data so the UI can display drift counts
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = "config_data/golden_config.db"
RESULTS_DIR = Path("config_data/service_results")

def create_service_result_files():
    """Create service result JSON files from database"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all validation runs with their metrics
    cursor.execute('''
        SELECT 
            vr.run_id,
            vr.service_name,
            vr.environment,
            vr.verdict,
            vr.created_at,
            vr.golden_branch,
            vr.drift_branch,
            COUNT(cd.id) as total_deltas,
            SUM(CASE WHEN cd.risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk,
            SUM(CASE WHEN cd.risk_level = 'MEDIUM' THEN 1 ELSE 0 END) as medium_risk,
            SUM(CASE WHEN cd.risk_level = 'LOW' THEN 1 ELSE 0 END) as low_risk,
            SUM(CASE WHEN cd.risk_level = 'ALLOWED' THEN 1 ELSE 0 END) as allowed,
            COUNT(DISTINCT cd.file_path) as files_with_drift
        FROM validation_runs vr
        LEFT JOIN config_deltas cd ON vr.run_id = cd.run_id
        GROUP BY vr.run_id
    ''')
    
    runs = cursor.fetchall()
    
    print("Creating service result files...\n")
    
    for run in runs:
        (run_id, service_name, environment, verdict, created_at, golden_branch, 
         drift_branch, total_deltas, high_risk, medium_risk, low_risk, allowed, files_with_drift) = run
        
        # Create service directory
        service_dir = RESULTS_DIR / service_name
        service_dir.mkdir(parents=True, exist_ok=True)
        
        # Create result file
        timestamp = datetime.fromisoformat(created_at).strftime("%Y%m%d_%H%M%S")
        result_file = service_dir / f"validation_{timestamp}_{run_id}.json"
        
        # Build result structure that matches what the UI expects
        result_data = {
            "timestamp": created_at,
            "service_id": service_name,
            "run_id": run_id,
            "validation_result": {
                "run_id": run_id,
                "status": "completed",
                "verdict": verdict,
                "environment": environment,
                "golden_branch": golden_branch,
                "drift_branch": drift_branch,
                "llm_output": {
                    "summary": {
                        "total_config_files": files_with_drift or 2,
                        "files_with_drift": files_with_drift or 2,
                        "total_drifts": total_deltas,
                        "high_risk": high_risk,
                        "medium_risk": medium_risk,
                        "low_risk": low_risk,
                        "allowed_variance": allowed
                    },
                    "verdict": verdict,
                    "confidence_score": 95 - (high_risk * 15) - (medium_risk * 5)
                }
            }
        }
        
        # Write file
        with open(result_file, 'w') as f:
            json.dump(result_data, f, indent=2)
        
        service_short = service_name.replace('jayeshics_', '')
        print(f"✅ {service_short} ({environment}): {total_deltas} issues ({high_risk}H, {medium_risk}M, {low_risk}L)")
    
    conn.close()
    print(f"\n✅ Created {len(runs)} service result files")

if __name__ == "__main__":
    create_service_result_files()
