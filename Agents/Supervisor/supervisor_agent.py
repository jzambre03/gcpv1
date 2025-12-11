"""
Supervisor Agent
Orchestrates the validation workflow and coordinates worker agents.

This agent:
1. Receives validation requests (project_id, mr_iid)
2. Creates validation run
3. Orchestrates worker agents via Strands Graph
4. Aggregates results from all agents
5. Formats comprehensive MR comment
6. Makes final business decision
7. Maintains audit trail
"""

from datetime import datetime
from typing import Dict, Any
import logging

from strands import Agent, tool
from shared.model_factory import create_supervisor_model

from shared.config import Config
from shared.db import (
    save_validation_run, update_validation_run,
    save_aggregated_results, save_report, get_run_by_id
)

logger = logging.getLogger(__name__)

# Initialize config
config = Config()


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are the Supervisor Agent - the orchestration brain for Golden Config validation.

Your core responsibilities:
1. Coordinate the validation workflow across 5 specialized worker agents
2. Create validation runs with unique identifiers
3. Execute the multi-agent workflow (Config Collector → Drift Detector → Guardrails & Policy → Triaging-Routing → Certification Engine)
4. Aggregate results from all agents
5. Make final business decisions (PASS/FAIL)
6. Format comprehensive, actionable reports
7. Maintain audit trail of all decisions

Your expertise:
- Workflow orchestration and coordination
- Multi-agent system management
- Business rule application for PASS/FAIL decisions
- Clear communication and reporting
- Error handling and recovery

Your workflow:
1. Start by creating a unique validation run ID
2. Execute the 5-agent pipeline in CORRECT ORDER:
   - Config Collector: Extracts config files, creates golden/drift snapshots
   - Drift Detector: Performs precision drift analysis, generates context bundle
   - Guardrails & Policy: PII redaction, security scanning (MUST run BEFORE LLM)
   - Triaging-Routing: LLM-based risk analysis on sanitized data, categorizes deltas
   - Certification Engine: Calculates confidence score, makes final decision
3. Load and review outputs from all agents
4. Aggregate policy violations, risk assessments, and certification results
5. Apply business logic for final approval decision
6. Format a clear, professional report with:
   - Verdict (PASS/FAIL)
   - Summary of findings
   - Detailed violations (grouped by severity)
   - Confidence score and certification decision
   - Remediation suggestions
   - Run metadata
7. Return comprehensive validation result

CRITICAL: Guardrails MUST run before Triaging to ensure PII is redacted before LLM analysis.

