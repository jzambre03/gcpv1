"""
LLM Format Prompt Template - EXACT MATCH to LLM_output.json

This module provides prompt templates that match the exact format
specified in UI/LLM_output.json with no extra fields.
"""

from typing import List, Dict, Any


def build_llm_format_prompt(
    file: str,
    deltas: List[Dict[str, Any]],
    environment: str = "production",
    policies: Dict[str, Any] = None
) -> str:
    """
    Build an AI prompt that returns LLM output format matching LLM_output.json EXACTLY.
    
    Args:
        file: File path being analyzed
        deltas: List of delta objects from context_bundle
        environment: Target environment (production, staging, dev, qa)
        policies: Policy rules and guidelines
    
    Returns:
        Complete prompt string for AI analysis
    
    Output Format (EXACT):
        {
          "high": [{id, file, locator, why, remediation}],
          "medium": [{id, file, locator, why, remediation}],
          "low": [{id, file, locator, why, remediation}],
          "allowed_variance": [{id, file, locator, rationale}]
        }
    """
    if policies is None:
        policies = {}
    
    # Build deltas summary
    deltas_summary = []
    for idx, delta in enumerate(deltas, 1):
        locator = delta.get('locator', {})
        deltas_summary.append({
            "index": idx,
            "delta_id": delta.get('id', 'unknown'),
            "locator_type": locator.get('type', 'unknown'),
            "locator_value": locator.get('value', 'unknown'),
            "locator_extra": {k: v for k, v in locator.items() if k not in ['type', 'value']},
            "old_value": str(delta.get('old')) if delta.get('old') is not None else "null",
            "new_value": str(delta.get('new')) if delta.get('new') is not None else "null",
            "policy_tag": delta.get('policy', {}).get('tag', 'unknown') if isinstance(delta.get('policy'), dict) else 'unknown',
            "category": delta.get('category', 'unknown')
        })
    
    # Build the prompt
    prompt = f"""You are a configuration drift adjudicator analyzing file "{file}" for environment "{environment}".

Your task is to categorize ALL {len(deltas)} configuration changes into risk buckets.

## CHANGES TO ANALYZE

"""
    
    # Add each delta
    for d in deltas_summary:
        prompt += f"""
### CHANGE #{d['index']}
- **ID**: `{d['delta_id']}`
- **Category**: {d['category']}
- **Location**: {d['locator_type']}: `{d['locator_value']}`
- **Old Value**: `{d['old_value']}`
- **New Value**: `{d['new_value']}`
- **Policy Tag**: {d['policy_tag']}

"""

    # Add output format specification - EXACT MATCH
    prompt += f"""
## OUTPUT FORMAT

Return ONLY valid JSON with this EXACT structure. Include ALL required fields.

```json
{{
  "high": [
    {{
      "id": "delta_id_from_above",
      "file": "{file}",
      "locator": {{
        "type": "keypath",
        "value": "full.path.to.key"
      }},
      "old": "previous value from the delta",
      "new": "new value from the delta",
      "why": "What changed and its impact",
      "remediation": {{
        "snippet": "corrected configuration value"
      }},
      "ai_review_assistant": {{
        "potential_risk": "Detailed 2-3 sentence explanation of what could go wrong and business impact",
        "suggested_action": "Numbered actionable steps: 1. First step, 2. Second step, 3. Third step, 4. Fourth step"
      }}
    }}
  ],
  "medium": [
    {{
      "id": "delta_id_from_above",
      "file": "{file}",
      "locator": {{
        "type": "keypath",
        "value": "full.path.to.key"
      }},
      "old": "previous value",
      "new": "new value",
      "why": "What changed and why it matters",
      "remediation": {{
        "snippet": "corrected value"
      }},
      "ai_review_assistant": {{
        "potential_risk": "Detailed explanation of potential issues and their impact on the system",
        "suggested_action": "Numbered steps: 1. Verify change, 2. Test thoroughly, 3. Monitor deployment, 4. Have rollback ready"
      }}
    }}
  ],
  "low": [],
  "allowed_variance": [
    {{
      "id": "delta_id_from_above",
      "file": "{file}",
      "locator": {{
        "type": "keypath",
        "value": "full.path.to.key"
      }},
      "old": "previous value",
      "new": "new value",
      "rationale": "Why this change is acceptable"
    }}
  ]
}}
```

## CRITICAL FIELD REQUIREMENTS

### For **high**, **medium**, **low** items (ALL REQUIRED):
- **id**: Use exact delta ID from above
- **file**: Use "{file}"
- **locator**: Copy the exact locator structure from the delta
  - **type**: keypath, yamlpath, jsonpath, unidiff, coord, or path
  - **value**: Full path to the configuration key
  - **If type is "unidiff"**: Also include old_start, old_lines, new_start, new_lines from the delta
- **old**: REQUIRED - Previous value from the delta (use Old Value from above)
- **new**: REQUIRED - New value from the delta (use New Value from above)
- **why**: Single sentence explaining what changed and its impact
- **remediation**: Object with "snippet" field containing corrected value
- **ai_review_assistant**: REQUIRED - Detailed analysis object with:
  - **potential_risk**: 2-3 sentences explaining what could go wrong, business impact, and affected systems
  - **suggested_action**: Numbered actionable steps (minimum 3-4 steps) for verification and mitigation

### For **allowed_variance** items:
- **id**: Use exact delta ID from above
- **file**: Use "{file}"
- **locator**: Same as above
- **old**: Previous value
- **new**: New value
- **rationale**: Single sentence explaining why this variance is acceptable

## DO NOT INCLUDE

DO NOT add these fields (they are NOT in the desired format):
- drift_category
- risk_level
- risk_reason
- why_allowed (use "rationale" instead)
- remediation.steps
- remediation.patch_hint (optional, only if you have full git diff)

## CATEGORIZATION GUIDELINES

### **high** (Critical - Database/Security):
- Database credentials changed (usernames, passwords, connection strings)
- Security features disabled
- Production endpoints modified
- Authentication/authorization changes
- Policy violations (invariant_breach)

### **medium** (Important - Configuration/Dependencies):
- Network configuration changes
- Dependency version changes
- Feature behavior modifications
- Performance settings adjusted

### **low** (Minor):
- Logging level changes
- Comment updates
- Minor tweaks

### **allowed_variance** (Acceptable):
- Environment-specific configuration (dev vs qa vs prod differences)
- Test suite configuration
- Build/CI pipeline settings
- Documentation changes
- Policy tag = "allowed_variance"

## ANALYSIS INSTRUCTIONS

1. **Analyze each delta** from the list above
2. **Categorize into ONE bucket**: high, medium, low, or allowed_variance
3. **Use exact delta IDs** from above
4. **Keep locator structure** from the delta (especially for unidiff types)
5. **Include "old" and "new" values** from the delta (copy from Old Value/New Value above)
6. **Write clear "why"** or "rationale" explaining the change
7. **Provide remediation snippet** for high/medium/low items
8. **Generate detailed ai_review_assistant** for high/medium/low items:
   - **potential_risk**: Write 2-3 sentences explaining:
     * What specific functionality could break
     * Which users/systems would be affected
     * The business impact (e.g., "customers unable to make payments", "service outages")
   - **suggested_action**: Write 4 numbered steps for verification and mitigation:
     * Step 1: Verification step (e.g., "Verify the new endpoint is correctly configured...")
     * Step 2: Testing step (e.g., "Test payment flows in a staging environment...")
     * Step 3: Monitoring step (e.g., "Monitor payment success rates after deployment...")
     * Step 4: Contingency step (e.g., "Have a rollback plan ready in case of issues")
9. **Return ONLY JSON** - no markdown, no explanations, just the JSON object

Begin analysis now.
"""
    
    return prompt


