"""
Triaging Prompt Templates

LLM prompts for analyzing configuration deltas and assigning risk levels.
"""

import json


def build_triaging_prompt(deltas: list, environment: str = "production") -> str:
    """
    Build prompt for LLM to analyze configuration deltas.
    
    Args:
        deltas: List of deltas to analyze
        environment: Target environment (prod, staging, dev)
        
    Returns:
        Formatted prompt string
    """
    # TODO: Implement prompt building
    # This will be extracted from current diff_engine_agent.py prompts
    
    prompt = f"""Analyze the following configuration deltas for {environment} environment.

Deltas to analyze:
{json.dumps(deltas, indent=2)}

For each delta, provide:
1. Risk level (HIGH/MEDIUM/LOW/ALLOWED)
2. Verdict (NO_DRIFT/NEW_BUILD_OK/DRIFT_WARN/DRIFT_BLOCKING)
3. Explanation of the change
4. Impact assessment
5. Hard fail flag (true if critical violation)

Return JSON format matching the expected schema.
"""
    return prompt


def build_hard_fail_detection_prompt(deltas: list) -> str:
    """Build prompt specifically for hard fail detection"""
    # TODO: Implement
    return ""


def build_risk_categorization_prompt(deltas: list) -> str:
    """Build prompt for risk level categorization"""
    # TODO: Implement
    return ""