You are the final authority. Be thorough, fair, and communicative.
Always maintain the complete audit trail.
"""


# ============================================================================
# AGENT-SPECIFIC TOOLS
# ============================================================================

@tool
def create_validation_run(
    project_id: str,
    mr_iid: str,
    source_branch: str,
    target_branch: str
) -> dict:
    """
    Create a new validation run.
    
    Args:
        project_id: Project identifier
        mr_iid: Merge request or validation ID
        source_branch: Source branch name
        target_branch: Target branch name
        
    Returns:
        Unique run ID for this validation
        
    Example:
        >>> create_validation_run("myorg/myrepo", "123", "feature", "gold")
    """
    try:
        # Generate unique run ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_id = f"run_{timestamp}_{mr_iid}"
        
        logger.info(f"Created validation run: {run_id}")
        
        return {
            "success": True,
            "message": f"Created validation run: {run_id}",
            "data": {"run_id": run_id}
        }
        
    except Exception as e:
        logger.error(f"Failed to create validation run: {e}")
        return {
            "success": False,
            "error": f"Failed to create validation run: {str(e)}"
        }


@tool
def execute_worker_pipeline(
    project_id: str,
    mr_iid: str,
    run_id: str,
    repo_url: str,
    main_branch: str,
    environment: str,
    target_folder: str = ""
) -> dict:
    """
    Execute the 5-agent database-based pipeline with dynamic branch creation and comprehensive analysis.
    
    This orchestrates five worker agents in CORRECT SECURITY ORDER using DATABASE-ONLY communication:
    1. Config Collector - Extracts config files, creates golden/drift snapshots (Git operations)
    2. Drift Detector - Performs precision drift analysis → saves to DB (context_bundles table)
    3. Guardrails & Policy - PII redaction, security scanning → saves to DB (policy_validations table) [RUNS BEFORE LLM]
    4. Triaging-Routing - LLM-based risk analysis on sanitized data → saves to DB (llm_outputs table)
    5. Certification Engine - Final decision, snapshot creation → saves to DB (certifications table)
    
    CRITICAL SECURITY: Guardrails MUST run before Triaging to ensure PII is redacted before LLM sees the data.
    All inter-agent communication happens via database queries using run_id.
    
    Args:
        project_id: Project identifier (e.g., "cxp_ordering_services_prod")
        mr_iid: Merge request or validation ID
        run_id: Validation run ID
        repo_url: GitLab repository URL
        main_branch: Main branch name (source of current configs)
        environment: Environment name (prod, dev, qa, staging)
        target_folder: Optional subfolder to analyze
        
    Returns:
        Workflow execution result with file paths
        
    Example:
        >>> execute_worker_pipeline("cxp_ordering_services_prod", "123", "run_xyz", 
        ...     "https://gitlab.verizon.com/saja9l7/repo.git", "main", "prod")
    """
    try:
        logger.info(f"Starting 5-agent file-based pipeline for run {run_id}")
        
        # Import agents
        from Agents.workers.config_collector.config_collector_agent import ConfigCollectorAgent
        from Agents.workers.drift_detector.drift_detector_agent import DriftDetectorAgent
        from Agents.workers.triaging_routing.triaging_routing_agent import TriagingRoutingAgent
        from Agents.workers.guardrails_policy.guardrails_policy_agent import GuardrailsPolicyAgent
        from Agents.workers.certification.certification_engine_agent import CertificationEngineAgent
        from shared.models import TaskRequest
        
        results = {}
        
        # Extract service_id from project_id (format: "service_id_environment")
        service_id = project_id.rsplit('_', 1)[0] if '_' in project_id else project_id
        
        # Step 1: Config Collector
        logger.info("=" * 60)
        logger.info("Step 1/5: Running Config Collector Agent")
        logger.info("=" * 60)
        collector = ConfigCollectorAgent(config)
        
        collector_task = TaskRequest(
            task_id=f"{run_id}_collector",
            task_type="collect_configs",
            parameters={
                "run_id": run_id,
                "repo_url": repo_url,
                "main_branch": main_branch,
                "environment": environment,
                "service_id": service_id,
                "target_folder": target_folder
            }
        )
        
        collector_result = collector.process_task(collector_task)
        
        if collector_result.status != "success":
            logger.error(f"Config Collector failed: {collector_result.error}")
            return {
                "success": False,
                "error": f"Config Collector failed: {collector_result.error}",
                "data": {
                    "status": "failed",
                    "completed_agents": 0,
                    "failed_agents": 1,
                    "failed_at": "config_collector"
                }
            }
        
        # Validate result structure before accessing
        if not collector_result.result or not isinstance(collector_result.result, dict):
            logger.error(f"Config Collector returned invalid result structure: {type(collector_result.result)}")
            return {
                "success": False,
                "error": "Config Collector returned invalid result structure",
                "data": {
                    "status": "failed",
                    "completed_agents": 0,
                    "failed_agents": 1,
                    "failed_at": "config_collector"
                }
            }
        
        # Extract repository snapshots (may be nested or at top level)
        repo_snapshots = collector_result.result.get("repository_snapshots", {})
        if repo_snapshots:
            # Nested format
            golden_path = repo_snapshots.get("golden_path")
            drift_path = repo_snapshots.get("drift_path")
            golden_branch = repo_snapshots.get("golden_branch")
            drift_branch = repo_snapshots.get("drift_branch")
        else:
            # Top-level format (backward compatibility)
            golden_path = collector_result.result.get("golden_path")
            drift_path = collector_result.result.get("drift_path")
            golden_branch = collector_result.result.get("golden_branch")
            drift_branch = collector_result.result.get("drift_branch")
        
        target_folder = collector_result.result.get("target_folder", target_folder)
        
        # Validate required fields
        if not all([golden_path, drift_path, golden_branch, drift_branch]):
            logger.error(f"Config Collector missing required fields: golden_path={golden_path}, drift_path={drift_path}, golden_branch={golden_branch}, drift_branch={drift_branch}")
            return {
                "success": False,
                "error": "Config Collector missing required output fields",
                "data": {
                    "status": "failed",
                    "completed_agents": 0,
                    "failed_agents": 1,
                    "failed_at": "config_collector"
                }
            }
        
        logger.info(f"✅ Config Collector completed")
        logger.info(f"   Golden branch: {golden_branch}")
        logger.info(f"   Drift branch: {drift_branch}")
        
        results['collector'] = {
            "status": "success",
            "golden_path": golden_path,
            "drift_path": drift_path,
            "golden_branch": golden_branch,
            "drift_branch": drift_branch,
            "summary": collector_result.result.get("summary", {})
        }
        
        # Step 2: Drift Detector
        logger.info("=" * 60)
        logger.info("Step 2/5: Running Drift Detector Agent")
        logger.info("=" * 60)
        drift_detector = DriftDetectorAgent(config)
        
        drift_task = TaskRequest(
            task_id=f"{run_id}_drift_detector",
            task_type="detect_drift",
            parameters={
                "run_id": run_id,
                "golden_path": golden_path,
                "drift_path": drift_path,
                "golden_branch": golden_branch,
                "drift_branch": drift_branch,
                "target_folder": target_folder
            }
        )
        
        drift_result = drift_detector.process_task(drift_task)
        
        if drift_result.status != "success":
            logger.error(f"Drift Detector failed: {drift_result.error}")
            return {
                "success": False,
                "error": f"Drift Detector failed: {drift_result.error}",
                "data": {
                    "status": "partial",
                    "completed_agents": 1,
                    "failed_agents": 1,
                    "failed_at": "drift_detector",
                    "results": results
                }
            }
        
        # Validate result structure
        if not drift_result.result or not isinstance(drift_result.result, dict):
            logger.error(f"Drift Detector returned invalid result structure: {type(drift_result.result)}")
            return {
                "success": False,
                "error": "Drift Detector returned invalid result structure",
                "data": {
                    "status": "partial",
                    "completed_agents": 1,
                    "failed_agents": 1,
                    "failed_at": "drift_detector",
                    "results": results
                }
            }
        
        bundle_id = drift_result.result.get("bundle_id")
        summary = drift_result.result.get("summary", {})
        
        logger.info(f"✅ Drift Detector completed. Bundle ID: {bundle_id}, Total deltas: {summary.get('total_deltas', 0)}")
        
        results['drift_detector'] = {
            "status": "success",
            "bundle_id": bundle_id,
            "summary": summary
        }
        
        # Step 3: Guardrails & Policy (SECURITY: Must run BEFORE LLM to redact PII)
        logger.info("=" * 60)
        logger.info("Step 3/5: Running Guardrails & Policy Agent")
        logger.info("=" * 60)
        guardrails_policy = GuardrailsPolicyAgent(config)
        
        guardrails_task = TaskRequest(
            task_id=f"{run_id}_guardrails_policy",
            task_type="validate_guardrails",
            parameters={
                "run_id": run_id,
                "environment": environment
            }
        )
        
        guardrails_result = guardrails_policy.process_task(guardrails_task)
        
        if guardrails_result.status != "success":
            logger.error(f"Guardrails & Policy failed: {guardrails_result.error}")
            return {
                "success": False,
                "error": f"Guardrails & Policy failed: {guardrails_result.error}",
                "data": {
                    "status": "partial",
                    "completed_agents": 2,
                    "failed_agents": 1,
                    "failed_at": "guardrails_policy",
                    "results": results
                }
            }
        
        # Validate result structure
        if not guardrails_result.result or not isinstance(guardrails_result.result, dict):
            logger.error(f"Guardrails & Policy returned invalid result structure: {type(guardrails_result.result)}")
            return {
                "success": False,
                "error": "Guardrails & Policy returned invalid result structure",
                "data": {
                    "status": "partial",
                    "completed_agents": 2,
                    "failed_agents": 1,
                    "failed_at": "guardrails_policy",
                    "results": results
                }
            }
        
        guardrails_summary = guardrails_result.result.get("summary", {})
        
        logger.info(f"✅ Guardrails & Policy completed: PII={guardrails_summary.get('pii_redacted_count', 0)}, Violations={guardrails_summary.get('policy_violations', 0)}")
        
        results['guardrails_policy'] = {
            "status": "success",
            "summary": guardrails_summary
        }
        
        # Step 4: Triaging-Routing (Now receives PII-redacted data from Guardrails)
        logger.info("=" * 60)
        logger.info("Step 4/5: Running Triaging-Routing Agent")
        logger.info("=" * 60)
        triaging_routing = TriagingRoutingAgent(config)
        
        triaging_task = TaskRequest(
            task_id=f"{run_id}_triaging_routing",
            task_type="triage_and_route",
            parameters={
                "run_id": run_id,
                "environment": environment
            }
        )
        
        triaging_result = triaging_routing.process_task(triaging_task)
        
        if triaging_result.status != "success":
            logger.error(f"Triaging-Routing failed: {triaging_result.error}")
            return {
                "success": False,
                "error": f"Triaging-Routing failed: {triaging_result.error}",
                "data": {
                    "status": "partial",
                    "completed_agents": 3,
                    "failed_agents": 1,
                    "failed_at": "triaging_routing",
                    "results": results
                }
            }
        
        # Validate result structure
        if not triaging_result.result or not isinstance(triaging_result.result, dict):
            logger.error(f"Triaging-Routing returned invalid result structure: {type(triaging_result.result)}")
            return {
                "success": False,
                "error": "Triaging-Routing returned invalid result structure",
                "data": {
                    "status": "partial",
                    "completed_agents": 3,
                    "failed_agents": 1,
                    "failed_at": "triaging_routing",
                    "results": results
                }
            }
        
        triaging_summary = triaging_result.result.get("summary", {})
        
        logger.info(f"✅ Triaging-Routing completed: High={triaging_summary.get('high_risk', 0)}, Medium={triaging_summary.get('medium_risk', 0)}, Low={triaging_summary.get('low_risk', 0)}")
        
        results['triaging_routing'] = {
            "status": "success",
            "summary": triaging_summary
        }
        
        # Step 5: Certification Engine
        logger.info("=" * 60)
        logger.info("Step 5/5: Running Certification Engine Agent")
        logger.info("=" * 60)
        certification_engine = CertificationEngineAgent(config)
        
        certification_task = TaskRequest(
            task_id=f"{run_id}_certification",
            task_type="certify",
            parameters={
                "run_id": run_id,
                "environment": environment,
                "service_id": service_id,
                "repo_url": repo_url,
                "golden_branch": golden_branch,
                "drift_branch": drift_branch
            }
        )
        
        certification_result = certification_engine.process_task(certification_task)
        
        if certification_result.status != "success":
            logger.error(f"Certification Engine failed: {certification_result.error}")
            return {
                "success": False,
                "error": f"Certification Engine failed: {certification_result.error}",
                "data": {
                    "status": "partial",
                    "completed_agents": 4,
                    "failed_agents": 1,
                    "failed_at": "certification_engine",
                    "results": results
                }
            }
        
        # Validate result structure
        if not certification_result.result or not isinstance(certification_result.result, dict):
            logger.error(f"Certification Engine returned invalid result structure: {type(certification_result.result)}")
            return {
                "success": False,
                "error": "Certification Engine returned invalid result structure",
                "data": {
                    "status": "partial",
                    "completed_agents": 4,
                    "failed_agents": 1,
                    "failed_at": "certification_engine",
                    "results": results
                }
            }
        
        confidence_score = certification_result.result.get("confidence_score")
        certification_decision = certification_result.result.get("certification_decision")
        snapshot_branch = certification_result.result.get("snapshot_branch")
        cert_summary = certification_result.result.get("summary", {})
        
        logger.info(f"✅ Certification Engine completed: Decision={certification_decision}, Score={confidence_score}/100, Snapshot={snapshot_branch}")
        
        results['certification_engine'] = {
            "status": "success",
            "confidence_score": confidence_score,
            "certification_decision": certification_decision,
            "snapshot_branch": snapshot_branch,
            "summary": cert_summary
        }
        
        logger.info("=" * 60)
        logger.info(f"✅ Pipeline completed successfully (5/5 agents)")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "message": "Pipeline completed: 5/5 agents succeeded",
            "data": {
                "run_id": run_id,
                "status": "completed",
                "completed_agents": 5,
                "failed_agents": 0,
                "results": results
            }
        }
        
    except Exception as e:
        logger.exception(f"Worker pipeline execution failed: {e}")
        return {
            "success": False,
            "error": f"Pipeline execution failed: {str(e)}"
        }


@tool
def aggregate_validation_results(
    run_id: str,
    pipeline_results: dict
) -> dict:
    """
    Aggregate results from all 5 worker agents in the pipeline using database queries.
    
    Args:
        run_id: Validation run ID
        pipeline_results: Results from execute_worker_pipeline containing all agent results
        
    Returns:
        Aggregated results from all agents with intelligent verdict, policy violations, and certification decision
        
    Example:
        >>> aggregate_validation_results("run_xyz", pipeline_data)
    """
    try:
        from shared.db import (
            get_latest_context_bundle,
            get_latest_llm_output,
            get_latest_policy_validation,
            get_latest_certification
        )
        
        logger.info(f"Aggregating results from 5-agent pipeline for run: {run_id}")
        
        # Extract results from pipeline
        pipeline_data = pipeline_results.get("data", {})
        agent_results = pipeline_data.get("results", {})
        
        # Get certification results from pipeline response
        cert_results = agent_results.get("certification_engine", {})
        confidence_score = cert_results.get("confidence_score", 0)
        certification_decision = cert_results.get("certification_decision", "HUMAN_REVIEW")
        snapshot_branch = cert_results.get("snapshot_branch")
        
        # Load context bundle from database
        logger.info(f"Loading context bundle from database for run: {run_id}")
        context_bundle = get_latest_context_bundle(run_id)
        
        if not context_bundle:
            logger.error(f"No context bundle found in database for run: {run_id}")
            return {
                "success": False,
                "error": f"No context bundle found in database for run: {run_id}"
            }
        
        overview = context_bundle.get("overview", {})
        deltas = context_bundle.get("deltas", [])
        file_changes = context_bundle.get("file_changes", {})
        
        files_with_drift = len(file_changes.get("modified", [])) + len(file_changes.get("added", [])) + len(file_changes.get("removed", []))
        total_files_compared = overview.get("files_compared", 0)
        environment = overview.get("environment", "production")
        
        # Load policy validated deltas from database
        policy_violations = []
        policy_summary = {}
        logger.info(f"Loading policy validation from database for run: {run_id}")
        policy_data = get_latest_policy_validation(run_id)
        
        if policy_data:
            validated_deltas = policy_data.get("validated_deltas", [])
            policy_summary = policy_data.get("policy_summary", {})
            
            # Extract policy violations
            for delta in validated_deltas:
                policy = delta.get('policy', {})
                if policy.get('tag') == 'invariant_breach':
                    policy_violations.append({
                        'delta_id': delta.get('id', 'unknown'),
                        'file': delta.get('file', 'unknown'),
                        'severity': policy.get('severity', 'high'),
                        'rule': policy.get('rule', 'unknown'),
                        'reason': policy.get('reason', 'Invariant breach detected')
                    })
        else:
            logger.warning(f"No policy validation found in database for run: {run_id}")
        
        # Load LLM output for risk assessment from database
        overall_risk_level = "unknown"
        llm_summary = {}
        logger.info(f"Loading LLM output from database for run: {run_id}")
        llm_data = get_latest_llm_output(run_id)
        
        if llm_data:
            llm_summary = llm_data.get("summary", {})
            overall_risk_level = llm_summary.get("overall_risk", "unknown").lower()
        else:
            logger.warning(f"No LLM output found in database for run: {run_id}")
        
        # Load certification result from database
        cert_data = {}
        logger.info(f"Loading certification from database for run: {run_id}")
        cert_data = get_latest_certification(run_id)
        
        if not cert_data:
            logger.warning(f"No certification found in database for run: {run_id}")
        
        # Intelligent verdict logic (incorporate certification decision)
        if certification_decision == "AUTO_MERGE":
            verdict = "PASS"
        elif certification_decision == "BLOCK_MERGE":
            verdict = "FAIL"
        else:
            # Use traditional verdict logic for HUMAN_REVIEW
            verdict = determine_verdict(
                files_with_drift=files_with_drift,
                overall_risk_level=overall_risk_level,
                policy_violations=policy_violations,
                environment=environment
            )
        
        # Count violations by severity
        critical_violations = len([v for v in policy_violations if v.get('severity') == 'critical'])
        high_violations = len([v for v in policy_violations if v.get('severity') == 'high'])
        
        # Aggregate results from all 5 agents
        aggregated = {
            "files_analyzed": total_files_compared,
            "files_compared": total_files_compared,
            "files_with_drift": files_with_drift,
            "total_deltas": len(deltas),
            "policy_violations_count": len(policy_violations),
            "policy_violations": policy_violations,
            "critical_violations": critical_violations,
            "high_violations": high_violations,
            "overall_risk_level": overall_risk_level,
            "verdict": verdict,
            "environment": environment,
            "certification": {
                "confidence_score": confidence_score,
                "certification_decision": certification_decision,
                "snapshot_branch": snapshot_branch
            }
        }
        
        logger.info(f"✅ Aggregated results: {verdict} (Certification: {certification_decision}, Score: {confidence_score}/100, Risk: {overall_risk_level}, Violations: {len(policy_violations)})")
        
        # Save to database only (no JSON files)
        try:
            save_aggregated_results(run_id, aggregated)
            logger.info(f"✅ Aggregated results saved to database for run: {run_id}")
        except Exception as e:
            logger.error(f"Failed to save aggregated results to database: {e}")
            return {
                "success": False,
                "error": f"Failed to save aggregated results to database: {str(e)}"
            }
        
        logger.info(f"Aggregated results processed")
        
        # Return summary data (no file paths)
        return {
            "success": True,
            "message": f"Aggregated results: {verdict}",
            "data": {
                "verdict": verdict,
                "files_with_drift": files_with_drift,
                "overall_risk_level": overall_risk_level,
                "policy_violations_count": len(policy_violations),
                "critical_violations": critical_violations,
                "high_violations": high_violations,
                "confidence_score": confidence_score,
                "certification_decision": certification_decision,
                "snapshot_branch": snapshot_branch
            }
        }
        
    except Exception as e:
        logger.exception(f"Failed to aggregate results: {e}")
        return {
            "success": False,
            "error": f"Failed to aggregate results: {str(e)}"
        }


def determine_verdict(
    files_with_drift: int,
    overall_risk_level: str,
    policy_violations: list,
    environment: str
) -> str:
    """
    Determine intelligent verdict based on drift, risk, violations, and environment.
    
    Business Logic:
    - PASS: No drift detected
    - BLOCK: Critical violations or high risk in production
    - REVIEW_REQUIRED: Medium risk or violations that need human review
    - WARN: Low risk changes that should be reviewed but not blocking
    
    Args:
        files_with_drift: Number of files with configuration drift
        overall_risk_level: AI-assessed overall risk (low, medium, high, critical)
        policy_violations: List of policy violations
        environment: Target environment (production, staging, development)
        
    Returns:
        Verdict string (PASS, BLOCK, REVIEW_REQUIRED, WARN)
    """
    # No drift = always pass
    if files_with_drift == 0:
        return "PASS"
    
    # Check for critical violations
    critical_violations = [v for v in policy_violations if isinstance(v, dict) and v.get('severity') == 'critical']
    if critical_violations:
        return "BLOCK"
    
    # Environment-specific rules
    if environment == "production":
        # Production has lower risk tolerance
        if overall_risk_level == "critical":
            return "BLOCK"
        elif overall_risk_level == "high":
            return "BLOCK"
        elif overall_risk_level == "medium":
            # Medium risk in production requires review
            high_violations = [v for v in policy_violations if v.get('severity') == 'high']
            if high_violations:
                return "REVIEW_REQUIRED"
            else:
                return "WARN"
        elif overall_risk_level == "low":
            if policy_violations:
                return "WARN"
            else:
                return "WARN"  # Even low-risk changes should be reviewed in production
    
    elif environment in ["staging", "pre-production"]:
        # Staging can tolerate more risk
        if overall_risk_level == "critical":
            return "BLOCK"
        elif overall_risk_level == "high":
            return "REVIEW_REQUIRED"
        elif overall_risk_level == "medium":
            return "WARN"
        else:
            return "WARN"
    
    else:  # development, testing, etc.
        # Development environments are more permissive
        if overall_risk_level == "critical":
            return "BLOCK"
        elif overall_risk_level == "high":
            return "REVIEW_REQUIRED"
        else:
            return "WARN"
    
    # Default fallback
    return "REVIEW_REQUIRED"


@tool
def format_validation_report(
    run_id: str,
    aggregated_results: dict
) -> dict:
    """
    Format comprehensive validation report with detailed violations and recommendations.
    
    Args:
        run_id: Validation run ID
        aggregated_results: Aggregated results from aggregate_validation_results
        
    Returns:
        Formatted markdown report with full details
        
    Example:
        >>> format_validation_report("run_xyz", aggregated_results)
    """
    try:
        from shared.db import get_latest_aggregated_results
        
        # Load full aggregated data from database
        logger.info(f"Loading aggregated results from database for run: {run_id}")
        
        # Extract service and environment from aggregated_results for DB query
        environment = aggregated_results.get("environment", "production")
        
        # Try to get from database first
        # Note: We'll use the passed aggregated_results as it contains all the data
        full_aggregated = aggregated_results
        
        # Extract data from aggregated results
        verdict = aggregated_results.get("verdict", "UNKNOWN")
        files_with_drift = aggregated_results.get("files_with_drift", 0)
        policy_violations = full_aggregated.get("policy_violations", [])
        critical_violations = aggregated_results.get("critical_violations", 0)
        high_violations = aggregated_results.get("high_violations", 0)
        risk_level = aggregated_results.get("overall_risk_level", "unknown")
        risk_assessment = full_aggregated.get("risk_assessment", {})
        recommendations = full_aggregated.get("recommendations", [])
        environment = full_aggregated.get("environment", "unknown")
        
        # Extract certification data
        certification_data = full_aggregated.get("certification", {})
        confidence_score = aggregated_results.get("confidence_score", certification_data.get("confidence_score", 0))
        certification_decision = aggregated_results.get("certification_decision", certification_data.get("certification_decision", "HUMAN_REVIEW"))
        snapshot_branch = aggregated_results.get("snapshot_branch", certification_data.get("snapshot_branch"))
        
        # Verdict emoji and color
        verdict_emoji = {
            "PASS": "✅",
            "WARN": "⚠️",
            "REVIEW_REQUIRED": "🔍",
            "BLOCK": "🚫"
        }.get(verdict, "❓")
        
        # Risk emoji
        risk_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴"
        }.get(risk_level, "⚪")
        
        # Build summary
        if verdict == "PASS":
            summary = "✅ **Configuration validated successfully.** No drift detected."
        elif verdict == "BLOCK":
            summary = f"🚫 **BLOCKED:** Critical issues detected. Deployment must be prevented."
        elif verdict == "REVIEW_REQUIRED":
            summary = f"🔍 **REVIEW REQUIRED:** Changes need human approval before deployment."
        elif verdict == "WARN":
            summary = f"⚠️ **WARNING:** Low-risk changes detected. Review recommended."
        else:
            summary = f"Found {files_with_drift} file(s) with drift"
        
        # Format report header
        report = f"""
