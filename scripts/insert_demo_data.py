#!/usr/bin/env python3.11
"""
Insert mock data for demo
Creates realistic services, validation runs, and drift analysis data
"""

import sqlite3
import json
from datetime import datetime, timedelta
import uuid
import random

DB_PATH = "config_data/golden_config.db"

def generate_run_id():
    """Generate unique run ID"""
    return f"run_{uuid.uuid4().hex[:12]}"

def insert_mock_services(cursor):
    """Insert mock services from different VSATs"""
    
    services = [
        {
            "service_id": "jayeshics_payments-api",
            "service_name": "payments-api",
            "repo_url": "https://github.com/jayeshics/payments-api.git",
            "vsat": "jayeshics",
            "vsat_url": "https://github.com/jayeshics",
            "description": "Payment processing microservice with PCI compliance requirements",
            "environments": ["dev", "staging", "prod"]
        },
        {
            "service_id": "jayeshics_user-service",
            "service_name": "user-service",
            "repo_url": "https://github.com/jayeshics/user-service.git",
            "vsat": "jayeshics",
            "vsat_url": "https://github.com/jayeshics",
            "description": "User authentication and profile management service",
            "environments": ["dev", "staging", "prod"]
        },
        {
            "service_id": "jayeshics_notification-engine",
            "service_name": "notification-engine",
            "repo_url": "https://github.com/jayeshics/notification-engine.git",
            "vsat": "jayeshics",
            "vsat_url": "https://github.com/jayeshics",
            "description": "Multi-channel notification delivery system",
            "environments": ["dev", "staging", "prod"]
        },
        {
            "service_id": "jayeshics_analytics-pipeline",
            "service_name": "analytics-pipeline",
            "repo_url": "https://github.com/jayeshics/analytics-pipeline.git",
            "vsat": "jayeshics",
            "vsat_url": "https://github.com/jayeshics",
            "description": "Real-time data analytics and reporting pipeline",
            "environments": ["dev", "staging", "prod"]
        },
        {
            "service_id": "jayeshics_inventory-service",
            "service_name": "inventory-service",
            "repo_url": "https://github.com/jayeshics/inventory-service.git",
            "vsat": "jayeshics",
            "vsat_url": "https://github.com/jayeshics",
            "description": "Inventory management and tracking system",
            "environments": ["dev", "staging", "prod"]
        }
    ]
    
    for svc in services:
        cursor.execute("""
            INSERT OR IGNORE INTO services (
                service_id, service_name, repo_url, main_branch,
                environments, config_paths, vsat, vsat_url,
                is_active, created_at, updated_at, description, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            svc["service_id"],
            svc["service_name"],
            svc["repo_url"],
            "main",
            json.dumps(svc["environments"]),
            json.dumps(["config/application.yaml", "config/database.yaml"]),
            svc["vsat"],
            svc["vsat_url"],
            1,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            svc["description"],
            json.dumps({"team": "Platform Engineering", "criticality": "high"})
        ))
    
    print(f"✅ Inserted {len(services)} mock services")
    return services

def insert_golden_branches(cursor, services):
    """Insert golden branches for mock services"""
    
    environments = ["dev", "staging", "prod"]
    branch_count = 0
    
    for svc in services:
        for env in environments:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"golden_{env}_{timestamp}_{random.randint(1000, 9999)}"
            
            cursor.execute("""
                INSERT INTO golden_branches (
                    service_name, environment, branch_name, branch_type,
                    is_active, created_at, certification_score, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                svc["service_id"],
                env,
                branch_name,
                "environment_specific",
                1,
                datetime.now().isoformat(),
                random.randint(85, 98),
                json.dumps({"auto_created": True, "config_files_count": 2})
            ))
            branch_count += 1
    
    print(f"✅ Inserted {branch_count} golden branches")

