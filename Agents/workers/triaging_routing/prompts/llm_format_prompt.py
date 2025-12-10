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

Return ONLY valid JSON with this EXACT structure. DO NOT add any extra fields.

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
      "why": "What changed and its impact",
      "remediation": {{
        "snippet": "corrected configuration value"
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
      "why": "What changed and why it matters",
      "remediation": {{
        "snippet": "corrected value"
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
      "rationale": "Why this change is acceptable"
    }}
  ]
}}
```

## CRITICAL FIELD REQUIREMENTS

### For **high**, **medium**, **low** items:
- **id**: Use exact delta ID from above
- **file**: Use "{file}"
- **locator**: Copy the exact locator structure from the delta
  - **type**: keypath, yamlpath, jsonpath, unidiff, coord, or path
  - **value**: Full path to the configuration key
  - **If type is "unidiff"**: Also include old_start, old_lines, new_start, new_lines from the delta
- **why**: Single sentence explaining what changed and its impact
- **remediation**: Object with "snippet" field containing corrected value

### For **allowed_variance** items:
- **id**: Use exact delta ID from above
- **file**: Use "{file}"
- **locator**: Same as above
- **rationale**: Single sentence explaining why this variance is acceptable

## DO NOT INCLUDE

DO NOT add these fields (they are NOT in the desired format):
- old, new
- drift_category
- risk_level
- risk_reason
- ai_review_assistant
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
5. **Write clear "why"** or "rationale" explaining the change
6. **Provide remediation snippet** for high/medium/low items
7. **Return ONLY JSON** - no markdown, no explanations, just the JSON object

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
            
            # Required fields for high/medium/low
            if not all(field in item for field in ["id", "file", "locator", "why", "remediation"]):
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
    
    # Check allowed_variance items
    for item in output["allowed_variance"]:
        if not isinstance(item, dict):
            return False
        
        # Required fields for allowed_variance
        if not all(field in item for field in ["id", "file", "locator", "rationale"]):
            return False
        
        # locator must have type and value
        if not isinstance(item["locator"], dict):
            return False
        if "type" not in item["locator"] or "value" not in item["locator"]:
            return False
    
    return True