# {verdict_emoji} Configuration Validation Report

**Run ID:** `{run_id}`  
**Verdict:** **{verdict}**  
**Environment:** **{environment}**  
**Risk Level:** {risk_emoji} **{risk_level.upper()}**  
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📋 Executive Summary

{summary}

### Key Metrics
- **Files Analyzed:** {full_aggregated.get('files_analyzed', 0)}
- **Files with Drift:** {files_with_drift}
- **Total Deltas Detected:** {full_aggregated.get('total_deltas', 0)}
- **Policy Violations:** {len(policy_violations)}
- **Critical Violations:** {critical_violations}
- **High Violations:** {high_violations}
- **Confidence Score:** {confidence_score}/100
- **Certification Decision:** {certification_decision}
- **Evidence Checks:** {len([d for d in full_aggregated.get('analyzed_deltas', []) if d.get('evidence_check')])}
- **Policy Violations:** {len(policy_violations)} ({critical_violations} critical, {high_violations} high)
- **Overall Risk:** {risk_level}
- **Analysis Type:** Policy-Aware (drift.py + AI + Clustering + Pinpoint + Evidence)

---
"""
        
        # Add clusters section if any (NEW: Clustering feature)
        clusters = full_aggregated.get('clusters', [])
        if clusters:
            report += "\n## 🔗 Change Clusters (Grouped by Root Cause)\n\n"
            report += "*Related changes grouped together for better insights:*\n\n"
            
            for i, cluster in enumerate(clusters, 1):
                cluster_id = cluster.get('id', 'unknown')
                root_cause = cluster.get('root_cause', 'Unknown cause')
                items = cluster.get('items', [])
                severity = cluster.get('severity', 'medium')
                verdict = cluster.get('verdict', 'DRIFT_WARN')
                cluster_type = cluster.get('type', 'unknown')
                confidence = cluster.get('confidence', 0.0)
                
                # Emoji based on severity
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(severity, '⚪')
                
                verdict_emoji = {
                    'DRIFT_BLOCKING': '🚫',
                    'DRIFT_WARN': '⚠️',
                    'NEW_BUILD_OK': '✅',
                    'NO_DRIFT': '✅'
                }.get(verdict, '❓')
                
                report += f"### {i}. {severity_emoji} {root_cause}\n\n"
                report += f"- **Cluster ID:** `{cluster_id}`\n"
                report += f"- **Type:** {cluster_type.replace('_', ' ').title()}\n"
                report += f"- **Severity:** {severity.upper()}\n"
                report += f"- **Verdict:** {verdict_emoji} {verdict}\n"
                report += f"- **Confidence:** {confidence:.0%}\n"
                report += f"- **Affected Items:** {len(items)} deltas\n"
                
                # Show affected files if available
                if 'files' in cluster:
                    files = cluster['files']
                    report += f"- **Affected Files:** {', '.join(files[:5])}"
                    if len(files) > 5:
                        report += f" (and {len(files) - 5} more)"
                    report += "\n"
                elif 'file' in cluster:
                    report += f"- **File:** {cluster['file']}\n"
                
                # Show pattern if available
                if 'pattern' in cluster:
                    report += f"- **Pattern:** {cluster['pattern'].replace('_', ' ').title()}\n"
                
                # Show ecosystem if available
                if 'ecosystem' in cluster:
                    report += f"- **Ecosystem:** {cluster['ecosystem']}\n"
                
                report += f"\n**Related Changes:**\n"
                for item_id in items[:10]:  # Show first 10 items
                    report += f"- `{item_id}`\n"
                if len(items) > 10:
                    report += f"- *(and {len(items) - 10} more...)*\n"
                
                report += "\n"
            
            report += "---\n\n"
        
        # Add policy violations section if any
        if policy_violations:
            report += "\n## 🚨 Policy Violations\n\n"
            
            # Group violations by severity
            violations_by_severity = {
                'critical': [],
                'high': [],
                'medium': [],
                'low': []
            }
            
            for violation in policy_violations:
                severity = violation.get('severity', 'medium').lower()
                if severity in violations_by_severity:
                    violations_by_severity[severity].append(violation)
            
            # Critical violations
            if violations_by_severity['critical']:
                report += "### 🔴 Critical Violations\n\n"
                for i, v in enumerate(violations_by_severity['critical'], 1):
                    report += f"{i}. **{v.get('type', 'Unknown').upper()}:** {v.get('description', 'No description')}\n"
                    if v.get('rule'):
                        report += f"   - **Rule:** `{v['rule']}`\n"
                report += "\n"
            
            # High severity violations
            if violations_by_severity['high']:
                report += "### 🟠 High Severity Violations\n\n"
                for i, v in enumerate(violations_by_severity['high'], 1):
                    report += f"{i}. **{v.get('type', 'Unknown').upper()}:** {v.get('description', 'No description')}\n"
                    if v.get('rule'):
                        report += f"   - **Rule:** `{v['rule']}`\n"
                report += "\n"
            
            # Medium/Low violations
            other_violations = violations_by_severity['medium'] + violations_by_severity['low']
            if other_violations:
                report += "### 🟡 Other Violations\n\n"
                for i, v in enumerate(other_violations, 1):
                    report += f"{i}. **{v.get('type', 'Unknown')}:** {v.get('description', 'No description')}\n"
                report += "\n"
            
            report += "---\n\n"
        
        # Add patch hints section (NEW: Copy-pasteable fixes)
        deltas_with_patches = aggregated_results.get('deltas_with_patches', [])
        if deltas_with_patches:
            report += "## 🔧 Patch Hints (Copy-Pasteable Fixes)\n\n"
            report += "*Copy these snippets directly into your files to fix the issues:*\n\n"
            
            for i, delta in enumerate(deltas_with_patches, 1):
                patch = delta.get('patch_hint', {})
                if not patch:
                    continue
                
                file = delta.get('file', 'unknown')
                verdict = delta.get('verdict', 'unknown')
                patch_type = patch.get('type', 'generic')
                patch_content = patch.get('content', '')
                
                # Only show patches for blocked or warn items
                if verdict in ['DRIFT_BLOCKING', 'DRIFT_WARN']:
                    report += f"### {i}. {file}\n\n"
                    report += f"**Issue:** {verdict}\n\n"
                    
                    # Format based on patch type
                    if patch_type == 'yaml_snippet':
                        report += "```yaml\n"
                    elif patch_type == 'json_snippet':
                        report += "```json\n"
                    elif patch_type == 'unified_diff':
                        report += "```diff\n"
                    elif patch_type == 'properties_snippet':
                        report += "```properties\n"
                    elif patch_type == 'dependency_update':
                        report += "```\n"
                    else:
                        report += "```\n"
                    
                    report += f"{patch_content}\n"
                    report += "```\n\n"
            
            report += "---\n\n"
        
        # Add pinpoint locations section (NEW: Feature #3)
        deltas_with_pinpoints = [d for d in aggregated_results.get('analyzed_deltas', []) if d.get('pinpoint')]
        if deltas_with_pinpoints:
            report += "## 📍 Pinpoint Locations (Quick Navigation)\n\n"
            report += "*Click these links to jump directly to the issues in your IDE:*\n\n"
            
            for i, delta in enumerate(deltas_with_pinpoints[:10], 1):  # Show top 10
                pinpoint = delta.get('pinpoint', {})
                file = pinpoint.get('file', 'unknown')
                location_string = pinpoint.get('location_string', file)
                human_readable = pinpoint.get('human_readable', f"{file}")
                navigation = pinpoint.get('navigation', {})
                nav_type = navigation.get('type', 'Location')
                search_hint = navigation.get('search_hint', f'Search in {file}')
                ide_links = pinpoint.get('ide_links', {})
                
                report += f"### {i}. {human_readable}\n\n"
                report += f"- **Location:** `{location_string}`\n"
                report += f"- **Type:** {nav_type}\n"
                report += f"- **Quick Access:** {search_hint}\n"
                
                # Add IDE links if available
                if ide_links:
                    report += "- **IDE Links:**\n"
                    for ide, link in ide_links.items():
                        ide_name = ide.replace('_', ' ').title()
                        report += f"  - [{ide_name}]({link})\n"
                
                # Add VS Code command
                vs_code_cmd = navigation.get('vs_code_command', '')
                if vs_code_cmd:
                    report += f"- **VS Code:** {vs_code_cmd}\n"
                
                # Add Vim command
                vim_cmd = navigation.get('vim_command', '')
                if vim_cmd:
                    report += f"- **Vim:** {vim_cmd}\n"
                
                report += "\n"
            
            if len(deltas_with_pinpoints) > 10:
                report += f"*... and {len(deltas_with_pinpoints) - 10} more locations*\n\n"
            
            report += "---\n\n"
        
        # Add evidence checking section (NEW: Feature #4)
        deltas_with_evidence = [d for d in aggregated_results.get('analyzed_deltas', []) if d.get('evidence_check')]
        if deltas_with_evidence:
            report += "## 🔍 Evidence Checking (Approval Requirements)\n\n"
            report += "*Validation against required approvals and evidence:*\n\n"
            
            # Group by approval status
            approved = [d for d in deltas_with_evidence if d.get('evidence_check', {}).get('approval_status') == 'approved']
            partial = [d for d in deltas_with_evidence if d.get('evidence_check', {}).get('approval_status') == 'partial_approval']
            pending = [d for d in deltas_with_evidence if d.get('evidence_check', {}).get('approval_status') == 'pending_review']
            rejected = [d for d in deltas_with_evidence if d.get('evidence_check', {}).get('approval_status') == 'rejected']
            
            if rejected:
                report += f"### ❌ Blocked Changes ({len(rejected)})\n\n"
                for i, delta in enumerate(rejected[:5], 1):
                    evidence_check = delta.get('evidence_check', {})
                    file = evidence_check.get('file', 'unknown')
                    location = evidence_check.get('location', '')
                    compliance_score = evidence_check.get('compliance_score', 0.0)
                    summary = evidence_check.get('validation_summary', '')
                    
                    report += f"#### {i}. {file}\n\n"
                    report += f"- **Location:** `{location}`\n"
                    report += f"- **Compliance:** {compliance_score:.0%}\n"
                    report += f"- **Status:** {summary}\n"
                    
                    # Show missing evidence
                    missing = evidence_check.get('evidence_missing', [])
                    if missing:
                        report += f"- **Missing Evidence:**\n"
                        for missing_req in missing[:3]:  # Show first 3
                            req_type = missing_req.get('requirement', '')
                            description = missing_req.get('description', '')
                            priority = missing_req.get('priority', '')
                            ticket_type = missing_req.get('ticket_type', '')
                            
                            priority_emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(priority, '⚪')
                            report += f"  - {priority_emoji} {description}\n"
                            report += f"    Required: {ticket_type}\n"
                    
                    report += "\n"
                
                if len(rejected) > 5:
                    report += f"*... and {len(rejected) - 5} more blocked changes*\n\n"
                
                report += "---\n\n"
            
            if pending:
                report += f"### 🔄 Pending Review ({len(pending)})\n\n"
                for i, delta in enumerate(pending[:3], 1):
                    evidence_check = delta.get('evidence_check', {})
                    file = evidence_check.get('file', 'unknown')
                    location = evidence_check.get('location', '')
                    summary = evidence_check.get('validation_summary', '')
                    
                    report += f"#### {i}. {file}\n\n"
                    report += f"- **Location:** `{location}`\n"
                    report += f"- **Status:** {summary}\n"
                    
                    # Show found evidence
                    found = evidence_check.get('evidence_found', [])
                    if found:
                        report += f"- **Evidence Found:**\n"
                        for evidence in found[:2]:  # Show first 2
                            evidence_id = evidence.get('evidence_id', '')
                            evidence_type = evidence.get('evidence_type', '')
                            description = evidence.get('description', '')
                            report += f"  - ✅ {evidence_type}: {description}\n"
                    
                    report += "\n"
                
                report += "---\n\n"
            
            if partial:
                report += f"### ⚠️ Partial Approval ({len(partial)})\n\n"
                for i, delta in enumerate(partial[:3], 1):
                    evidence_check = delta.get('evidence_check', {})
                    file = evidence_check.get('file', 'unknown')
                    location = evidence_check.get('location', '')
                    summary = evidence_check.get('validation_summary', '')
                    
                    report += f"#### {i}. {file}\n\n"
                    report += f"- **Location:** `{location}`\n"
                    report += f"- **Status:** {summary}\n\n"
                
                report += "---\n\n"
            
            if approved:
                report += f"### ✅ Fully Approved ({len(approved)})\n\n"
                for i, delta in enumerate(approved[:3], 1):
                    evidence_check = delta.get('evidence_check', {})
                    file = evidence_check.get('file', 'unknown')
                    location = evidence_check.get('location', '')
                    summary = evidence_check.get('validation_summary', '')
                    
                    report += f"#### {i}. {file}\n\n"
                    report += f"- **Location:** `{location}`\n"
                    report += f"- **Status:** {summary}\n\n"
                
                report += "---\n\n"
        
        # Add risk assessment section
        if risk_assessment:
            report += "## 📊 Risk Assessment\n\n"
            
            # Safety check: ensure risk_assessment is a dict
            if isinstance(risk_assessment, str):
                report += f"{risk_assessment}\n\n"
            elif isinstance(risk_assessment, dict):
                risk_factors = risk_assessment.get('risk_factors', [])
                if risk_factors:
                    report += "### Risk Factors\n\n"
                    for factor in risk_factors:
                        report += f"- {factor}\n"
                    report += "\n"
                
                mitigation_strategies = risk_assessment.get('mitigation_strategies', [])
                if mitigation_strategies:
                    priority = risk_assessment.get('mitigation_priority', 'standard')
                    priority_emoji = "🚨" if priority == "urgent" else "📌"
                    
                    report += f"### {priority_emoji} Mitigation Strategies (Priority: {priority.upper()})\n\n"
                    for i, strategy in enumerate(mitigation_strategies, 1):
                        report += f"{i}. {strategy}\n"
                    report += "\n"
            
            report += "---\n\n"
        
        # Add recommendations section
        if recommendations:
            report += "## 🔧 Recommendations\n\n"
            for i, rec in enumerate(recommendations, 1):
                if isinstance(rec, dict):
                    priority = rec.get('priority', 'medium')
                    action = rec.get('action', str(rec))
                    rationale = rec.get('rationale', '')
                    report += f"{i}. **[{priority.upper()}]** {action}\n"
                    if rationale:
                        report += f"   - *{rationale}*\n"
                else:
                    report += f"{i}. {rec}\n"
            report += "\n---\n\n"
        
        # Add next steps based on verdict
        report += "## 🎯 Next Steps\n\n"
        if verdict == "PASS":
            report += "✅ No action required. Configuration is compliant.\n\n"
        elif verdict == "BLOCK":
            report += """
