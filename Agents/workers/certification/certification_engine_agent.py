"""
Certification Engine Agent - Final Decision Maker (Database-Only)

This agent makes the final certification decision based on all analysis.

Responsibilities:
- Fetch policy_validated_deltas from database using run_id
- Calculate confidence score (0-100)
- Make certification decision (AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE)
- Create certified snapshots
- Save certification to database (certifications table)

Input: run_id (fetches policy_validated_deltas from DB)
Output: Database record in certifications table, no JSON files
"""

import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools import tool

from shared.config import Config
from shared.models import TaskRequest, TaskResponse
from shared.db import save_certification
from .confidence_scorer import ConfidenceScorer

logger = logging.getLogger(__name__)


class CertificationEngineAgent(Agent):
    """
    Certification Engine Agent - Final Decision Maker
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config()
        
        system_prompt = self._get_system_prompt()
        
        super().__init__(
            model=BedrockModel(model_id=config.bedrock_worker_model_id),
            system_prompt=system_prompt,
            tools=[
                self.load_policy_validated_deltas,
                self.calculate_confidence_score,
                self.make_certification_decision,
                self.create_certified_snapshot,
                self.generate_certification_report
            ]
        )
        self.config = config
        self.confidence_scorer = ConfidenceScorer()

    def _get_system_prompt(self) -> str:
        return """You are the Certification Engine Agent in the Golden Config AI system.

Your responsibilities:
1. Calculate confidence score (0-100) based on all analysis
2. Make final certification decision (AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE)
3. Create certified snapshot branches when approved
4. Generate comprehensive certification reports

