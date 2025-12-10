"""
Triaging-Routing Agent - AI-Powered Delta Analysis

This agent uses LLM to analyze and categorize configuration deltas.

Responsibilities:
- LLM-based analysis of configuration changes
- Hard fail detection (critical violations)
- Risk categorization (HIGH/MEDIUM/LOW)
- Initial triage and routing decisions

Input: context_bundle.json from Drift Detector
Output: triaged_deltas.json with AI insights and risk levels
"""

from .triaging_routing_agent import TriagingRoutingAgent

__all__ = ['TriagingRoutingAgent']