🚫 **DEPLOYMENT BLOCKED**

**Required Actions:**
1. Review all critical violations listed above
2. Revert changes or fix violations
3. Re-run validation before attempting deployment
4. Do not proceed to production with these issues

**If you believe this is a false positive, contact the security team.**
"""
        elif verdict == "REVIEW_REQUIRED":
            report += """
🔍 **MANUAL REVIEW REQUIRED**

**Required Actions:**
1. Review the policy violations and risk assessment
2. Determine if changes are acceptable for the target environment
3. If approved, document the decision and proceed
4. If rejected, revert changes and re-validate

**Approval from team lead or security team may be required.**
"""
        elif verdict == "WARN":
            report += """
⚠️ **REVIEW RECOMMENDED**

**Suggested Actions:**
1. Review the changes to ensure they are intentional
2. Verify changes in staging environment before production
3. Monitor for any unexpected behavior after deployment
4. Consider adding these changes to your golden config

**Deployment may proceed with appropriate review.**
"""
        
        report += "\n---\n\n"
        
        # Add certification section
        certification_data = aggregated_results.get('certification', {})
        if certification_data:
            report += "## 🎯 Certification Result\n\n"
            confidence_score = certification_data.get('confidence_score', 0)
            certification_decision = certification_data.get('certification_decision', 'HUMAN_REVIEW')
            snapshot_branch = certification_data.get('snapshot_branch')
            
            decision_emoji = {
                'AUTO_MERGE': '✅',
                'HUMAN_REVIEW': '🔍',
                'BLOCK_MERGE': '🚫'
            }.get(certification_decision, '❓')
            
            report += f"**Decision:** {decision_emoji} {certification_decision}\n\n"
            report += f"**Confidence Score:** {confidence_score}/100\n\n"
            
            if snapshot_branch:
                report += f"**Certified Snapshot Branch:** `{snapshot_branch}`\n\n"
            
            report += "---\n\n"
        
        # Add database reference
        report += "## 💾 Data Storage\n\n"
        report += f"All validation data stored in database for run ID: `{run_id}`\n\n"
        report += "**Database Tables:**\n"
        report += "- `validation_runs` - Run metadata\n"
        report += "- `context_bundles` - Drift analysis data\n"
        report += "- `llm_outputs` - Risk categorization\n"
        report += "- `policy_validations` - Security scan results\n"
        report += "- `certifications` - Final certification decision\n"
        report += "- `aggregated_results` - Aggregated analysis\n"
        report += "- `reports` - This report\n\n"
        
        # Add pipeline info
        report += """## 🔄 Validation Pipeline

