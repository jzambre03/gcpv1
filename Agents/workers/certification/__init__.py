"""
Certification Engine Agent - Final Decision Maker

This agent makes the final certification decision based on all analysis.

Responsibilities:
- Calculate confidence score (0-100)
- Make certification decision (AUTO_MERGE/HUMAN_REVIEW/BLOCK_MERGE)
- Create certified snapshots
- Generate approval/rejection reports

Input: policy_validated_deltas.json from Guardrails & Policy Engine
Output: certification_result.json with final decision and score
"""

from .certification_engine_agent import CertificationEngineAgent

__all__ = ['CertificationEngineAgent']

