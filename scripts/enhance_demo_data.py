#!/usr/bin/env python3.11
"""
Enhance demo data to show properly in all tabs:
- Overview: Multiple environments with certification status
- Certification: Issue counts and certification details
- Drift Analysis: Detailed drift with explanations
"""

import sqlite3
import json
from datetime import datetime, timedelta
import uuid
import random

DB_PATH = "config_data/golden_config.db"

def add_drift_explanations():
    """Add detailed explanations to config deltas"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Define detailed explanations for each drift scenario
    explanations = {
        "security.encryption.algorithm": {
            "explanation": "Downgrading from AES-256-GCM to AES-128-CBC reduces encryption strength and removes authenticated encryption",
            "impact": "Violates PCI-DSS requirements for payment data protection",
            "recommendation": "Maintain AES-256-GCM encryption standard for production systems",
            "risk_justification": "HIGH: Security degradation exposes sensitive payment data to potential breaches"
        },
        "payment.processor.timeout_ms": {
            "explanation": "Reducing payment processor timeout from 30 seconds to 5 seconds",
            "impact": "May cause transaction failures during peak load or network latency",
            "recommendation": "Keep timeout at 30 seconds or conduct thorough load testing before reducing",
            "risk_justification": "HIGH: Critical timeout change could result in failed transactions and revenue loss"
        },
        "database.pool.max_connections": {
            "explanation": "5x increase in database connection pool size from 100 to 500",
            "impact": "May exhaust database server resources without proper capacity planning",
            "recommendation": "Verify database server can handle 500 connections and monitor resource usage",
            "risk_justification": "MEDIUM: Resource scaling requires infrastructure validation"
        },
        "logging.level.root": {
            "explanation": "Changing log level from INFO to DEBUG in production",
            "impact": "DEBUG logging may expose sensitive payment data and degrade performance",
            "recommendation": "Use INFO or WARNING level in production; DEBUG only for troubleshooting",
            "risk_justification": "MEDIUM: May expose PII and impact system performance"
        },
        "security.audit.enabled": {
            "explanation": "Disabling security audit logging",
            "impact": "Violates SOX and PCI-DSS compliance requirements for audit trails",
            "recommendation": "Keep audit logging enabled at all times in production",
            "risk_justification": "HIGH: Compliance violation with regulatory requirements"
        },
        "auth.session.timeout_minutes": {
            "explanation": "Increasing session timeout from 30 minutes to 2 hours",
            "impact": "Extends exposure window for session hijacking attacks",
            "recommendation": "Keep session timeout under 60 minutes for sensitive applications",
            "risk_justification": "MEDIUM: Security relaxation increases attack surface"
        },
        "auth.password.min_length": {
            "explanation": "Reducing minimum password length from 12 to 8 characters",
            "impact": "Weakens authentication security and password strength",
            "recommendation": "Maintain minimum 12-character password requirement",
            "risk_justification": "MEDIUM: Security degradation below industry standards"
        },
        "cache.redis.ttl_seconds": {
            "explanation": "Doubled cache TTL from 1 hour to 2 hours",
            "impact": "May serve stale user data but improves cache hit ratio",
            "recommendation": "Monitor data freshness requirements and adjust if needed",
            "risk_justification": "LOW: Performance optimization with acceptable staleness"
        },
        "rate_limiting.max_requests_per_minute": {
            "explanation": "Increased rate limit from 1000 to 2000 requests per minute",
            "impact": "Accommodates higher user traffic but may stress backend services",
            "recommendation": "Ensure backend services can handle increased load",
            "risk_justification": "LOW: Capacity increase with proper monitoring"
        },
        "notification.retry.max_attempts": {
            "explanation": "Increased retry attempts from 3 to 5",
            "impact": "Improves delivery reliability for transient failures",
            "recommendation": "Monitor retry queue depth and processing time",
            "risk_justification": "LOW: Reliability improvement with minimal risk"
        },
        "notification.batch_size": {
            "explanation": "Increased batch size from 100 to 250 notifications",
            "impact": "Improves throughput for bulk notification delivery",
            "recommendation": "Monitor memory usage and processing latency",
            "risk_justification": "LOW: Performance optimization"
        },
        "email.sender_name": {
            "explanation": "Updated sender name from 'Notifications' to 'Platform Notifications'",
            "impact": "Branding update with no functional impact",
            "recommendation": "No action required",
            "risk_justification": "ALLOWED: Cosmetic change only"
        },
        "pipeline.data_retention_days": {
            "explanation": "Reducing data retention from 90 to 30 days",
            "impact": "Violates regulatory requirements for financial data retention",
            "recommendation": "Maintain 90-day retention period per compliance requirements",
            "risk_justification": "HIGH: Compliance violation - GDPR and financial regulations"
        },
        "pipeline.pii_masking.enabled": {
            "explanation": "Disabling PII masking in analytics pipeline",
            "impact": "Exposes sensitive personal information in analytics logs and reports",
            "recommendation": "Keep PII masking enabled to protect user privacy",
            "risk_justification": "HIGH: Privacy violation - GDPR non-compliance"
        },
        "warehouse.query_timeout_seconds": {
            "explanation": "12x increase in query timeout from 5 minutes to 1 hour",
            "impact": "Allows runaway queries to consume resources for extended periods",
            "recommendation": "Keep timeout under 10 minutes and optimize slow queries",
            "risk_justification": "MEDIUM: Performance risk from long-running queries"
        },
        "pipeline.validation.skip_on_errors": {
            "explanation": "Skipping data validation when errors occur",
            "impact": "May propagate corrupted or invalid data to downstream systems",
            "recommendation": "Maintain strict validation; investigate and fix errors",
            "risk_justification": "MEDIUM: Data quality risk"
        },
        "inventory.stock_check_interval_seconds": {
            "explanation": "More frequent stock checks - reduced from 60 to 30 seconds",
            "impact": "Improves inventory accuracy with slightly increased database load",
            "recommendation": "Monitor database performance impact",
            "risk_justification": "LOW: Performance optimization for better accuracy"
        },
        "inventory.low_stock_threshold": {
            "explanation": "Increased low stock threshold from 10 to 25 units",
            "impact": "Triggers earlier reorder notifications",
            "recommendation": "Align with business inventory management policies",
            "risk_justification": "LOW: Business logic adjustment"
        },
        "cache.strategy": {
            "explanation": "Changed caching strategy from write-through to write-behind",
            "impact": "Improves write performance but introduces eventual consistency",
            "recommendation": "Ensure application can handle eventual consistency",
            "risk_justification": "MEDIUM: Consistency trade-off for performance"
        }
    }
    
    # Update config_deltas with explanations
    cursor.execute('SELECT id, locator_value, risk_level FROM config_deltas')
    deltas = cursor.fetchall()
    
    print("Adding detailed explanations to drift deltas...\n")
    
    for delta_id, locator, risk_level in deltas:
        if locator in explanations:
            exp = explanations[locator]
            metadata = json.dumps({
                "explanation": exp["explanation"],
                "impact": exp["impact"],
                "recommendation": exp["recommendation"],
                "risk_justification": exp["risk_justification"]
            })
            
            # Add metadata column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE config_deltas ADD COLUMN metadata JSON')
            except:
                pass
            
            cursor.execute('''
                UPDATE config_deltas
                SET metadata = ?
                WHERE id = ?
            ''', (metadata, delta_id))
    
    conn.commit()
    print(f"✅ Added explanations to {len(deltas)} drift deltas")
    
    conn.close()

def add_multiple_environments():
    """Add validation runs for multiple environments per service"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\nAdding multiple environment validations...\n")
    
    # Define which services should have multiple environments
    multi_env_services = {
        'jayeshics_payments-api': {
            'existing': 'prod',
            'add': ['staging'],  # Add staging environment
            'staging_status': 'APPROVE',  # Staging is clean
            'staging_issues': 0
        },
        'jayeshics_analytics-pipeline': {
            'existing': 'prod',
            'add': ['staging'],
            'staging_status': 'APPROVE',
            'staging_issues': 0
        }
    }
    
    for service_id, config in multi_env_services.items():
        for new_env in config['add']:
            run_id = f"run_{uuid.uuid4().hex[:12]}"
            created_at = datetime.now() - timedelta(hours=random.randint(24, 48))
            execution_time = random.randint(15000, 30000)
            completed_at = created_at + timedelta(milliseconds=execution_time)
            
            golden_branch = f"golden_{new_env}_{created_at.strftime('%Y%m%d_%H%M%S')}"
            drift_branch = f"feature/config-update-{random.randint(100, 999)}"
            
            # Insert validation run for staging (clean - no issues)
            cursor.execute('''
                INSERT INTO validation_runs (
                    run_id, service_name, environment, status, created_at,
                    completed_at, execution_time_ms, verdict, summary,
                    repo_url, golden_branch, drift_branch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                service_id,
                new_env,
                'completed',
                created_at.isoformat(),
                completed_at.isoformat(),
                execution_time,
                config['staging_status'],
                f"No configuration drift detected in {new_env} environment",
                f"https://github.com/jayeshics/{service_id.replace('jayeshics_', '')}.git",
                golden_branch,
                drift_branch
            ))
            
            # Add certification for staging
            cursor.execute('''
                INSERT INTO certifications (
                    run_id, created_at, confidence_score, decision, environment,
                    violations_count, high_risk_count, certified_snapshot_branch,
                    certification_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                completed_at.isoformat(),
                98,  # High confidence for clean environment
                config['staging_status'],
                new_env,
                0,
                0,
                golden_branch,
                json.dumps({
                    "certification_timestamp": completed_at.isoformat(),
                    "certified_by": "AI Multi-Agent System",
                    "certification_notes": f"Clean {new_env} environment - no drift detected"
                })
            ))
            
            service_short = service_id.replace('jayeshics_', '')
            print(f"✅ {service_short}: Added {new_env} environment (CLEAN - {config['staging_status']})")
    
    conn.commit()
    conn.close()

