"""ClinicalTrials.gov collector using the v2 REST API."""

from __future__ import annotations

import logging
import re
from datetime import date

import requests

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Filler words to strip from queries — ClinicalTrials.gov searches best with
# medical keywords, not natural language sentences.
_STOPWORDS = frozenset(
    "a an the of in on for and or with to by from is are was were be been being "
    "that this these those it its into as at which how what where when who whom "
    "using including particularly especially specifically co-occurring concurrent "
    "approaches techniques outcomes impact effects role potential latest recent "
    "new novel current emerging innovative comprehensive multimodal tailored "
    "targeted diagnosed patients individuals subjects people adolescents pediatric "
    "young adults children teenagers monitoring alleviating managing addressing "
    "disorders conditions associated related based".split()
)


def _sanitize_query(raw: str) -> str:
    """Convert a natural-language query into effective API keywords.

    Strips stopwords and filler, keeps medical terms, caps at 8 keywords.
    """
    # Remove parenthetical content and special chars except hyphens
    cleaned = re.sub(r"\([^)]*\)", " ", raw)
    cleaned = re.sub(r"[^\w\s-]", " ", cleaned)

    keywords = []
    for word in cleaned.split():
        if word.lower() not in _STOPWORDS and len(word) > 1:
            keywords.append(word)
        if len(keywords) >= 8:
            break

    return " ".join(keywords) if keywords else raw.split()[0]


class ClinicalTrialsCollector(Collector):
    source_type = "clinical_trials"

    def search(self, query: str, max_results: int = 15) -> list[RawFinding]:
        clean_query = _sanitize_query(query)
        logger.debug(f"ClinicalTrials query: '{query[:60]}' → '{clean_query}'")

        params = {
            "query.term": clean_query,
            "pageSize": min(max_results, 100),
            "format": "json",
        }

        resp = requests.get(API_BASE, params=params, timeout=30)
        if resp.status_code == 400:
            # Last resort: try just the first 3 words
            fallback = " ".join(clean_query.split()[:3])
            logger.warning(
                f"ClinicalTrials.gov 400 for '{clean_query}', retrying with '{fallback}'"
            )
            params["query.term"] = fallback
            resp = requests.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        findings = []
        for study in data.get("studies", []):
            try:
                findings.append(self._parse_study(study))
            except Exception:
                logger.debug("Failed to parse a clinical trial study", exc_info=True)
                continue

        return findings

    def _parse_study(self, study: dict) -> RawFinding:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        desc = proto.get("descriptionModule", {})
        status = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        arms = proto.get("armsInterventionsModule", {})
        contacts = proto.get("contactsLocationsModule", {})

        nct_id = ident.get("nctId", "")
        title = ident.get("briefTitle", ident.get("officialTitle", ""))
        summary = desc.get("briefSummary", "")

        # Interventions
        interventions = []
        for interv in arms.get("interventions", []):
            name = interv.get("name", "")
            itype = interv.get("type", "")
            if name:
                interventions.append(f"{itype}: {name}" if itype else name)

        # Locations
        locations = []
        for loc in contacts.get("locations", [])[:5]:
            parts = [loc.get("facility", ""), loc.get("city", ""), loc.get("state", ""), loc.get("country", "")]
            locations.append(", ".join(p for p in parts if p))

        # Contact info
        contact_info = []
        for contact in contacts.get("centralContacts", [])[:2]:
            name = contact.get("name", "")
            email = contact.get("email", "")
            if name:
                contact_info.append(f"{name} ({email})" if email else name)

        # Build rich content
        content_parts = [summary]
        if interventions:
            content_parts.append(f"Interventions: {'; '.join(interventions)}")
        if locations:
            content_parts.append(f"Locations: {'; '.join(locations)}")
        if contact_info:
            content_parts.append(f"Contacts: {'; '.join(contact_info)}")

        # Parse start date
        start_date = None
        date_str = status.get("startDateStruct", {}).get("date", "")
        if date_str:
            try:
                parts = date_str.split("-")
                if len(parts) >= 2:
                    start_date = date(int(parts[0]), int(parts[1]), 1)
                else:
                    start_date = date(int(parts[0]), 1, 1)
            except (ValueError, IndexError):
                pass

        phases = design.get("phases", [])

        return RawFinding(
            source_type=self.source_type,
            source_url=f"https://clinicaltrials.gov/study/{nct_id}",
            title=title,
            content="\n\n".join(content_parts),
            date=start_date,
            metadata={
                "nct_id": nct_id,
                "status": status.get("overallStatus", ""),
                "phases": phases,
                "interventions": interventions,
                "locations": locations[:3],
                "contacts": contact_info,
            },
        )
