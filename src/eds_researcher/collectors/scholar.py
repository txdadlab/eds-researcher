"""Google Scholar collector using the scholarly library."""

from __future__ import annotations

import logging

from scholarly import scholarly

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)


class ScholarCollector(Collector):
    """Google Scholar search. May be rate-limited or blocked with heavy use."""

    source_type = "scholar"

    def __init__(self, use_proxy: bool = False):
        if use_proxy:
            try:
                scholarly.use_proxy(scholarly.FreeProxy())
                logger.info("Scholar using free proxy")
            except Exception:
                logger.warning("Failed to set up Scholar proxy, proceeding without")

    def search(self, query: str, max_results: int = 10) -> list[RawFinding]:
        findings = []
        try:
            search_query = scholarly.search_pubs(query)
            for _ in range(max_results):
                try:
                    pub = next(search_query)
                    findings.append(self._parse_pub(pub))
                except StopIteration:
                    break
                except Exception:
                    logger.debug("Failed to parse a Scholar result", exc_info=True)
                    continue
        except Exception:
            logger.warning("Scholar search failed (possibly rate-limited)", exc_info=True)

        return findings

    def _parse_pub(self, pub) -> RawFinding:
        bib = pub.get("bib", {})
        title = bib.get("title", "")
        abstract = bib.get("abstract", "")
        authors = bib.get("author", [])
        year = bib.get("pub_year", "")
        venue = bib.get("venue", "")

        # Build content
        content_parts = []
        if abstract:
            content_parts.append(abstract)
        if venue:
            content_parts.append(f"Published in: {venue}")
        if authors:
            author_str = ", ".join(authors[:5])
            content_parts.append(f"Authors: {author_str}")

        # URL — prefer eprint (direct link) over pub_url
        url = pub.get("eprint_url", "") or pub.get("pub_url", "")

        pub_date = None
        if year:
            try:
                from datetime import date
                pub_date = date(int(year), 1, 1)
            except (ValueError, TypeError):
                pass

        return RawFinding(
            source_type=self.source_type,
            source_url=url,
            title=title,
            content="\n\n".join(content_parts) if content_parts else title,
            date=pub_date,
            metadata={
                "authors": authors[:5],
                "year": year,
                "venue": venue,
                "cited_by": pub.get("num_citations", 0),
            },
        )
