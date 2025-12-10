"""
Guardrails & Policy Engine Agent - Security & Compliance

This agent enforces security guardrails and organizational policies.

Responsibilities:
- PII redaction (detect and scrub sensitive data)
- Intent guard (detect malicious patterns)
- Policy validation (enforce policies.yaml rules)
- Compliance checking

Input: triaged_deltas.json from Triaging-Routing Agent
Output: policy_validated_deltas.json with sanitized, compliant data
"""

from .guardrails_policy_agent import GuardrailsPolicyAgent

__all__ = ['GuardrailsPolicyAgent']