def validate_llm_output(output: dict) -> bool:
    """
    Validate LLM output matches the EXACT format from LLM_output.json.
    
    Args:
        output: Parsed JSON output from AI
    
    Returns:
        True if valid, False otherwise
    """
    # Check top-level structure
    required_keys = ["high", "medium", "low", "allowed_variance"]
    if not all(key in output for key in required_keys):
        return False
    
    # Check each bucket is a list
    for key in required_keys:
        if not isinstance(output[key], list):
            return False
    
    # Check items have required fields (minimal set)
    for bucket in ["high", "medium", "low"]:
        for item in output[bucket]:
            if not isinstance(item, dict):
                return False
            
            # Required fields for high/medium/low (including new fields)
            required_fields = ["id", "file", "locator", "old", "new", "why", "remediation", "ai_review_assistant"]
            if not all(field in item for field in required_fields):
                return False
            
            # locator must have type and value
            if not isinstance(item["locator"], dict):
                return False
            if "type" not in item["locator"] or "value" not in item["locator"]:
                return False
            
            # remediation must have snippet
            if not isinstance(item["remediation"], dict):
                return False
            if "snippet" not in item["remediation"]:
                return False
            
            # ai_review_assistant must have potential_risk and suggested_action
            if not isinstance(item["ai_review_assistant"], dict):
                return False
            if "potential_risk" not in item["ai_review_assistant"] or "suggested_action" not in item["ai_review_assistant"]:
                return False
    
    # Check allowed_variance items
    for item in output["allowed_variance"]:
        if not isinstance(item, dict):
            return False
        
        # Required fields for allowed_variance (including old/new)
        required_fields = ["id", "file", "locator", "old", "new", "rationale"]
        if not all(field in item for field in required_fields):
            return False
        
        # locator must have type and value
        if not isinstance(item["locator"], dict):
            return False
        if "type" not in item["locator"] or "value" not in item["locator"]:
            return False
    
    return True





