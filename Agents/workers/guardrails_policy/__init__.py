"""
Guardrails & Policy Engine Agent - Security & Compliance

This agent enforces security guardrails and organizational policies.

**CRITICAL: This agent MUST run BEFORE Triaging to redact PII before LLM sees the data.**

Responsibilities:
- PII redaction (detect and scrub sensitive data)
- Intent guard (detect malicious patterns)
- Policy validation (enforce policies.yaml rules)
- Compliance checking

Input: context_bundle from Drift Detector Agent (via database)
Output: policy_validated_deltas with sanitized, compliant data (saved to database)
"""

from .guardrails_policy_agent import GuardrailsPolicyAgent

__all__ = ['GuardrailsPolicyAgent']

