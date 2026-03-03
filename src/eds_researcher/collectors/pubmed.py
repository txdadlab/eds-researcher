"""PubMed/NCBI collector using Biopython's Entrez API."""

from __future__ import annotations

import logging
import os
from datetime import date

from Bio import Entrez

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)


class PubMedCollector(Collector):
    source_type = "pubmed"

    def __init__(self, email: str = "", api_key: str | None = None):
        Entrez.email = email or os.getenv("NCBI_EMAIL", "eds-researcher@example.com")
        key = api_key or os.getenv("NCBI_API_KEY")
        if key:
            Entrez.api_key = key

    def search(self, query: str, max_results: int = 20) -> list[RawFinding]:
        # Search for article IDs
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="relevance")
        record = Entrez.read(handle)
        handle.close()

        id_list = record.get("IdList", [])
        if not id_list:
            return []

        # Fetch article details
        handle = Entrez.efetch(db="pubmed", id=id_list, rettype="xml", retmode="xml")
        articles = Entrez.read(handle)
        handle.close()

        findings = []
        for article in articles.get("PubmedArticle", []):
            try:
                findings.append(self._parse_article(article))
            except Exception:
                logger.debug("Failed to parse a PubMed article", exc_info=True)
                continue

        return findings

    def _parse_article(self, article: dict) -> RawFinding:
        medline = article["MedlineCitation"]
        art = medline["Article"]
        pmid = str(medline["PMID"])

        title = str(art.get("ArticleTitle", ""))

        # Extract abstract text
        abstract_parts = []
        abstract_data = art.get("Abstract", {}).get("AbstractText", [])
        for part in abstract_data:
            abstract_parts.append(str(part))
        abstract = "\n".join(abstract_parts)

        # Extract publication date
        pub_date = None
        date_data = art.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        year = date_data.get("Year")
        month = date_data.get("Month", "01")
        if year:
            try:
                # Month might be a name like "Jan"
                month_map = {
                    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                }
                m = month_map.get(str(month), None) or int(month)
                pub_date = date(int(year), m, 1)
            except (ValueError, TypeError):
                pub_date = date(int(year), 1, 1)

        # Extract authors
        authors = []
        for author in art.get("AuthorList", []):
            last = author.get("LastName", "")
            first = author.get("ForeName", "")
            if last:
                authors.append(f"{last} {first}".strip())

        # Extract MeSH terms
        mesh_terms = []
        for mesh in medline.get("MeshHeadingList", []):
            descriptor = mesh.get("DescriptorName")
            if descriptor:
                mesh_terms.append(str(descriptor))

        return RawFinding(
            source_type=self.source_type,
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            title=title,
            content=abstract or title,
            date=pub_date,
            metadata={
                "pmid": pmid,
                "authors": authors[:5],  # Top 5
                "mesh_terms": mesh_terms,
                "journal": str(art.get("Journal", {}).get("Title", "")),
            },
        )
