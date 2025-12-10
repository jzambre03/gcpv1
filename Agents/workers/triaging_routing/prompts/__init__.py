"""
Triaging-Routing Agent Prompts

LLM prompt templates for analyzing configuration deltas.
"""

from .triaging_prompt import build_triaging_prompt

__all__ = ['build_triaging_prompt']