def create_realistic_drift_scenarios():
    """Define realistic drift scenarios for different services"""
    
    return [
        {
            "service": "payments-api",
            "environment": "prod",
            "status": "completed",
            "verdict": "REJECT",
            "severity": "high",
            "drift_count": 8,
            "scenarios": [
                {
                    "file": "config/application.yaml",
                    "locator": "security.encryption.algorithm",
                    "old_value": "AES-256-GCM",
                    "new_value": "AES-128-CBC",
                    "category": "security_degradation",
                    "risk": "HIGH",
                    "reason": "Downgrading from AES-256-GCM to AES-128-CBC reduces encryption strength and removes authenticated encryption, violating PCI-DSS requirements"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "payment.processor.timeout_ms",
                    "old_value": "30000",
                    "new_value": "5000",
                    "category": "critical_timeout_change",
                    "risk": "HIGH",
                    "reason": "Reducing payment processor timeout from 30s to 5s may cause transaction failures during peak load"
                },
                {
                    "file": "config/database.yaml",
                    "locator": "database.pool.max_connections",
                    "old_value": "100",
                    "new_value": "500",
                    "category": "resource_scaling",
                    "risk": "MEDIUM",
                    "reason": "5x increase in connection pool size may exhaust database resources without capacity planning"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "logging.level.root",
                    "old_value": "INFO",
                    "new_value": "DEBUG",
                    "category": "logging_change",
                    "risk": "MEDIUM",
                    "reason": "DEBUG logging in production may expose sensitive payment data and impact performance"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "security.audit.enabled",
                    "old_value": "true",
                    "new_value": "false",
                    "category": "compliance_violation",
                    "risk": "HIGH",
                    "reason": "Disabling audit logging violates SOX and PCI-DSS compliance requirements"
                }
            ],
            "policy_violations": [
                "PCI-DSS requirement 3.4 violated: Encryption downgrade detected",
                "Audit logging disabled in production environment",
                "DEBUG logging may expose sensitive cardholder data"
            ]
        },
        {
            "service": "user-service",
            "environment": "staging",
            "status": "completed",
            "verdict": "APPROVE_WITH_WARNINGS",
            "severity": "medium",
            "drift_count": 5,
            "scenarios": [
                {
                    "file": "config/application.yaml",
                    "locator": "auth.session.timeout_minutes",
                    "old_value": "30",
                    "new_value": "120",
                    "category": "security_relaxation",
                    "risk": "MEDIUM",
                    "reason": "Increasing session timeout from 30min to 2hrs extends exposure window for session hijacking"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "auth.password.min_length",
                    "old_value": "12",
                    "new_value": "8",
                    "category": "security_degradation",
                    "risk": "MEDIUM",
                    "reason": "Reducing minimum password length weakens authentication security"
                },
                {
                    "file": "config/database.yaml",
                    "locator": "cache.redis.ttl_seconds",
                    "old_value": "3600",
                    "new_value": "7200",
                    "category": "performance_optimization",
                    "risk": "LOW",
                    "reason": "Doubled cache TTL may serve stale user data but improves performance"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "rate_limiting.max_requests_per_minute",
                    "old_value": "1000",
                    "new_value": "2000",
                    "category": "capacity_change",
                    "risk": "LOW",
                    "reason": "Increased rate limit accommodates higher user traffic"
                }
            ],
            "policy_violations": [
                "Session timeout exceeds recommended 60 minutes for sensitive services",
                "Password policy weakened below organizational standards"
            ]
        },
        {
            "service": "notification-engine",
            "environment": "prod",
            "status": "completed",
            "verdict": "APPROVE",
            "severity": "low",
            "drift_count": 3,
            "scenarios": [
                {
                    "file": "config/application.yaml",
                    "locator": "notification.retry.max_attempts",
                    "old_value": "3",
                    "new_value": "5",
                    "category": "reliability_improvement",
                    "risk": "LOW",
                    "reason": "Increased retry attempts improve delivery reliability"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "notification.batch_size",
                    "old_value": "100",
                    "new_value": "250",
                    "category": "performance_optimization",
                    "risk": "LOW",
                    "reason": "Larger batch size improves throughput for bulk notifications"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "email.sender_name",
                    "old_value": "Notifications",
                    "new_value": "Platform Notifications",
                    "category": "cosmetic_change",
                    "risk": "ALLOWED",
                    "reason": "Branding update with no functional impact"
                }
            ],
            "policy_violations": []
        },
        {
            "service": "analytics-pipeline",
            "environment": "prod",
            "status": "completed",
            "verdict": "REJECT",
            "severity": "high",
            "drift_count": 6,
            "scenarios": [
                {
                    "file": "config/application.yaml",
                    "locator": "pipeline.data_retention_days",
                    "old_value": "90",
                    "new_value": "30",
                    "category": "compliance_violation",
                    "risk": "HIGH",
                    "reason": "Reducing retention from 90 to 30 days violates regulatory requirements for financial data"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "pipeline.pii_masking.enabled",
                    "old_value": "true",
                    "new_value": "false",
                    "category": "privacy_violation",
                    "risk": "HIGH",
                    "reason": "Disabling PII masking exposes sensitive personal data in analytics logs"
                },
                {
                    "file": "config/database.yaml",
                    "locator": "warehouse.query_timeout_seconds",
                    "old_value": "300",
                    "new_value": "3600",
                    "category": "performance_risk",
                    "risk": "MEDIUM",
                    "reason": "12x increase in query timeout may allow runaway queries to consume resources"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "pipeline.validation.skip_on_errors",
                    "old_value": "false",
                    "new_value": "true",
                    "category": "data_quality_risk",
                    "risk": "MEDIUM",
                    "reason": "Skipping validation on errors may propagate corrupted data downstream"
                }
            ],
            "policy_violations": [
                "GDPR Article 5(1)(e) violated: Data retention period reduced below legal requirements",
                "PII masking disabled - exposes sensitive personal information",
                "Data quality controls bypassed"
            ]
        },
        {
            "service": "inventory-service",
            "environment": "staging",
            "status": "completed",
            "verdict": "APPROVE",
            "severity": "low",
            "drift_count": 4,
            "scenarios": [
                {
                    "file": "config/application.yaml",
                    "locator": "inventory.stock_check_interval_seconds",
                    "old_value": "60",
                    "new_value": "30",
                    "category": "performance_optimization",
                    "risk": "LOW",
                    "reason": "More frequent stock checks improve inventory accuracy"
                },
                {
                    "file": "config/application.yaml",
                    "locator": "inventory.low_stock_threshold",
                    "old_value": "10",
                    "new_value": "25",
                    "category": "business_logic_change",
                    "risk": "LOW",
                    "reason": "Higher threshold triggers earlier reorder notifications"
                },
                {
                    "file": "config/database.yaml",
                    "locator": "cache.strategy",
                    "old_value": "write-through",
                    "new_value": "write-behind",
                    "category": "performance_optimization",
                    "risk": "MEDIUM",
                    "reason": "Write-behind caching improves performance but adds eventual consistency risk"
                }
            ],
            "policy_violations": []
        }
    ]

