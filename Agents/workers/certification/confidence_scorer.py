"""
Confidence Scorer - Calculate 0-100 Confidence Scores

Calculates confidence scores for auto-merge decisions based on
policy violations, risk levels, evidence, and environment.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScore:
    """Confidence score result"""
    score: int  # 0-100
    components: Dict[str, int]  # Breakdown by component
    decision: str  # AUTO_MERGE, HUMAN_REVIEW, BLOCK_MERGE
    explanation: str  # Why this score?
    confidence_level: str  # HIGH, MEDIUM, LOW


class ConfidenceScorer:
    """
    INTELLIGENT & DYNAMIC Confidence Scorer - AI Agent Decision System
    
    Combines DETERMINISTIC BRAIN (Rules) + LLM BRAIN (Context/Reasoning)
    
    Scoring Formula (inspired by PTG Adapter example):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Baseline:                             100 points (full confidence)
    
    DETERMINISTIC DEDUCTIONS (Rules Brain):
    - Critical risk/violations:           -60 to -80 (hard block)
    - High risk/violations:               -40 to -60 (service mismatch, etc)
    - Medium risk/violations:             -30 to -55 (behavioral changes)
    - Policy violations:                  -5 to -30 per violation
    
    IMPACT PENALTY (Blast Radius - LLM Brain):
    - High blast radius (5+ files):       -25 (magnitude penalty)
    - Medium blast radius (2-4 files):    -15
    - Low blast radius (1 file):          -5
    
    HISTORY SCORE (Learning from Past - LLM Brain):
    - Past outages in this area:          -10 to -20 (distrust)
    - Clean history:                      +5 to +10 (trust bonus)
    
    LLM SAFETY PROBABILITY (Contextual Reasoning):
    - LLM infers likely typo/error:       -10 to -20 (low safety)
    - LLM sees valid pattern:             +5 to +15 (high safety)
    - Unknown service IDs:                -15 (anomaly detected)
    
    CONTEXT BONUS (MR Quality):
    - MR tags present ([rename], etc):    +5
    - Jira ticket linked:                 +5
    - Rollback plan documented:           +10
    - No context/documentation:           0
    
    Final Score = Baseline + Deductions + Bonuses (0-100)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    Example (PTG Adapter):
    100 - 40(service mismatch) - 25(magnitude) - 5(history) + 4(LLM) + 0(context) = 34 BLOCK
    """
    
    def __init__(self):
        """Initialize confidence scorer"""
        pass
    
    def calculate(
        self,
        policy_violations: List[Dict[str, Any]],
        risk_level: str,
        evidence: Optional[Dict[str, Any]] = None,
        environment: str = "production",
        historical_pattern: Optional[Dict[str, Any]] = None,
        high_risk_count: int = 0,
        medium_risk_count: int = 0,
        low_risk_count: int = 0,
        # NEW: LLM Brain parameters for intelligent scoring
        blast_radius: Optional[Dict[str, Any]] = None,
        llm_reasoning: Optional[Dict[str, Any]] = None,
        mr_context: Optional[Dict[str, Any]] = None
    ) -> ConfidenceScore:
        """
        Calculate confidence score.
        
        Args:
            policy_violations: List of policy violations
            risk_level: Overall risk level (critical, high, medium, low, none)
            evidence: Evidence data (found, missing)
            environment: Target environment
            historical_pattern: Historical approval patterns
            
        Returns:
            ConfidenceScore object
        """
        # Start with base score (Baseline = 100, full confidence)
        score = 100
        components = {
            "base_score": 100,
            "policy_deductions": 0,
            "risk_deductions": 0,
            "blast_radius_penalty": 0,      # NEW: Impact magnitude
            "history_adjustment": 0,         # NEW: Past behavior
            "llm_safety_adjustment": 0,      # NEW: LLM reasoning
            "context_bonus": 0,              # NEW: MR quality
            "evidence_adjustments": 0,
            "historical_bonus": 0
        }
        
        # Apply policy violation deductions
        policy_deduction = self._calculate_policy_deductions(policy_violations)
        score -= policy_deduction
        components["policy_deductions"] = -policy_deduction
        
        # Apply risk level deductions
        # Use actual counts if provided (more accurate than overall risk level)
        # Check for critical risk level first (from risk_level string)
        critical_count = 1 if risk_level.lower() == 'critical' and (high_risk_count == 0 and medium_risk_count == 0 and low_risk_count == 0) else 0
        
        if high_risk_count > 0 or medium_risk_count > 0 or low_risk_count > 0 or critical_count > 0:
            risk_deduction = self._calculate_risk_deduction_from_counts(
                high_risk_count, medium_risk_count, low_risk_count, critical_count
            )
        else:
            # Fallback to overall risk level if counts not available
            risk_deduction = self._calculate_risk_deduction(risk_level)
        score -= risk_deduction
        components["risk_deductions"] = -risk_deduction
        
        # Apply evidence adjustments
        if evidence:
            evidence_adjustment = self._calculate_evidence_adjustment(evidence)
            score += evidence_adjustment
            components["evidence_adjustments"] = evidence_adjustment
        
        # Apply historical pattern bonus (OLD - kept for compatibility)
        if historical_pattern:
            historical_bonus = self._calculate_historical_bonus(historical_pattern)
            score += historical_bonus
            components["historical_bonus"] = historical_bonus
        
        # ============================================================================
        # NEW: INTELLIGENT LLM BRAIN SCORING
        # ============================================================================
        
        # Apply blast radius penalty (Impact Magnitude)
        if blast_radius:
            blast_penalty = self._calculate_blast_radius_penalty(blast_radius)
            score -= blast_penalty
            components["blast_radius_penalty"] = -blast_penalty
        
        # Apply history-based adjustment (Learning from Past)
        if llm_reasoning and llm_reasoning.get('historical_analysis'):
            history_adjustment = self._calculate_history_adjustment(
                llm_reasoning.get('historical_analysis', {})
            )
            score += history_adjustment
            components["history_adjustment"] = history_adjustment
        
        # Apply LLM safety probability (Contextual Reasoning)
        if llm_reasoning and llm_reasoning.get('safety_probability'):
            llm_adjustment = self._calculate_llm_safety_adjustment(
                llm_reasoning.get('safety_probability', 0.5),
                llm_reasoning.get('anomaly_score', 0.0)
            )
            score += llm_adjustment
            components["llm_safety_adjustment"] = llm_adjustment
        
        # Apply context bonus (MR Quality)
        if mr_context:
            context_bonus = self._calculate_context_bonus(mr_context)
            score += context_bonus
            components["context_bonus"] = context_bonus
        
        # Apply environment modifier
        score = self._apply_environment_modifier(score, environment)
        
        # Ensure score is in 0-100 range
        score = max(0, min(100, score))
        
        # Determine decision (pass risk counts to enforce BLOCK on medium+)
        decision = self._determine_decision(score, environment, high_risk_count, medium_risk_count, critical_count)
        
        # Generate explanation (include risk counts for context)
        explanation = self._generate_explanation(score, components, decision, environment, high_risk_count, medium_risk_count, critical_count)
        
        # Determine confidence level
        confidence_level = self._determine_confidence_level(score)
        
        return ConfidenceScore(
            score=score,
            components=components,
            decision=decision,
            explanation=explanation,
            confidence_level=confidence_level
        )
    
    def _calculate_policy_deductions(self, violations: List[Dict[str, Any]]) -> int:
        """Calculate deductions for policy violations"""
        deduction = 0
        
        for violation in violations:
            severity = violation.get('severity', 'medium').lower()
            if severity == 'critical':
                deduction += 30
            elif severity == 'high':
                deduction += 15
            elif severity == 'medium':
                deduction += 5
        
        return deduction
    
    def _calculate_risk_deduction(self, risk_level: str) -> int:
        """
        RIGOROUS SCORING: Calculate deduction for risk level (fallback when counts not available).
        
        CRITICAL RULE: Any medium/high/critical → score MUST be < 50
        """
        risk_deductions = {
            'critical': 80,  # Score < 50
            'high': 60,      # Score < 50
            'medium': 55,    # Score < 50 (even 1 medium = BLOCK)
            'low': 0,        # Can still score > 50
            'none': 0        # Can score 100
        }
        return risk_deductions.get(risk_level.lower(), 55)  # Default to medium if unknown
    
    def _calculate_risk_deduction_from_counts(self, high_count: int, medium_count: int, low_count: int, critical_count: int = 0) -> int:
        """
        RIGOROUS SCORING: Calculate risk deduction based on actual counts of risk items.
        
        CRITICAL RULE: Any medium/high/critical drift → score MUST be < 50
        - Critical risk: -80 points (ensures score < 50 even with base 100)
        - High risk: -60 points (ensures score < 50)
        - Medium risk: -55 points (ensures score < 50, even 1 medium = BLOCK)
        - Low risk: -1 per item (can still score > 50 if few items)
        
        Only low/allowed_variance drifts can score above 50, based on quantity.
        """
        deduction = 0
        
        # CRITICAL: Any critical/high/medium = instant BLOCK (score < 50)
        if critical_count > 0:
            # Critical risk: Score must be < 50
            deduction = 80  # Even with base 100, score = 20 (well below 50)
        
        elif high_count > 0:
            # High risk: Score must be < 50
            deduction = 60  # Even with base 100, score = 40 (below 50)
        
        elif medium_count > 0:
            # Medium risk: Score must be < 50 (EVEN 1 MEDIUM = BLOCK)
            deduction = 55  # Even with base 100, score = 45 (below 50)
        
        else:
            # Only low risk items: Deduct based on quantity (can still score > 50)
            if low_count > 0:
                # Low risk: -2 per item (more penalty than before)
                # With 10 low items: -20 → score = 80 (still > 50)
                # With 25 low items: -50 → score = 50 (exactly 50)
                # With 30+ low items: score < 50
                low_deduction = low_count * 2
                deduction = min(low_deduction, 60)  # Cap at -60 to allow some flexibility
        
        return deduction
    
    def _calculate_evidence_adjustment(self, evidence: Dict[str, Any]) -> int:
        """Calculate adjustment based on evidence"""
        adjustment = 0
        
        found = evidence.get('found', [])
        missing = evidence.get('missing', [])
        
        # Bonus if all evidence present
        if found and not missing:
            adjustment += 20
        # Penalty if evidence missing
        elif missing:
            adjustment -= 20
        
        return adjustment
    
    def _calculate_historical_bonus(self, pattern: Dict[str, Any]) -> int:
        """Calculate bonus for historical approval pattern"""
        # TODO: Implement historical pattern analysis
        return 0
    
    # ============================================================================
    # INTELLIGENT LLM BRAIN SCORING METHODS
    # ============================================================================
    
    def _calculate_blast_radius_penalty(self, blast_radius: Dict[str, Any]) -> int:
        """
        Calculate Impact Magnitude Penalty based on blast radius.
        
        Inspired by PTG Adapter example: "5 drifted references in a critical adapter YAML 
        (single change fan-out, high blast radius)" → -25 points
        
        Args:
            blast_radius: {
                'files_affected': int,
                'critical_files': int,
                'downstream_services': List[str],
                'scope': 'low' | 'medium' | 'high'
            }
        """
        files_affected = blast_radius.get('files_affected', 1)
        critical_files = blast_radius.get('critical_files', 0)
        downstream_services = blast_radius.get('downstream_services', [])
        scope = blast_radius.get('scope', 'low').lower()
        
        penalty = 0
        
        # Base penalty from scope
        scope_penalties = {
            'critical': 30,  # Critical infrastructure changes
            'high': 25,      # High fan-out (PTG example)
            'medium': 15,    # Moderate impact
            'low': 5         # Limited scope
        }
        penalty += scope_penalties.get(scope, 15)
        
        # Additional penalty for multiple files
        if files_affected > 5:
            penalty += 10
        elif files_affected > 3:
            penalty += 5
        
        # Additional penalty for critical files (auth, database, etc)
        if critical_files > 0:
            penalty += critical_files * 5
        
        # Additional penalty for downstream service dependencies
        if downstream_services:
            penalty += min(len(downstream_services) * 3, 15)
        
        return min(penalty, 50)  # Cap at 50
    
    def _calculate_history_adjustment(self, historical_analysis: Dict[str, Any]) -> int:
        """
        Calculate History Score adjustment based on past behavior in this area.
        
        Inspired by PTG Adapter: "Prior alias/route typo caused outage in this area 
        — slight distrust" → -5 points
        
        Args:
            historical_analysis: {
                'past_failures': int,
                'past_successes': int,
                'outage_history': bool,
                'similar_changes': List[Dict],
                'trust_level': float  # 0.0 to 1.0
            }
        """
        past_failures = historical_analysis.get('past_failures', 0)
        past_successes = historical_analysis.get('past_successes', 0)
        outage_history = historical_analysis.get('outage_history', False)
        trust_level = historical_analysis.get('trust_level', 0.5)
        
        adjustment = 0
        
        # Penalty for past failures
        if outage_history:
            adjustment -= 20  # Significant distrust if past outages
        elif past_failures > 0:
            adjustment -= min(past_failures * 5, 15)  # -5 per failure, max -15
        
        # Bonus for clean history
        if past_successes > 5 and past_failures == 0:
            adjustment += 10  # Trust bonus for clean track record
        elif past_successes > 0:
            adjustment += min(past_successes * 2, 5)
        
        # Trust level adjustment (-10 to +10)
        if trust_level < 0.3:
            adjustment -= 10  # Low trust
        elif trust_level > 0.8:
            adjustment += 10  # High trust
        
        return max(-20, min(adjustment, 10))  # Range: -20 to +10
    
    def _calculate_llm_safety_adjustment(self, safety_probability: float, anomaly_score: float) -> int:
        """
        Calculate LLM Safety Probability adjustment from contextual reasoning.
        
        Inspired by PTG Adapter: "LLM sees ptg-sqa3 used many times, 08v-beta2 never; 
        infers likely typo — very low safety" → +4 points (scaled)
        
        Args:
            safety_probability: 0.0 to 1.0 (LLM's confidence this change is safe)
            anomaly_score: 0.0 to 1.0 (LLM's detection of anomalous patterns)
        """
        adjustment = 0
        
        # Penalty for low safety probability (likely typo/error)
        if safety_probability < 0.3:
            # Very unsafe: -20 points
            adjustment -= 20
        elif safety_probability < 0.5:
            # Somewhat unsafe: -10 points
            adjustment -= 10
        elif safety_probability > 0.8:
            # Very safe: +15 points
            adjustment += 15
        elif safety_probability > 0.6:
            # Somewhat safe: +5 points
            adjustment += 5
        
        # Additional penalty for anomalies (unknown service IDs, etc)
        if anomaly_score > 0.7:
            adjustment -= 15  # High anomaly detected
        elif anomaly_score > 0.5:
            adjustment -= 10  # Moderate anomaly
        elif anomaly_score > 0.3:
            adjustment -= 5   # Low anomaly
        
        return max(-20, min(adjustment, 15))  # Range: -20 to +15
    
    def _calculate_context_bonus(self, mr_context: Dict[str, Any]) -> int:
        """
        Calculate Context Bonus based on MR quality and documentation.
        
        Inspired by PTG Adapter: "No MR tag like [rename-adapter], no Jira rename plan, 
        no rollback note" → 0 points
        
        Args:
            mr_context: {
                'has_mr_tags': bool,
                'has_jira_link': bool,
                'has_rollback_plan': bool,
                'has_test_evidence': bool,
                'description_quality': 'high' | 'medium' | 'low'
            }
        """
        bonus = 0
        
        # MR tags present ([rename], [feature], etc)
        if mr_context.get('has_mr_tags'):
            bonus += 5
        
        # Jira ticket linked
        if mr_context.get('has_jira_link'):
            bonus += 5
        
        # Rollback plan documented
        if mr_context.get('has_rollback_plan'):
            bonus += 10
        
        # Test evidence provided
        if mr_context.get('has_test_evidence'):
            bonus += 5
        
        # Description quality
        desc_quality = mr_context.get('description_quality', 'low').lower()
        if desc_quality == 'high':
            bonus += 5
        elif desc_quality == 'medium':
            bonus += 2
        
        return min(bonus, 25)  # Cap at 25
    
    def _apply_environment_modifier(self, score: int, environment: str) -> int:
        """Apply environment-specific modifier"""
        # Production is stricter - no modifier needed (already strict)
        # Staging/Dev could be more lenient, but we'll keep it strict for now
        return score
    
    def _determine_decision(self, score: int, environment: str, high_risk_count: int = 0, medium_risk_count: int = 0, critical_count: int = 0) -> str:
        """
        RIGOROUS DECISION: Determine certification decision based on score and risk levels.
        
        CRITICAL RULE: Medium/High/Critical risk → ALWAYS BLOCK (regardless of score)
        Only low/allowed_variance can proceed based on score.
        """
        # CRITICAL: Any medium/high/critical risk → IMMEDIATE BLOCK
        if critical_count > 0 or high_risk_count > 0 or medium_risk_count > 0:
            return "BLOCK_MERGE"
        
        # Only low/allowed_variance items: Use score-based decision
        if environment == "production":
            if score >= 85:
                return "AUTO_MERGE"
            elif score >= 60:
                return "HUMAN_REVIEW"
            else:
                return "BLOCK_MERGE"
        elif environment in ["staging", "pre-production"]:
            if score >= 75:
                return "AUTO_MERGE"
            elif score >= 50:
                return "HUMAN_REVIEW"
            else:
                return "BLOCK_MERGE"
        else:  # development, testing
            if score >= 65:
                return "AUTO_MERGE"
            elif score >= 50:  # Stricter: require 50+ even in dev
                return "HUMAN_REVIEW"
            else:
                return "BLOCK_MERGE"
    
    def _generate_explanation(
        self,
        score: int,
        components: Dict[str, int],
        decision: str,
        environment: str,
        high_risk_count: int = 0,
        medium_risk_count: int = 0,
        critical_count: int = 0
    ) -> str:
        """Generate human-readable explanation with rigorous scoring details"""
        parts = [f"Confidence score: {score}/100"]
        
        # Explain blocking conditions first
        if critical_count > 0 or high_risk_count > 0 or medium_risk_count > 0:
            blocking_reasons = []
            if critical_count > 0:
                blocking_reasons.append(f"{critical_count} critical risk item(s)")
            if high_risk_count > 0:
                blocking_reasons.append(f"{high_risk_count} high risk item(s)")
            if medium_risk_count > 0:
                blocking_reasons.append(f"{medium_risk_count} medium risk item(s)")
            parts.append(f"🚫 BLOCKED: {', '.join(blocking_reasons)} detected (rigorous policy: medium+ = BLOCK)")
        
        if components["policy_deductions"] < 0:
            parts.append(f"Policy violations: -{abs(components['policy_deductions'])} points")
        
        if components["risk_deductions"] < 0:
            parts.append(f"Risk deductions: -{abs(components['risk_deductions'])} points")
            if critical_count > 0 or high_risk_count > 0 or medium_risk_count > 0:
                parts.append("(Rigorous scoring: medium/high/critical = score < 50)")
        
        if components["evidence_adjustments"] > 0:
            parts.append(f"Evidence complete: +{components['evidence_adjustments']} points")
        elif components["evidence_adjustments"] < 0:
            parts.append(f"Missing evidence: {components['evidence_adjustments']} points")
        
        parts.append(f"Decision: {decision}")
        if decision == "BLOCK_MERGE" and (critical_count > 0 or high_risk_count > 0 or medium_risk_count > 0):
            parts.append("(Pipeline blocked due to medium/high/critical risk items)")
        
        return ". ".join(parts)
    
    def _get_threshold(self, environment: str) -> int:
        """Get threshold for environment"""
        thresholds = {
            "production": 85,
            "staging": 75,
            "pre-production": 75,
            "development": 65,
            "dev": 65,
            "testing": 65
        }
        return thresholds.get(environment.lower(), 75)
    
    def _determine_confidence_level(self, score: int) -> str:
        """Determine confidence level"""
        if score >= 80:
            return "HIGH"
        elif score >= 60:
            return "MEDIUM"
        else:
            return "LOW"

