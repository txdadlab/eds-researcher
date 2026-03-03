"""Abstract base class for all data collectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from eds_researcher.memory.models import RawFinding

logger = logging.getLogger(__name__)


class Collector(ABC):
    """Base interface for all data source collectors."""

    source_type: str = "unknown"

    @abstractmethod
    def search(self, query: str, max_results: int = 20) -> list[RawFinding]:
        """Execute a search query and return raw findings."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
    def _search_with_retry(self, query: str, max_results: int = 20) -> list[RawFinding]:
        """Search with automatic retry on transient network errors."""
        return self.search(query, max_results)

    def search_safe(self, query: str, max_results: int = 20) -> list[RawFinding]:
        """Search with error handling and retry — never raises, returns empty list on failure."""
        try:
            results = self._search_with_retry(query, max_results)
            logger.info(f"[{self.source_type}] Query '{query[:60]}' returned {len(results)} results")
            return results
        except Exception:
            logger.exception(f"[{self.source_type}] Failed to search for '{query[:60]}'")
            return []