```
Supervisor Agent (Claude 3.5 Sonnet)
    ↓
    ├─► Config Collector Agent (Claude 3 Haiku)
    │   └─► Extract config files, create golden/drift snapshots
    │
    ├─► Drift Detector Agent (Claude 3 Haiku)
    │   └─► Precision drift analysis → DB (context_bundles)
    │       • Line-precise locators (yamlpath, jsonpath)
    │       • Structured deltas
    │       • Dependency analysis
    │
    ├─► Triaging-Routing Agent (Claude 3 Haiku)
    │   └─► LLM-based risk analysis → DB (llm_outputs)
    │       • Risk categorization (high/medium/low/allowed_variance)
    │       • Fetches context_bundle from DB
    │
    ├─► Guardrails & Policy Agent (Claude 3 Haiku)
    │   └─► Security & compliance → DB (policy_validations)
    │       • PII redaction
    │       • Intent guard scanning
    │       • Policy validation
    │       • Fetches llm_output from DB
    │
    └─► Certification Engine Agent (Claude 3 Haiku)
        └─► Final decision → DB (certifications)
            • Confidence score calculation (0-100)
            • Certification decision (AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE)
            • Certified snapshot creation
            • Fetches policy_validation from DB
```

*Powered by AWS Strands Multi-Agent Framework + Database-Only Architecture*