You are the final authority on whether a configuration change can proceed.
Be thorough and conservative - better to require review than allow risky changes.
"""

    def process_task(self, task: TaskRequest) -> TaskResponse:
        """
        Process a certification task.
        
        Args:
            task: TaskRequest with parameters:
                - run_id: Validation run ID (to fetch data from DB)
                - environment: Target environment (prod, staging, dev)
                - service_id: Service identifier
                - repo_url: Repository URL
                - golden_branch: Golden branch name
                - drift_branch: Drift branch name (optional, for snapshot creation)
                
        Returns:
            TaskResponse with summary data (no file paths)
        """
        start_time = time.time()
        
        try:
            logger.info("=" * 60)
            logger.info(f"🎯 Certification Engine processing task: {task.task_id}")
            logger.info("=" * 60)
            
            params = task.parameters
            
            # Extract parameters
            run_id = params.get('run_id')
            environment = params.get('environment', 'production')
            service_id = params.get('service_id')
            repo_url = params.get('repo_url')
            golden_branch = params.get('golden_branch')
            drift_branch = params.get('drift_branch')
            
            if not run_id:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Missing required parameter: run_id",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "certification"}
                )
            
            # Step 1: Load policy-validated deltas from database
            logger.info(f"📥 Loading policy-validated deltas from database for run: {run_id}...")
            try:
                from shared.db import get_latest_policy_validation
                validated_data = get_latest_policy_validation(run_id)
                
                if not validated_data:
                    return TaskResponse(
                        task_id=task.task_id,
                        status="failure",
                        result={},
                        error=f"Policy validated deltas not found in database for run: {run_id}",
                        processing_time_seconds=time.time() - start_time,
                        metadata={"agent": "certification"}
                    )
                
                logger.info(f"✅ Policy validated deltas loaded from database")
            except Exception as e:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to load policy validated deltas from database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "certification"}
                )
            
            validated_deltas = validated_data.get('validated_deltas', [])
            policy_summary = validated_data.get('policy_summary', {})
            llm_summary = validated_data.get('llm_summary', {})
            overview = validated_data.get('overview', {})
            
            # Step 2: Extract policy violations and risk level
            logger.info("🔍 Extracting policy violations and risk assessment...")
            policy_violations = self._extract_policy_violations(validated_deltas)
            risk_level = self._determine_risk_level(llm_summary, validated_deltas)
            evidence = self._extract_evidence(validated_data)
            
            # Step 3: Calculate confidence score
            logger.info("📊 Calculating confidence score...")
            confidence_result = self.confidence_scorer.calculate(
                policy_violations=policy_violations,
                risk_level=risk_level,
                evidence=evidence,
                environment=environment
            )
            
            # Step 4: Make certification decision (already included in confidence_result)
            decision = confidence_result.decision
            confidence_score = confidence_result.score
            
            logger.info(f"✅ Confidence Score: {confidence_score}/100")
            logger.info(f"✅ Decision: {decision}")
            
            # Step 5: Create certified snapshot if AUTO_MERGE
            snapshot_branch = None
            if decision == "AUTO_MERGE" and repo_url and golden_branch and drift_branch:
                logger.info("🌿 Creating certified snapshot branch...")
                snapshot_result = self._create_certified_snapshot(
                    repo_url=repo_url,
                    golden_branch=golden_branch,
                    drift_branch=drift_branch,
                    service_id=service_id,
                    environment=environment,
                    approved_deltas=validated_deltas,
                    confidence_score=confidence_score
                )
                snapshot_branch = snapshot_result.get('snapshot_branch')
                if snapshot_branch:
                    logger.info(f"✅ Certified snapshot branch created: {snapshot_branch}")
            
            # Step 6: Generate certification report
            logger.info("📄 Generating certification report...")
            certification_result = self._generate_certification_result(
                task_id=task.task_id,
                confidence_result=confidence_result,
                validated_deltas=validated_deltas,
                policy_violations=policy_violations,
                policy_summary=policy_summary,
                llm_summary=llm_summary,
                overview=overview,
                environment=environment,
                service_id=service_id,
                snapshot_branch=snapshot_branch
            )
            
            # Step 7: Save certification result to database only (no JSON files)
            try:
                save_certification(run_id, certification_result)
                logger.info(f"✅ Certification result saved to database for run: {run_id}")
            except Exception as e:
                logger.error(f"Failed to save certification to database: {e}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to save certification to database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "certification"}
                )
            
            logger.info("=" * 60)
            
            return TaskResponse(
                task_id=task.task_id,
                status="success",
                result={
                    "confidence_score": confidence_score,
                    "certification_decision": decision,
                    "snapshot_branch": snapshot_branch,
                    "summary": {
                        "total_deltas": len(validated_deltas),
                        "policy_violations": len(policy_violations),
                        "risk_level": risk_level,
                        "confidence_level": confidence_result.confidence_level
                    }
                },
                error=None,
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "certification"}
            )
            
        except Exception as e:
            logger.exception(f"❌ Certification Engine task processing failed: {e}")
            return TaskResponse(
                task_id=task.task_id,
                status="failure",
                result={},
                error=str(e),
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "certification"}
            )

    # Helper methods
    # Removed _load_policy_validated_deltas - now loading directly from DB in process_task
    
    def _extract_policy_violations(self, validated_deltas: list) -> list:
        """Extract policy violations from validated deltas"""
        violations = []
        
        for delta in validated_deltas:
            policy = delta.get('policy', {})
            
            # Check for invariant breach
            if policy.get('tag') == 'invariant_breach':
                violations.append({
                    'delta_id': delta.get('id', 'unknown'),
                    'file': delta.get('file', 'unknown'),
                    'severity': policy.get('severity', 'high'),
                    'rule': policy.get('rule', 'unknown'),
                    'reason': policy.get('reason', 'Invariant breach detected')
                })
            
            # Check for policy violations in meta
            policy_violations = delta.get('meta', {}).get('policy_violations', [])
            for violation in policy_violations:
                if violation.get('violation'):
                    violations.append({
                        'delta_id': delta.get('id', 'unknown'),
                        'file': delta.get('file', 'unknown'),
                        'severity': violation.get('severity', 'medium'),
                        'rule': violation.get('rule', 'unknown'),
                        'reason': violation.get('reason', 'Policy violation')
                    })
        
        return violations
    
    def _determine_risk_level(self, llm_summary: Dict[str, Any], validated_deltas: list) -> str:
        """Determine overall risk level from LLM summary and deltas"""
        # Check LLM summary first
        risk_level = llm_summary.get('overall_risk', '').lower()
        
        if risk_level in ['critical', 'high', 'medium', 'low', 'none']:
            return risk_level
        
        # Fallback: analyze deltas
        high_risk_count = sum(1 for d in validated_deltas 
                            if d.get('llm_category') == 'high')
        medium_risk_count = sum(1 for d in validated_deltas 
                              if d.get('llm_category') == 'medium')
        
        if high_risk_count > 0:
            return 'high'
        elif medium_risk_count > 0:
            return 'medium'
        else:
            return 'low'
    
    def _extract_evidence(self, validated_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract evidence information from validated data"""
        # Check for evidence in overview or meta
        overview = validated_data.get('overview', {})
        meta = validated_data.get('meta', {})
        
        # For now, return None (evidence tracking can be enhanced later)
        # This would include things like:
        # - Test results
        # - Approval signatures
        # - Documentation links
        # - Historical patterns
        
        return None
    
    def _create_certified_snapshot(
        self,
        repo_url: str,
        golden_branch: str,
        drift_branch: str,
        service_id: str,
        environment: str,
        approved_deltas: list,
        confidence_score: int
    ) -> Dict[str, Any]:
        """Create a certified snapshot branch by merging approved deltas"""
        try:
            from shared.git_operations import (
                generate_unique_branch_name,
                create_selective_golden_branch
            )
            from shared.golden_branch_tracker import add_golden_branch
            import os
            
            # Generate new golden branch name
            new_golden_branch = generate_unique_branch_name("golden", environment)
            
            # Get approved files from deltas
            approved_files = [delta.get('file') for delta in approved_deltas 
                            if delta.get('file')]
            
            # Get config paths (default patterns)
            config_paths = [
                "*.yml", "*.yaml", "*.json", "*.properties",
                "*.conf", "*.config", "*.toml", "*.ini"
            ]
            
            # Get GitLab token
            gitlab_token = os.getenv('GITLAB_TOKEN')
            
            # Create selective golden branch
            success = create_selective_golden_branch(
                repo_url=repo_url,
                old_golden_branch=golden_branch,
                drift_branch=drift_branch,
                new_branch_name=new_golden_branch,
                approved_files=approved_files,
                config_paths=config_paths,
                gitlab_token=gitlab_token
            )
            
            if success:
                # Track the new golden branch
                add_golden_branch(service_id, environment, new_golden_branch)
                
                return {
                    "snapshot_branch": new_golden_branch,
                    "approved_files_count": len(approved_files),
                    "confidence_score": confidence_score
                }
            else:
                logger.error("Failed to create certified snapshot branch")
                return {"snapshot_branch": None, "error": "Failed to create branch"}
                
        except Exception as e:
            logger.exception(f"Error creating certified snapshot: {e}")
            return {"snapshot_branch": None, "error": str(e)}
    
    def _generate_certification_result(
        self,
        task_id: str,
        confidence_result,
        validated_deltas: list,
        policy_violations: list,
        policy_summary: Dict[str, Any],
        llm_summary: Dict[str, Any],
        overview: Dict[str, Any],
        environment: str,
        service_id: str,
        snapshot_branch: Optional[str]
    ) -> Dict[str, Any]:
        """Generate comprehensive certification result - flattened for save_certification compatibility"""
        return {
            # Top-level fields for save_certification DB function
            "confidence_score": confidence_result.score,
            "decision": confidence_result.decision,
            "environment": environment,
            "violations_count": len(policy_violations),
            "high_risk_count": sum(1 for d in validated_deltas if d.get('llm_category') == 'high'),
            "certified_snapshot_branch": snapshot_branch,
            
            # Nested metadata for full certification data
            "meta": {
                "task_id": task_id,
                "certified_at": datetime.now().isoformat() + "Z",
                "service_id": service_id
            },
            "certification": {
                "confidence_level": confidence_result.confidence_level,
                "explanation": confidence_result.explanation,
                "components": confidence_result.components
            },
            "summary": {
                "total_deltas": len(validated_deltas),
                "policy_violations": len(policy_violations),
                "risk_level": self._determine_risk_level(llm_summary, validated_deltas),
                "high_risk_deltas": sum(1 for d in validated_deltas 
                                       if d.get('llm_category') == 'high'),
                "medium_risk_deltas": sum(1 for d in validated_deltas 
                                        if d.get('llm_category') == 'medium'),
                "low_risk_deltas": sum(1 for d in validated_deltas 
                                      if d.get('llm_category') == 'low'),
                "allowed_variance_deltas": sum(1 for d in validated_deltas 
                                             if d.get('llm_category') == 'allowed_variance')
            },
            "policy_violations": policy_violations,
            "policy_summary": policy_summary,
            "llm_summary": llm_summary,
            "overview": overview
        }

    # Tool methods for LLM agent use
    @tool
    def load_policy_validated_deltas(self, run_id: str) -> Dict[str, Any]:
        """Load policy-validated deltas from database"""
        try:
            from shared.db import get_latest_policy_validation
            validated_data = get_latest_policy_validation(run_id)
            
            if not validated_data:
                return {
                    "status": "error",
                    "error": f"Policy validated deltas not found for run: {run_id}"
                }
            
            return {
                "status": "success",
                "validated_data": validated_data
            }
        except Exception as e:
            logger.error(f"Failed to load policy validated deltas from database: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    @tool
    def calculate_confidence_score(
        self,
        validated_deltas: list,
        policy_violations: list,
        risk_level: str,
        environment: str
    ) -> Dict[str, Any]:
        """Calculate confidence score (0-100)"""
        evidence = None  # Can be enhanced later
        result = self.confidence_scorer.calculate(
            policy_violations=policy_violations,
            risk_level=risk_level,
            evidence=evidence,
            environment=environment
        )
        return {
            "score": result.score,
            "breakdown": result.components,
            "decision": result.decision,
            "explanation": result.explanation,
            "confidence_level": result.confidence_level
        }

    @tool
    def make_certification_decision(
        self,
        confidence_score: int,
        environment: str
    ) -> Dict[str, Any]:
        """Make certification decision based on score"""
        # Decision is already determined by ConfidenceScorer
        # This tool provides a way to check thresholds
        thresholds = {
            "production": 85,
            "staging": 75,
            "pre-production": 75,
            "development": 65,
            "dev": 65,
            "testing": 65
        }
        threshold = thresholds.get(environment.lower(), 75)
        
        if confidence_score >= threshold:
            decision = "AUTO_MERGE"
        elif confidence_score >= threshold - 25:
            decision = "HUMAN_REVIEW"
        else:
            decision = "BLOCK_MERGE"
        
        return {
            "decision": decision,
            "action": "merge" if decision == "AUTO_MERGE" else "review_required" if decision == "HUMAN_REVIEW" else "block",
            "threshold": threshold,
            "score": confidence_score
        }

    @tool
    def create_certified_snapshot(
        self,
        repo_url: str,
        golden_branch: str,
        drift_branch: str,
        service_id: str,
        environment: str,
        approved_deltas: list,
        confidence_score: int
    ) -> Dict[str, Any]:
        """Create certified snapshot branch"""
        return self._create_certified_snapshot(
            repo_url=repo_url,
            golden_branch=golden_branch,
            drift_branch=drift_branch,
            service_id=service_id,
            environment=environment,
            approved_deltas=approved_deltas,
            confidence_score=confidence_score
        )

    @tool
    def generate_certification_report(
        self,
        certification_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate certification report"""
        # Report is already generated in process_task
        # This tool provides access to the result
        return certification_result

