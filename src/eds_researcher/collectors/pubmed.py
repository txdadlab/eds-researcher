"""NCBI collector — PubMed, PMC (full-text), Books (GeneReviews), and OMIM."""

from __future__ import annotations

import logging
import os
from datetime import date

from Bio import Entrez

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

# NCBI databases relevant to EDS treatment research
NCBI_DATABASES = {
    "pubmed": {
        "rettype": "xml",
        "retmode": "xml",
        "parser": "_parse_pubmed_article",
        "article_key": "PubmedArticle",
    },
    "pmc": {
        "rettype": "xml",
        "retmode": "xml",
        "parser": "_parse_pmc_article",
        "article_key": None,  # PMC has different structure
    },
}


class PubMedCollector(Collector):
    """Searches PubMed, PMC, and NCBI Books via Entrez API."""

    source_type = "pubmed"

    def __init__(
        self,
        email: str = "",
        api_key: str | None = None,
        databases: list[str] | None = None,
    ):
        Entrez.email = email or os.getenv("NCBI_EMAIL", "eds-researcher@example.com")
        key = api_key or os.getenv("NCBI_API_KEY")
        if key:
            Entrez.api_key = key
        self.databases = databases or ["pubmed", "pmc"]

    def search(self, query: str, max_results: int = 20) -> list[RawFinding]:
        findings = []
        per_db = max(5, max_results // len(self.databases))

        for db_name in self.databases:
            try:
                if db_name == "pubmed":
                    findings.extend(self._search_pubmed(query, per_db))
                elif db_name == "pmc":
                    findings.extend(self._search_pmc(query, per_db))
                elif db_name == "books":
                    findings.extend(self._search_books(query, per_db))
            except Exception:
                logger.warning(f"NCBI {db_name} search failed", exc_info=True)
                continue

        return findings[:max_results]

    # ── PubMed ──────────────────────────────────────────────

    def _search_pubmed(self, query: str, max_results: int) -> list[RawFinding]:
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="relevance")
        record = Entrez.read(handle)
        handle.close()

        id_list = record.get("IdList", [])
        if not id_list:
            return []

        handle = Entrez.efetch(db="pubmed", id=id_list, rettype="xml", retmode="xml")
        articles = Entrez.read(handle)
        handle.close()

        findings = []
        for article in articles.get("PubmedArticle", []):
            try:
                findings.append(self._parse_pubmed_article(article))
            except Exception:
                logger.debug("Failed to parse PubMed article", exc_info=True)
        return findings

    def _parse_pubmed_article(self, article: dict) -> RawFinding:
        medline = article["MedlineCitation"]
        art = medline["Article"]
        pmid = str(medline["PMID"])

        title = str(art.get("ArticleTitle", ""))

        abstract_parts = []
        abstract_data = art.get("Abstract", {}).get("AbstractText", [])
        for part in abstract_data:
            abstract_parts.append(str(part))
        abstract = "\n".join(abstract_parts)

        pub_date = self._parse_pubdate(art)
        authors = self._extract_authors(art)
        mesh_terms = self._extract_mesh(medline)

        return RawFinding(
            source_type="pubmed",
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            title=title,
            content=abstract or title,
            date=pub_date,
            metadata={
                "pmid": pmid,
                "ncbi_db": "pubmed",
                "authors": authors[:5],
                "mesh_terms": mesh_terms,
                "journal": str(art.get("Journal", {}).get("Title", "")),
            },
        )

    # ── PMC (full-text) ────────────────────────────────────

    def _search_pmc(self, query: str, max_results: int) -> list[RawFinding]:
        handle = Entrez.esearch(db="pmc", term=query, retmax=max_results, sort="relevance")
        record = Entrez.read(handle)
        handle.close()

        id_list = record.get("IdList", [])
        if not id_list:
            return []

        # Fetch summaries (full XML is huge, summaries are more practical)
        handle = Entrez.esummary(db="pmc", id=",".join(id_list))
        summaries = Entrez.read(handle)
        handle.close()

        findings = []
        for summary in summaries:
            try:
                findings.append(self._parse_pmc_summary(summary))
            except Exception:
                logger.debug("Failed to parse PMC summary", exc_info=True)
        return findings

    def _parse_pmc_summary(self, summary: dict) -> RawFinding:
        pmcid = str(summary.get("Id", ""))
        title = str(summary.get("Title", ""))
        source = str(summary.get("Source", ""))
        pub_date_str = str(summary.get("PubDate", ""))
        authors = [str(a) for a in summary.get("AuthorList", [])]

        # PMC summaries don't include abstracts, but we can fetch them via efetch
        # For now, build content from available fields
        content_parts = [title]
        if source:
            content_parts.append(f"Published in: {source}")
        if authors:
            content_parts.append(f"Authors: {', '.join(authors[:5])}")

        pub_date = None
        if pub_date_str:
            try:
                parts = pub_date_str.split()
                if len(parts) >= 1:
                    pub_date = date(int(parts[0]), 1, 1)
            except (ValueError, IndexError):
                pass

        return RawFinding(
            source_type="pubmed",
            source_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/",
            title=title,
            content="\n".join(content_parts),
            date=pub_date,
            metadata={
                "pmcid": f"PMC{pmcid}",
                "ncbi_db": "pmc",
                "authors": authors[:5],
                "journal": source,
            },
        )

    # ── Books (GeneReviews, NCBI Bookshelf) ────────────────

    def _search_books(self, query: str, max_results: int) -> list[RawFinding]:
        handle = Entrez.esearch(db="books", term=query, retmax=max_results, sort="relevance")
        record = Entrez.read(handle)
        handle.close()

        id_list = record.get("IdList", [])
        if not id_list:
            return []

        handle = Entrez.esummary(db="books", id=",".join(id_list))
        summaries = Entrez.read(handle)
        handle.close()

        findings = []
        for summary in summaries:
            try:
                findings.append(self._parse_book_summary(summary))
            except Exception:
                logger.debug("Failed to parse Books summary", exc_info=True)
        return findings

    def _parse_book_summary(self, summary: dict) -> RawFinding:
        rid = str(summary.get("RID", summary.get("Id", "")))
        title = str(summary.get("Title", ""))
        book_title = str(summary.get("BookTitle", ""))
        authors = [str(a) for a in summary.get("AuthorList", [])]

        content_parts = [title]
        if book_title and book_title != title:
            content_parts.append(f"From: {book_title}")
        if authors:
            content_parts.append(f"Authors: {', '.join(authors[:5])}")

        return RawFinding(
            source_type="pubmed",
            source_url=f"https://www.ncbi.nlm.nih.gov/books/{rid}/",
            title=title,
            content="\n".join(content_parts),
            date=None,
            metadata={
                "ncbi_db": "books",
                "book_title": book_title,
                "authors": authors[:5],
            },
        )

    # ── Helpers ─────────────────────────────────────────────

    def _parse_pubdate(self, art: dict) -> date | None:
        date_data = art.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        year = date_data.get("Year")
        month = date_data.get("Month", "01")
        if year:
            try:
                month_map = {
                    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                }
                m = month_map.get(str(month), None) or int(month)
                return date(int(year), m, 1)
            except (ValueError, TypeError):
                return date(int(year), 1, 1)
        return None

    def _extract_authors(self, art: dict) -> list[str]:
        authors = []
        for author in art.get("AuthorList", []):
            last = author.get("LastName", "")
            first = author.get("ForeName", "")
            if last:
                authors.append(f"{last} {first}".strip())
        return authors

    def _extract_mesh(self, medline: dict) -> list[str]:
        mesh_terms = []
        for mesh in medline.get("MeshHeadingList", []):
            descriptor = mesh.get("DescriptorName")
            if descriptor:
                mesh_terms.append(str(descriptor))
        return mesh_terms