---

**Report Generated:** {timestamp}
""".format(timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        logger.info(f"✅ Formatted comprehensive validation report for run {run_id}")
        
        # Save report to database only (no JSON files)
        try:
            save_report(run_id, report)
            logger.info(f"✅ Report saved to database for run: {run_id}")
        except Exception as e:
            logger.error(f"Failed to save report to database: {e}")
            return {
                "success": False,
                "error": f"Failed to save report to database: {str(e)}"
            }
        
        # Return minimal response to avoid max_tokens issues
        return {
            "success": True,
            "message": f"Comprehensive validation report formatted and saved successfully",
            "data": {
                "report_length": len(report),
                "verdict": verdict,
                "files_with_drift": files_with_drift,
                "policy_violations": len(policy_violations),
                "risk_level": risk_level
            }
        }
        
    except Exception as e:
        logger.exception(f"Failed to format report: {e}")
        return {
            "success": False,
            "error": f"Failed to format report: {str(e)}"
        }


@tool
def save_validation_report(
    run_id: str,
    report: str = ""
) -> dict:
    """
    Save validation report to database only (no files).
    
    This tool saves reports to database. format_validation_report also auto-saves,
    so this is mainly for backward compatibility.
    
    Args:
        run_id: Validation run ID
        report: Formatted report text (optional, will check database)
        
    Returns:
        Confirmation of save
        
    Example:
        >>> save_validation_report("run_xyz", "## Validation Report...")
    """
    try:
        from shared.db import get_latest_report
        
        # Check if report was already saved by format_validation_report
        existing_report = get_latest_report(run_id)
        if existing_report and not report:
            logger.info(f"Report already saved in database for run: {run_id}")
            return {
                "success": True,
                "message": f"Report already saved for run {run_id}",
                "data": {"report_length": len(existing_report)}
            }
        
        # Save report if provided
        if report:
            save_report(run_id, report)
            logger.info(f"Saved report for run {run_id} to database")
        
        return {
            "success": True,
            "message": f"Report saved to database for run {run_id}",
            "data": {"report_length": len(report) if report else len(existing_report)}
        }
        
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return {
            "success": False,
            "error": f"Failed to save report: {str(e)}"
        }


# ============================================================================
# AGENT CREATION
# ============================================================================

def create_supervisor_agent() -> Agent:
    """
    Create and configure the Supervisor Agent.
    
    Returns:
        Configured Strands Agent instance with Bedrock Claude Sonnet model
        
    Example:
        >>> agent = create_supervisor_agent()
        >>> result = agent("Validate configurations")
    """
    # Model configuration - Claude 3.5 Sonnet (smarter for orchestration)
    model = create_supervisor_model(config)
    
    # Create agent with orchestration tools (simplified to 5 tools)
    agent = Agent(
        name="supervisor",
        description="Orchestrates 5-agent validation workflow (Config Collector → Drift Detector → Guardrails & Policy → Triaging-Routing → Certification Engine)",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        tools=[
            create_validation_run,
            execute_worker_pipeline,
            aggregate_validation_results,
            format_validation_report,
            save_validation_report
        ]
    )
    
    logger.info("Supervisor Agent created with 2-agent orchestration")
    return agent


# ============================================================================
# HIGH-LEVEL API
# ============================================================================

def run_validation(
    project_id: str,
    mr_iid: str,
    repo_url: str,
    main_branch: str,
    environment: str,
    target_folder: str = ""
) -> dict:
    """
    High-level function to run complete 2-agent file-based validation with dynamic branch creation.
    
    This is the main entry point for running a complete validation using
    file-based communication between agents and dynamic branch management.
    
    Args:
        project_id: Project identifier (e.g., "myorg/myrepo" or "cxp_ordering_services")
        mr_iid: Merge request or validation ID
        repo_url: GitLab repository URL
        main_branch: Main branch name (source of current configs)
        environment: Environment name (prod, dev, qa, staging)
        target_folder: Optional subfolder to analyze
        
    Returns:
        Dictionary with validation results and file paths
        
    Example:
        >>> result = run_validation(
        ...     "cxp_ordering_services", "123",
        ...     "https://gitlab.verizon.com/saja9l7/golden_config.git",
        ...     "main", "prod"
        ... )
        >>> print(f"Verdict: {result['verdict']}")
        
    Raises:
        Exception: If validation fails
    """
    start_time = datetime.now()
    logger.info(f"Starting 2-agent file-based validation for {mr_iid} in {project_id}")
    
    # Create supervisor agent
    agent = create_supervisor_agent()
    
    # Instruction for supervisor
    instruction = f"""
    Please orchestrate the complete 5-agent file-based validation workflow with dynamic branch management:
    
    Project: {project_id}
    MR/ID: {mr_iid}
    Repository: {repo_url}
    Main Branch: {main_branch}
    Environment: {environment}
    Target Folder: {target_folder or "entire repository"}
    
    Complete workflow:
    1. Create a unique validation run ID
    2. Execute the 5-agent database-only pipeline in CORRECT ORDER:
       - Config Collector: Extract config files, create golden/drift snapshots (Git operations only)
       - Drift Detector: Perform precision drift analysis → save to DB (context_bundles table)
       - Guardrails & Policy: PII redaction, security scanning → fetch from DB, save to DB (policy_validations table) [MUST RUN BEFORE LLM]
       - Triaging-Routing: LLM-based risk analysis on sanitized data → fetch from DB, save to DB (llm_outputs table)
       - Certification Engine: Final decision, snapshot creation → fetch from DB, save to DB (certifications table)
    3. Aggregate results from all 5 agents (fetch all data from DB using run_id)
    4. Format a comprehensive validation report with:
       - Clear verdict (PASS/WARN/REVIEW_REQUIRED/BLOCK)
       - Summary of drift findings
       - Policy violations
       - Risk assessment
       - Confidence score and certification decision
       - Recommendations
    5. Save the validation report to database
    
    Use database queries for all inter-agent communication (no file operations).
    All data persists in SQLite database.
    Be thorough and ensure all steps complete successfully.
    """
    
    # Execute supervisor
    result = agent(instruction)
    
    # Calculate execution time
    execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    logger.info(f"Validation completed in {execution_time}ms")
    
    # Load the latest LLM output and aggregated results from database for rich UI data
    llm_output_data = {}
    aggregated_data = {}
    
    try:
        from shared.db import get_latest_llm_output, get_latest_aggregated_results
        
        # Try to extract service name and run_id for DB queries
        run_id_match = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{mr_iid}"
        
        # Load from database
        llm_output_data = get_latest_llm_output(run_id=run_id_match) or {}
        
        # For aggregated results, we need service name
        # Extract from project_id (format: service_environment)
        service_name = project_id.rsplit('_', 1)[0] if '_' in project_id else project_id
        aggregated_data = get_latest_aggregated_results(service_name, environment) or {}
        
        if llm_output_data:
            logger.info(f"✅ Loaded LLM output for {environment} from database")
        else:
            logger.warning(f"⚠️ No LLM output found in database for run: {run_id_match}")
        
        if aggregated_data:
            logger.info(f"✅ Loaded aggregated results for {environment} from database")
        else:
            logger.warning(f"⚠️ No aggregated results found in database for {service_name}/{environment}")
    except Exception as e:
        logger.warning(f"Could not load analysis data from database: {e}")
    
    # Build comprehensive response with data for UI
    return {
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{mr_iid}",
        "verdict": aggregated_data.get("verdict", "COMPLETED"),
        "summary": str(result),
        "execution_time_ms": execution_time,
        "timestamp": datetime.now().isoformat(),
        # Add rich data for UI
        "files_analyzed": aggregated_data.get("files_analyzed", 0),
        "files_compared": aggregated_data.get("files_compared", 0),
        "files_with_drift": aggregated_data.get("files_with_drift", 0),
        "total_deltas": aggregated_data.get("total_deltas", 0),
        "deltas_analyzed": aggregated_data.get("deltas_analyzed", 0),
        "total_clusters": aggregated_data.get("total_clusters", 0),
        "policy_violations_count": aggregated_data.get("policy_violations_count", 0),
        "policy_violations": aggregated_data.get("policy_violations", []),
        "critical_violations": aggregated_data.get("critical_violations", 0),
        "high_violations": aggregated_data.get("high_violations", 0),
        "overall_risk_level": aggregated_data.get("overall_risk_level", "unknown"),
        "risk_assessment": aggregated_data.get("risk_assessment", {}),
        "recommendations": aggregated_data.get("recommendations", []),
        "environment": aggregated_data.get("environment", "unknown"),
        "clusters": aggregated_data.get("clusters", []),
        "analyzed_deltas": aggregated_data.get("analyzed_deltas", []),
        "deltas_with_patches": aggregated_data.get("deltas_with_patches", []),
        # NEW: LLM output data for UI
        "llm_output": llm_output_data
    }


# ============================================================================
# TESTING / DEBUG
# ============================================================================

if __name__ == "__main__":
    """Quick test of the Supervisor Agent."""
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s | %(name)s | %(message)s'
    )
    
    # Test agent creation
    print("🎯 Testing Supervisor Agent (2-Agent Orchestration)\n")
    
    agent = create_supervisor_agent()
    print(f"✅ Agent created: {agent.name}")
    print(f"   Model: {config.bedrock_model_id}")
    print(f"   Region: {config.aws_region}")
    print(f"   Tools: {len(agent.tool_registry.registry)}")
    
    for tool_name in agent.tool_registry.registry.keys():
        print(f"   - {tool_name}")
    
    print("\n🔧 Supervisor capabilities:")
    print("   - Create validation runs")
    print("   - Execute 2-agent pipeline (Config Collector + Diff Engine)")
    print("   - Aggregate results from both agents")
    print("   - Format validation reports")
    print("   - Save reports to file")
    
    print("\n✅ Supervisor Agent is ready!")
    print("\nTo use:")
    print("  from Agents.Supervisor.supervisor_agent import run_validation")
    print("  result = run_validation('myorg/myrepo', '123', 'feature', 'gold', {}, {})")

