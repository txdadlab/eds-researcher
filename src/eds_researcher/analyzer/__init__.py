"""Grok-powered analysis: extraction, scoring, and lead generation."""

from .extractor import ExtractionResult, Extractor
from .grok_client import GrokClient
from .lead_generator import LeadGenerator
from .scorer import aggregate_treatment_tier, is_trending, score_evidence_tier

__all__ = [
    "ExtractionResult",
    "Extractor",
    "GrokClient",
    "LeadGenerator",
    "aggregate_treatment_tier",
    "is_trending",
    "score_evidence_tier",
]
