"""
Guardrails & Policy Engine Agent - Security & Compliance (Database-Only)

This agent enforces security guardrails and organizational policies.

**CRITICAL: This agent MUST run BEFORE Triaging to redact PII before LLM sees the data.**

Responsibilities:
- Fetch context_bundle from database using run_id
- PII redaction (detect and scrub sensitive data)
- Update context_bundle in database with redacted values
- Intent guard (detect malicious patterns)
- Policy validation (enforce policies.yaml rules)
- Save redacted context_bundle back to database for Triaging to consume

Input: run_id (fetches context_bundle from DB)
Output: Updated context_bundle with redacted data + policy_validation record in database
"""

import logging
import json
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools import tool

from shared.config import Config
from shared.models import TaskRequest, TaskResponse
from shared.db import save_policy_validation
from .pii_redactor import PIIRedactor
from .intent_guard import IntentGuard

logger = logging.getLogger(__name__)


class GuardrailsPolicyAgent(Agent):
    """
    Guardrails & Policy Engine Agent - Security & Compliance Enforcement
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config()
        
        system_prompt = self._get_system_prompt()
        
        super().__init__(
            model=BedrockModel(model_id=config.bedrock_worker_model_id),
            system_prompt=system_prompt,
            tools=[
                # NOTE: Removed load_llm_output and combine_delta_data - we run BEFORE Triaging now
                self.load_context_bundle,
                self.scan_for_pii,
                self.redact_sensitive_data,
                self.scan_for_malicious_patterns,
                self.validate_policies,
                self.apply_policy_tags,
                self.generate_validated_output
            ]
        )
        self.config = config
        self.pii_redactor = PIIRedactor()
        self.intent_guard = IntentGuard()

    def _get_system_prompt(self) -> str:
        return """You are the Guardrails & Policy Engine Agent in the Golden Config AI system.

Your responsibilities:
1. Detect and redact PII (personally identifiable information) and secrets
2. Scan for malicious patterns (SQL injection, command injection, backdoors)
3. Validate against organizational policies (policies.yaml)
4. Apply policy tags (invariant_breach, allowed_variance, suspect)