def insert_drift_analysis(cursor, services, scenarios):
    """Insert realistic drift analysis data"""
    
    run_count = 0
    
    for scenario in scenarios:
        # Find matching service
        service_data = next((s for s in services if s["service_name"] == scenario["service"]), None)
        if not service_data:
            continue
        
        run_id = generate_run_id()
        service_id = service_data["service_id"]
        environment = scenario["environment"]
        
        # Calculate timing
        created_at = datetime.now() - timedelta(hours=random.randint(1, 72))
        execution_time = random.randint(15000, 45000)
        completed_at = created_at + timedelta(milliseconds=execution_time)
        
        # Generate branch names
        golden_branch = f"golden_{environment}_{created_at.strftime('%Y%m%d_%H%M%S')}"
        drift_branch = f"feature/config-update-{random.randint(100, 999)}"
        
        # Insert validation run
        cursor.execute("""
            INSERT INTO validation_runs (
                run_id, service_name, environment, status, created_at,
                completed_at, execution_time_ms, verdict, summary,
                repo_url, golden_branch, drift_branch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            service_id,
            environment,
            scenario["status"],
            created_at.isoformat(),
            completed_at.isoformat(),
            execution_time,
            scenario["verdict"],
            f"Analyzed {len(scenario['scenarios'])} configuration changes with {len(scenario['policy_violations'])} policy violations",
            service_data["repo_url"],
            golden_branch,
            drift_branch
        ))
        
        # Insert context bundle
        bundle_id = f"bundle_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO context_bundles (
                run_id, bundle_id, created_at, golden_branch, drift_branch,
                total_files, files_with_drift, total_deltas, bundle_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            bundle_id,
            created_at.isoformat(),
            golden_branch,
            drift_branch,
            len(set(d["file"] for d in scenario["scenarios"])),
            len(set(d["file"] for d in scenario["scenarios"])),
            len(scenario["scenarios"]),
            json.dumps({
                "files": list(set(d["file"] for d in scenario["scenarios"])),
                "analysis_type": "full_config_drift"
            })
        ))
        
        # Insert config deltas
        for idx, delta in enumerate(scenario["scenarios"]):
            delta_id = f"delta_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
                INSERT INTO config_deltas (
                    run_id, bundle_id, delta_id, file_path, locator_type,
                    locator_value, old_value, new_value, drift_category,
                    risk_level, line_number_range, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                bundle_id,
                delta_id,
                delta["file"],
                "yaml_path",
                delta["locator"],
                delta["old_value"],
                delta["new_value"],
                delta["category"],
                delta["risk"],
                f"{random.randint(10, 50)}-{random.randint(51, 100)}",
                created_at.isoformat()
            ))
        
        # Count risk levels
        risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "ALLOWED": 0}
        for delta in scenario["scenarios"]:
            risk_counts[delta["risk"]] += 1
        
        # Insert LLM output
        cursor.execute("""
            INSERT INTO llm_outputs (
                run_id, created_at, golden_ref, candidate_ref, total_files,
                drifted_files, total_deltas, high_risk_count, medium_risk_count,
                low_risk_count, allowed_count, llm_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            created_at.isoformat(),
            golden_branch,
            drift_branch,
            len(set(d["file"] for d in scenario["scenarios"])),
            len(set(d["file"] for d in scenario["scenarios"])),
            len(scenario["scenarios"]),
            risk_counts["HIGH"],
            risk_counts["MEDIUM"],
            risk_counts["LOW"],
            risk_counts["ALLOWED"],
            json.dumps({
                "analysis_summary": f"Detected {len(scenario['scenarios'])} configuration changes",
                "risk_assessment": f"{risk_counts['HIGH']} high-risk, {risk_counts['MEDIUM']} medium-risk changes",
                "recommendations": [
                    "Review all high-risk changes before deployment",
                    "Ensure compliance requirements are met",
                    "Test configuration changes in staging first"
                ]
            })
        ))
        
        # Insert policy validations
        cursor.execute("""
            INSERT INTO policy_validations (
                run_id, created_at, pii_findings_count, intent_violations_count,
                policy_violations_count, policy_warnings_count, validation_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            created_at.isoformat(),
            len([v for v in scenario["policy_violations"] if "PII" in v or "personal" in v]),
            0,
            len(scenario["policy_violations"]),
            len([d for d in scenario["scenarios"] if d["risk"] == "MEDIUM"]),
            json.dumps({
                "violations": scenario["policy_violations"],
                "compliance_frameworks": ["PCI-DSS", "GDPR", "SOX", "HIPAA"]
            })
        ))
        
        # Calculate certification score
        confidence_score = 95 - (risk_counts["HIGH"] * 15) - (risk_counts["MEDIUM"] * 5)
        confidence_score = max(20, min(98, confidence_score))
        
        decision = scenario["verdict"]
        
        # Insert certification
        cursor.execute("""
            INSERT INTO certifications (
                run_id, created_at, confidence_score, decision, environment,
                violations_count, high_risk_count, certified_snapshot_branch,
                certification_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            completed_at.isoformat(),
            confidence_score,
            decision,
            environment,
            len(scenario["policy_violations"]),
            risk_counts["HIGH"],
            golden_branch if decision == "APPROVE" else None,
            json.dumps({
                "certification_timestamp": completed_at.isoformat(),
                "certified_by": "AI Multi-Agent System",
                "certification_notes": f"Automated analysis of {len(scenario['scenarios'])} configuration changes"
            })
        ))
        
        # Insert aggregated results
        cursor.execute("""
            INSERT INTO aggregated_results (
                run_id, created_at, service_name, environment, overall_status,
                files_analyzed, total_deltas, policy_violations, confidence_score,
                final_decision, aggregated_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            completed_at.isoformat(),
            service_id,
            environment,
            scenario["status"],
            len(set(d["file"] for d in scenario["scenarios"])),
            len(scenario["scenarios"]),
            len(scenario["policy_violations"]),
            confidence_score,
            decision,
            json.dumps({
                "summary": f"Drift analysis complete for {service_data['service_name']} in {environment}",
                "severity": scenario["severity"],
                "drift_categories": list(set(d["category"] for d in scenario["scenarios"]))
            })
        ))
        
        run_count += 1
        print(f"  ✅ Created drift analysis for {service_data['service_name']} ({environment}) - {scenario['verdict']}")
    
    print(f"✅ Inserted {run_count} complete drift analysis runs")

def main():
    """Main function to insert all demo data"""
    
    print("🎬 Inserting demo data for presentation...\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Insert mock services
        print("📦 Creating mock services...")
        services = insert_mock_services(cursor)
        
        # Insert golden branches
        print("\n🌿 Creating golden branches...")
        insert_golden_branches(cursor, services)
        
        # Get drift scenarios
        print("\n📊 Creating drift analysis data...")
        scenarios = create_realistic_drift_scenarios()
        
        # Insert drift analysis
        insert_drift_analysis(cursor, services, scenarios)
        
        conn.commit()
        
        print("\n" + "="*80)
        print("✅ Demo data inserted successfully!")
        print("="*80)
        
        # Print summary
        cursor.execute("SELECT COUNT(*) FROM services")
        service_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM validation_runs")
        run_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM config_deltas")
        delta_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM golden_branches")
        branch_count = cursor.fetchone()[0]
        
        print(f"\n📊 Summary:")
        print(f"   • Services: {service_count}")
        print(f"   • Validation Runs: {run_count}")
        print(f"   • Config Deltas: {delta_count}")
        print(f"   • Golden Branches: {branch_count}")
        print(f"\n🚀 Your demo is ready! Start the server with: python3.11 main.py")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error inserting demo data: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
