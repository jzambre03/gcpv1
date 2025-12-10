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
    Calculate confidence scores for certification decisions.
    
    Scoring Components (100 points total):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Base Score:                           100 points
    
    Deductions:
    - Critical policy violations:         -30 each
    - High severity violations:           -15 each
    - Medium severity violations:         -5 each
    - Risk level (critical):              -40
    - Risk level (high):                  -25
    - Risk level (medium):                -10
    - Missing evidence:                   -20
    - Incomplete testing:                 -10
    
    Bonuses:
    - All evidence present:               +20
    - Historical approval pattern:        +10
    - Automated test pass:                +10
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        historical_pattern: Optional[Dict[str, Any]] = None
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
        # Start with base score
        score = 100
        components = {
            "base_score": 100,
            "policy_deductions": 0,
            "risk_deductions": 0,
            "evidence_adjustments": 0,
            "historical_bonus": 0
        }
        
        # Apply policy violation deductions
        policy_deduction = self._calculate_policy_deductions(policy_violations)
        score -= policy_deduction
        components["policy_deductions"] = -policy_deduction
        
        # Apply risk level deductions
        risk_deduction = self._calculate_risk_deduction(risk_level)
        score -= risk_deduction
        components["risk_deductions"] = -risk_deduction
        
        # Apply evidence adjustments
        if evidence:
            evidence_adjustment = self._calculate_evidence_adjustment(evidence)
            score += evidence_adjustment
            components["evidence_adjustments"] = evidence_adjustment
        
        # Apply historical pattern bonus
        if historical_pattern:
            historical_bonus = self._calculate_historical_bonus(historical_pattern)
            score += historical_bonus
            components["historical_bonus"] = historical_bonus
        
        # Apply environment modifier
        score = self._apply_environment_modifier(score, environment)
        
        # Ensure score is in 0-100 range
        score = max(0, min(100, score))
        
        # Determine decision
        decision = self._determine_decision(score, environment)
        
        # Generate explanation
        explanation = self._generate_explanation(score, components, decision, environment)
        
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
        """Calculate deduction for risk level"""
        risk_deductions = {
            'critical': 40,
            'high': 25,
            'medium': 10,
            'low': 0,
            'none': 0
        }
        return risk_deductions.get(risk_level.lower(), 10)
    
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
    
    def _apply_environment_modifier(self, score: int, environment: str) -> int:
        """Apply environment-specific modifier"""
        # Production is stricter - no modifier needed (already strict)
        # Staging/Dev could be more lenient, but we'll keep it strict for now
        return score
    
    def _determine_decision(self, score: int, environment: str) -> str:
        """Determine certification decision based on score and environment"""
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
            elif score >= 40:
                return "HUMAN_REVIEW"
            else:
                return "BLOCK_MERGE"
    
    def _generate_explanation(
        self,
        score: int,
        components: Dict[str, int],
        decision: str,
        environment: str
    ) -> str:
        """Generate human-readable explanation"""
        parts = [f"Confidence score: {score}/100"]
        
        if components["policy_deductions"] < 0:
            parts.append(f"Policy violations: -{abs(components['policy_deductions'])} points")
        
        if components["risk_deductions"] < 0:
            parts.append(f"Risk level: -{abs(components['risk_deductions'])} points")
        
        if components["evidence_adjustments"] > 0:
            parts.append(f"Evidence complete: +{components['evidence_adjustments']} points")
        elif components["evidence_adjustments"] < 0:
            parts.append(f"Missing evidence: {components['evidence_adjustments']} points")
        
        parts.append(f"Decision: {decision} (threshold for {environment}: {self._get_threshold(environment)})")
        
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