You ensure security and compliance before final certification.
Always err on the side of caution - better to flag than miss a security issue.
"""

    def process_task(self, task: TaskRequest) -> TaskResponse:
        """
        Process a guardrails & policy validation task.
        
        Args:
            task: TaskRequest with parameters:
                - run_id: Validation run ID (to fetch data from DB)
                - environment: Environment name (optional)
                
        Returns:
            TaskResponse with summary data (no file paths)
        """
        start_time = time.time()
        
        try:
            logger.info("=" * 60)
            logger.info(f"🔐 Guardrails & Policy processing task: {task.task_id}")
            logger.info("=" * 60)
            
            params = task.parameters
            
            # Extract parameters
            run_id = params.get('run_id')
            environment = params.get('environment', 'production')
            
            if not run_id:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Missing required parameter: run_id",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "guardrails_policy"}
                )
            
            # Load context_bundle from database (ONLY source before LLM redaction)
            logger.info(f"\n📂 Loading context bundle from database for run: {run_id}")
            logger.info("-" * 60)
            
            try:
                from shared.db import get_latest_context_bundle
                context_bundle = get_latest_context_bundle(run_id)
                if not context_bundle:
                    return TaskResponse(
                        task_id=task.task_id,
                        status="failure",
                        result={},
                        error=f"Context bundle not found in database for run: {run_id}",
                        processing_time_seconds=time.time() - start_time,
                        metadata={"agent": "guardrails_policy"}
                    )
                
                logger.info(f"✅ Context bundle loaded from database")
                
            except Exception as e:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to load context bundle from database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "guardrails_policy"}
                )
            
            logger.info(f"✅ Context bundle loaded successfully from database")
            
            # Extract deltas from context bundle (NO LLM OUTPUT YET - we run BEFORE Triaging)
            logger.info(f"\n🔗 Extracting deltas from context bundle...")
            logger.info("-" * 60)
            
            combined_deltas = context_bundle.get('deltas', [])
            logger.info(f"✅ Found {len(combined_deltas)} deltas to process")
            
            if not combined_deltas:
                logger.warning("No deltas to process - saving empty policy validation")
                
                # Save empty policy validation to database (Certification Engine expects this)
                empty_result = {
                    "pii_report": {"instances_found": 0, "types": []},
                    "intent_report": {"total_findings": 0, "critical_findings": 0},
                    "policy_summary": {"total_violations": 0, "high": 0, "medium": 0, "low": 0},
                    "validated_deltas": []
                }
                
                try:
                    save_policy_validation(run_id, empty_result)
                    logger.info("✅ Empty policy validation saved to database")
                except Exception as e:
                    logger.error(f"Failed to save empty policy validation: {e}")
                
                return TaskResponse(
                    task_id=task.task_id,
                    status="success",
                    result={
                        "summary": {
                            "pii_found": False,
                            "pii_redacted_count": 0,
                            "policy_violations": 0,
                            "suspicious_patterns": 0,
                            "critical_findings": 0
                        }
                    },
                    error=None,
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "guardrails_policy"}
                )
            
            # Scan for PII and redact
            logger.info(f"\n🔍 Scanning for PII and secrets...")
            logger.info("-" * 60)
            
            pii_redacted_deltas, pii_report = self._scan_and_redact_pii(combined_deltas)
            logger.info(f"✅ PII scan complete:")
            logger.info(f"   Instances found: {pii_report['instances_found']}")
            logger.info(f"   Types detected: {', '.join(pii_report['types']) if pii_report['types'] else 'none'}")
            
            # CRITICAL SECURITY: Update context_bundle with redacted deltas and save back to DB
            # This ensures Triaging LLM only sees sanitized data
            logger.info(f"\n💾 Updating context bundle with redacted deltas...")
            logger.info("-" * 60)
            
            try:
                from shared.db import update_context_bundle_deltas
                context_bundle['deltas'] = pii_redacted_deltas
                update_context_bundle_deltas(run_id, pii_redacted_deltas)
                logger.info(f"✅ Context bundle updated with {len(pii_redacted_deltas)} redacted deltas")
                logger.info(f"   Triaging agent will now receive PII-redacted data")
            except Exception as e:
                logger.error(f"Failed to update context bundle with redacted data: {e}")
                # Continue processing but log the error
            
            # Scan for malicious patterns
            logger.info(f"\n🛡️ Scanning for malicious patterns...")
            logger.info("-" * 60)
            
            intent_scanned_deltas, intent_report = self._scan_for_malicious_patterns(pii_redacted_deltas)
            logger.info(f"✅ Intent guard scan complete:")
            logger.info(f"   Suspicious patterns: {intent_report['total_findings']}")
            logger.info(f"   Critical findings: {intent_report['critical_findings']}")
            
            # Validate policies
            logger.info(f"\n📋 Validating against policies.yaml...")
            logger.info("-" * 60)
            
            validated_deltas, policy_summary = self._validate_policies(intent_scanned_deltas, context_bundle.get('overview', {}))
            logger.info(f"✅ Policy validation complete:")
            logger.info(f"   Total violations: {policy_summary['total_violations']}")
            logger.info(f"   Critical: {policy_summary['critical']}")
            logger.info(f"   High: {policy_summary['high']}")
            
            # Generate validated output
            logger.info(f"\n📦 Generating validated output...")
            logger.info("-" * 60)
            
            # NOTE: We run BEFORE Triaging, so no LLM output exists yet
            validated_output = self._generate_validated_output(
                validated_deltas,
                pii_report,
                intent_report,
                policy_summary,
                {},  # No LLM summary yet - we run before Triaging
                context_bundle.get('overview', {})
            )
            
            # Save to database only (no JSON files)
            try:
                save_policy_validation(run_id, validated_output)
                logger.info(f"✅ Policy validation saved to database for run: {run_id}")
            except Exception as e:
                logger.error(f"Failed to save policy validation to database: {e}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to save policy validation to database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "guardrails_policy"}
                )
            
            logger.info("\n✅ Guardrails & Policy completed!")
            logger.info("=" * 60)
            
            return TaskResponse(
                task_id=task.task_id,
                status="success",
                result={
                    "summary": {
                        "pii_found": pii_report['redacted'],
                        "pii_redacted_count": pii_report['instances_found'],
                        "policy_violations": policy_summary['total_violations'],
                        "suspicious_patterns": intent_report['total_findings'],
                        "critical_findings": intent_report['critical_findings']
                    }
                },
                error=None,
                processing_time_seconds=time.time() - start_time,
                metadata={
                    "agent": "guardrails_policy",
                    "deltas_processed": len(validated_deltas)
                }
            )
            
        except Exception as e:
            logger.exception(f"❌ Guardrails & Policy task processing failed: {e}")
            return TaskResponse(
                task_id=task.task_id,
                status="failure",
                result={},
                error=str(e),
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "guardrails_policy"}
            )

    # OBSOLETE: No longer needed since we run BEFORE Triaging (no LLM output exists yet)
    # def _combine_delta_data(self, llm_output: Dict[str, Any], context_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    #     """
    #     [OBSOLETE] Combine delta data from llm_output and context_bundle.
    #     This was used when Guardrails ran AFTER Triaging.
    #     Now we run BEFORE Triaging, so we work directly with context_bundle deltas.
    #     """
    #     pass

    def _scan_and_redact_pii(self, deltas: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scan deltas for PII and redact sensitive data.
        
        Args:
            deltas: List of combined deltas
            
        Returns:
            Tuple of (redacted_deltas, pii_report)
        """
        redacted_deltas = []
        pii_report = {
            'instances_found': 0,
            'types': set(),
            'redacted': False
        }
        
        for delta in deltas:
            # Redact delta using PIIRedactor
            redacted_delta = self.pii_redactor.redact_delta(delta)
            redacted_deltas.append(redacted_delta)
            
            # Track findings
            if redacted_delta.get('pii_redacted'):
                pii_report['instances_found'] += 1
                pii_report['types'].update(redacted_delta.get('pii_types', []))
        
        pii_report['redacted'] = pii_report['instances_found'] > 0
        pii_report['types'] = list(pii_report['types'])
        
        return redacted_deltas, pii_report

    def _scan_for_malicious_patterns(self, deltas: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scan deltas for malicious patterns using IntentGuard.
        
        Args:
            deltas: List of deltas (already PII redacted)
            
        Returns:
            Tuple of (scanned_deltas, intent_report)
        """
        scanned_deltas = []
        intent_report = {
            'suspicious_patterns': [],
            'total_findings': 0,
            'critical_findings': 0,
            'safe': True
        }
        
        for delta in deltas:
            # Scan delta using IntentGuard
            scanned_delta = self.intent_guard.scan_delta(delta)
            scanned_deltas.append(scanned_delta)
            
            # Track findings
            intent_guard_data = scanned_delta.get('intent_guard', {})
            if intent_guard_data.get('suspicious'):
                findings = intent_guard_data.get('patterns_detected', [])
                intent_report['suspicious_patterns'].extend(findings)
                intent_report['total_findings'] += len(findings)
                
                # Count critical findings
                critical = [f for f in findings if f.get('severity') == 'critical']
                intent_report['critical_findings'] += len(critical)
        
        intent_report['safe'] = intent_report['total_findings'] == 0
        
        return scanned_deltas, intent_report

    def _validate_policies(self, deltas: List[Dict[str, Any]], overview: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Validate deltas against policies.yaml.
        
        Args:
            deltas: List of deltas to validate
            overview: Overview metadata (for environment)
            
        Returns:
            Tuple of (validated_deltas, policy_summary)
        """
        # Load policies
        PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
        policies_path = PROJECT_ROOT / "shared" / "policies.yaml"
        
        policies = {}
        if policies_path.exists():
            try:
                with open(policies_path, 'r', encoding='utf-8') as f:
                    policies = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load policies.yaml: {e}")
        
        # Get environment
        environment = overview.get('environment', 'production')
        
        # Validate each delta
        validated_deltas = []
        policy_summary = {
            'total_violations': 0,
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }
        
        for delta in deltas:
            validated_delta = delta.copy()
            
            # Check if already has policy tag from drift analysis
            existing_policy = delta.get('policy', {})
            if isinstance(existing_policy, dict):
                policy_tag = existing_policy.get('tag', '')
                policy_rule = existing_policy.get('rule', '')
            else:
                policy_tag = ''
                policy_rule = ''
            
            # Apply policy validation
            policy_result = self._check_policy_rules(delta, policies, environment)
            
            # Update policy tag if violation found
            if policy_result['violation']:
                validated_delta['policy'] = {
                    'tag': 'invariant_breach',
                    'rule': policy_result['rule'],
                    'severity': policy_result['severity'],
                    'violation': True,
                    'reason': policy_result['reason']
                }
                
                # Update summary
                policy_summary['total_violations'] += 1
                severity = policy_result['severity']
                if severity == 'critical':
                    policy_summary['critical'] += 1
                elif severity == 'high':
                    policy_summary['high'] += 1
                elif severity == 'medium':
                    policy_summary['medium'] += 1
                else:
                    policy_summary['low'] += 1
            elif policy_tag == 'allowed_variance':
                # Keep existing allowed_variance tag
                validated_delta['policy'] = existing_policy
            elif not policy_tag:
                # No policy tag, mark as suspect
                validated_delta['policy'] = {
                    'tag': 'suspect',
                    'rule': None,
                    'severity': 'medium',
                    'violation': False,
                    'reason': 'Requires AI analysis'
                }
            else:
                # Keep existing policy tag
                validated_delta['policy'] = existing_policy
            
            validated_deltas.append(validated_delta)
        
        return validated_deltas, policy_summary

    def _check_policy_rules(self, delta: Dict[str, Any], policies: Dict[str, Any], environment: str) -> Dict[str, Any]:
        """
        Check a single delta against policy rules.
        
        Args:
            delta: Delta to check
            policies: Loaded policies.yaml content
            environment: Target environment
            
        Returns:
            Policy check result
        """
        locator = delta.get('locator', {})
        locator_value = str(locator.get('value', '')).lower()
        file = delta.get('file', '').lower()
        old_value = str(delta.get('old', '')).lower()
        new_value = str(delta.get('new', '')).lower()
        
        # Check invariants
        invariants = policies.get('invariants', [])
        for invariant in invariants:
            rule_name = invariant.get('name', '')
            locator_contains = invariant.get('locator_contains', '')
            forbid_values = invariant.get('forbid_values', [])
            require_values = invariant.get('require_values', [])
            
            # Check if locator matches
            if locator_contains and locator_contains.lower() not in locator_value:
                continue
            
            # Check forbidden values
            if forbid_values:
                for forbidden in forbid_values:
                    if forbidden.lower() in new_value:
                        return {
                            'violation': True,
                            'rule': rule_name,
                            'severity': invariant.get('severity', 'critical'),
                            'reason': f"Forbidden value detected: {forbidden}"
                        }
            
            # Check required values
            if require_values:
                for required in require_values:
                    if required.lower() not in new_value:
                        return {
                            'violation': True,
                            'rule': rule_name,
                            'severity': invariant.get('severity', 'critical'),
                            'reason': f"Required value missing: {required}"
                        }
        
        # Check environment allowlist
        env_allow_keys = policies.get('env_allow_keys', [])
        if any(allowed in file for allowed in env_allow_keys):
            return {
                'violation': False,
                'rule': None,
                'severity': None,
                'reason': 'Environment-specific file, allowed variance'
            }
        
        # No violation
        return {
            'violation': False,
            'rule': None,
            'severity': None,
            'reason': None
        }

    def _generate_validated_output(
        self,
        validated_deltas: List[Dict[str, Any]],
        pii_report: Dict[str, Any],
        intent_report: Dict[str, Any],
        policy_summary: Dict[str, Any],
        llm_summary: Dict[str, Any],
        overview: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate final validated output.
        
        Args:
            validated_deltas: Deltas with PII redacted, intent scanned, and policies validated
            pii_report: PII scanning report
            intent_report: Intent guard report
            policy_summary: Policy validation summary
            llm_summary: Summary from LLM output
            overview: Overview from context bundle
            
        Returns:
            Complete validated output structure
        """
        return {
            "meta": {
                "validated_at": datetime.now().isoformat() + "Z",
                "pii_found": pii_report['redacted'],
                "pii_redacted_count": pii_report['instances_found'],
                "policy_violations": policy_summary['total_violations'],
                "suspicious_patterns": intent_report['total_findings'],
                "environment": overview.get('environment', 'prod')
            },
            "validated_deltas": validated_deltas,
            "pii_report": pii_report,
            "intent_report": intent_report,
            "policy_summary": policy_summary,
            "llm_summary": llm_summary,
            "overview": overview
        }

    # Tool methods for LLM agent use
    
    # OBSOLETE: No longer needed since we run BEFORE Triaging
    # @tool
    # def load_llm_output(self, run_id: str) -> Dict[str, Any]:
    #     """[OBSOLETE] Load LLM output from database - not available when we run before Triaging"""
    #     pass
    
    @tool
    def load_context_bundle(self, run_id: str) -> Dict[str, Any]:
        """Load context bundle from database"""
        try:
            from shared.db import get_latest_context_bundle
            context_bundle = get_latest_context_bundle(run_id)
            
            if not context_bundle:
                return {"status": "error", "error": f"Context bundle not found for run: {run_id}"}
            
            return {"status": "success", "context_bundle": context_bundle}
        except Exception as e:
            logger.error(f"Failed to load context bundle from database: {e}")
            return {"status": "error", "error": str(e)}

    # OBSOLETE: No longer needed since we run BEFORE Triaging
    # @tool
    # def combine_delta_data(self, llm_output: Dict[str, Any], context_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    #     """[OBSOLETE] Combine delta data from both sources - not needed when we run before Triaging"""
    #     pass

    @tool
    def scan_for_pii(self, deltas: list) -> Dict[str, Any]:
        """Scan deltas for PII and secrets"""
        _, pii_report = self._scan_and_redact_pii(deltas)
        return pii_report

    @tool
    def redact_sensitive_data(self, deltas: list) -> List[Dict[str, Any]]:
        """Redact PII from deltas"""
        redacted, _ = self._scan_and_redact_pii(deltas)
        return redacted

    @tool
    def scan_for_malicious_patterns(self, deltas: list) -> Dict[str, Any]:
        """Scan for malicious patterns (intent guard)"""
        _, intent_report = self._scan_for_malicious_patterns(deltas)
        return intent_report

    @tool
    def validate_policies(self, deltas: list, policies_path: str) -> List[Dict[str, Any]]:
        """Validate deltas against policies.yaml"""
        overview = {}
        validated, _ = self._validate_policies(deltas, overview)
        return validated

    @tool
    def apply_policy_tags(self, deltas: list) -> List[Dict[str, Any]]:
        """Apply policy tags (invariant_breach, allowed_variance, suspect)"""
        # Policy tags are applied during validation
        return deltas

    @tool
    def generate_validated_output(self, validated_deltas: list, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Generate policy_validated_deltas.json output"""
        # This is a simplified version for tool use
        return {
            "validated_deltas": validated_deltas,
            "meta": metadata
        }
