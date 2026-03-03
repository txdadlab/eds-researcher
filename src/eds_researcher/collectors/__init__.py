"""Data source collectors for EDS research."""

from .base import Collector
from .clinical_trials import ClinicalTrialsCollector
from .pubmed import PubMedCollector
from .reddit import RedditCollector
from .scholar import ScholarCollector
from .xai_search import XAISearchCollector

__all__ = [
    "Collector",
    "ClinicalTrialsCollector",
    "PubMedCollector",
    "RedditCollector",
    "ScholarCollector",
    "XAISearchCollector",
]
