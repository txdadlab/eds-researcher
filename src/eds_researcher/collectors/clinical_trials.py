"""ClinicalTrials.gov collector using the v2 REST API."""

from __future__ import annotations

import logging
from datetime import date

import requests

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

API_BASE = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsCollector(Collector):
    source_type = "clinical_trials"

    def search(self, query: str, max_results: int = 15) -> list[RawFinding]:
        params = {
            "query.term": query,
            "pageSize": min(max_results, 100),
            "format": "json",
            "fields": (
                "NCTId,BriefTitle,OfficialTitle,BriefSummary,"
                "OverallStatus,StartDate,CompletionDate,Phase,"
                "Condition,InterventionName,InterventionType,"
                "LocationFacility,LocationCity,LocationState,LocationCountry,"
                "ContactName,ContactEMail"
            ),
        }

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
