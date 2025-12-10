"""
Drift Detector Agent - Configuration Drift Detection

This agent performs precision drift analysis using drift.py.

Responsibilities:
- Context parsing (parse YAML/JSON/properties files)
- Compare algorithms (structural diff, semantic diff)
- Diff generation (line-by-line deltas with exact locators)
- Delta deduplication and clustering

Input: Repository snapshots from Config Collector
Output: context_bundle.json with structured deltas
"""

from .drift_detector_agent import DriftDetectorAgent

__all__ = ['DriftDetectorAgent']