def update_certifications():
    """Update certifications table with proper data"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\nUpdating certification data...\n")
    
    # Get all validation runs and update their certifications
    cursor.execute('''
        SELECT 
            vr.run_id,
            vr.service_name,
            vr.environment,
            vr.verdict,
            COUNT(cd.id) as total_deltas,
            SUM(CASE WHEN cd.risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk,
            pv.policy_violations_count
        FROM validation_runs vr
        LEFT JOIN config_deltas cd ON vr.run_id = cd.run_id
        LEFT JOIN policy_validations pv ON vr.run_id = pv.run_id
        GROUP BY vr.run_id
    ''')
    
    runs = cursor.fetchall()
    
    for run in runs:
        run_id, service_name, environment, verdict, total_deltas, high_risk, violations = run
        
        # Calculate confidence score
        confidence = 95 - (high_risk * 15) - (total_deltas * 2)
        confidence = max(20, min(98, confidence))
        
        # Check if certification exists
        cursor.execute('SELECT id FROM certifications WHERE run_id = ?', (run_id,))
        if not cursor.fetchone():
            # Create certification
            cursor.execute('''
                INSERT INTO certifications (
                    run_id, created_at, confidence_score, decision, environment,
                    violations_count, high_risk_count, certification_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                datetime.now().isoformat(),
                confidence,
                verdict,
                environment,
                violations or 0,
                high_risk,
                json.dumps({
                    "total_issues": total_deltas,
                    "high_risk_count": high_risk,
                    "certification_notes": f"Automated analysis completed for {environment}"
                })
            ))
        else:
            # Update existing certification
            cursor.execute('''
                UPDATE certifications
                SET confidence_score = ?,
                    violations_count = ?,
                    high_risk_count = ?,
                    certification_data = ?
                WHERE run_id = ?
            ''', (
                confidence,
                violations or 0,
                high_risk,
                json.dumps({
                    "total_issues": total_deltas,
                    "high_risk_count": high_risk,
                    "certification_notes": f"Automated analysis completed for {environment}"
                }),
                run_id
            ))
        
        service_short = service_name.replace('jayeshics_', '')
        print(f"✅ {service_short} ({environment}): Confidence {confidence}%, {total_deltas} issues")
    
    conn.commit()
    conn.close()

def main():
    print("🎨 Enhancing demo data for all tabs...\n")
    print("="*80)
    
    add_drift_explanations()
    add_multiple_environments()
    update_certifications()
    
    print("\n" + "="*80)
    print("✅ Demo data enhanced successfully!")
    print("\nNow all tabs will show:")
    print("  • Overview: Multiple environments with certification status")
    print("  • Certification: Issue counts and confidence scores")
    print("  • Drift Analysis: Detailed drift with explanations and recommendations")

if __name__ == "__main__":
    main()
