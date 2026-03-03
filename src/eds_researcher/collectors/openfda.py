"""OpenFDA collector — drug labels, mechanisms, adverse events, interactions.

Free API, no authentication required.
"""

from __future__ import annotations

import logging

import requests

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov"


class OpenFDACollector(Collector):
    """Searches OpenFDA for drug labels, mechanisms, and safety data.

    Useful for finding:
    - Drug mechanism of action and pharmacology
    - Indications and usage (including off-label patterns)
    - Adverse events and side effect profiles
    - Drug interactions
    """

    source_type = "openfda"

    def search(self, query: str, max_results: int = 15) -> list[RawFinding]:
        findings = []

        # Search drug labels for pharmacology info
        findings.extend(self._search_drug_labels(query, max_results))

        # Search adverse event reports
        findings.extend(self._search_adverse_events(query, max(3, max_results // 4)))

        return findings[:max_results]

    def _search_drug_labels(self, query: str, max_results: int) -> list[RawFinding]:
        """Search FDA drug labels for mechanism, indication, and pharmacology."""
        try:
            resp = requests.get(
                f"{OPENFDA_BASE}/drug/label.json",
                params={
                    "search": f'"{query}"',
                    "limit": min(max_results, 99),
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = data.get("results", [])

            findings = []
            for result in results:
                try:
                    findings.append(self._parse_drug_label(result))
                except Exception:
                    logger.debug("Failed to parse FDA drug label", exc_info=True)

            return findings

        except Exception:
            logger.warning("OpenFDA drug label search failed", exc_info=True)
            return []

    def _parse_drug_label(self, label: dict) -> RawFinding:
        openfda = label.get("openfda", {})

        # Drug name
        brand_names = openfda.get("brand_name", [])
        generic_names = openfda.get("generic_name", [])
        name = (brand_names[0] if brand_names else
                generic_names[0] if generic_names else "Unknown Drug")

        # Build rich pharmacological content
        content_parts = []

        # Mechanism of action
        mechanism = label.get("mechanism_of_action", [])
        if mechanism:
            content_parts.append(f"MECHANISM OF ACTION:\n{mechanism[0][:1000]}")

        # Clinical pharmacology
        pharmacology = label.get("clinical_pharmacology", [])
        if pharmacology:
            content_parts.append(f"CLINICAL PHARMACOLOGY:\n{pharmacology[0][:1000]}")

        # Indications
        indications = label.get("indications_and_usage", [])
        if indications:
            content_parts.append(f"INDICATIONS:\n{indications[0][:500]}")

        # Drug interactions
        interactions = label.get("drug_interactions", [])
        if interactions:
            content_parts.append(f"DRUG INTERACTIONS:\n{interactions[0][:500]}")

        # Adverse reactions
        adverse = label.get("adverse_reactions", [])
        if adverse:
            content_parts.append(f"ADVERSE REACTIONS:\n{adverse[0][:500]}")

        # Pharmacokinetics
        pk = label.get("pharmacokinetics", [])
        if pk:
            content_parts.append(f"PHARMACOKINETICS:\n{pk[0][:500]}")

        # Warnings
        warnings = label.get("warnings_and_cautions", label.get("warnings", []))
        if warnings:
            content_parts.append(f"WARNINGS:\n{warnings[0][:500]}")

        # Drug class
        pharm_class = openfda.get("pharm_class_epc", [])

        # Application number for linking
        app_num = openfda.get("application_number", [""])[0]

        return RawFinding(
            source_type=self.source_type,
            source_url=f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={name.replace(' ', '+')}",
            title=name,
            content="\n\n".join(content_parts) if content_parts else name,
            date=None,
            metadata={
                "brand_names": brand_names[:3],
                "generic_names": generic_names[:3],
                "pharm_class": pharm_class,
                "application_number": app_num,
                "has_mechanism": bool(mechanism),
                "has_pharmacology": bool(pharmacology),
                "has_interactions": bool(interactions),
            },
        )

    def _search_adverse_events(self, query: str, max_results: int) -> list[RawFinding]:
        """Search FDA adverse event reports — useful for understanding real-world side effects."""
        try:
            resp = requests.get(
                f"{OPENFDA_BASE}/drug/event.json",
                params={
                    "search": f'patient.drug.openfda.generic_name:"{query}"',
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": 20,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = data.get("results", [])

            if not results:
                return []

            # Build a summary of the most common adverse reactions
            reactions = [(r["term"], r["count"]) for r in results[:20]]
            content_parts = [f"Most reported adverse reactions for '{query}':"]
            for reaction, count in reactions:
                content_parts.append(f"- {reaction}: {count} reports")

            return [RawFinding(
                source_type=self.source_type,
                source_url=f"https://open.fda.gov/apis/drug/event/",
                title=f"Adverse event profile: {query}",
                content="\n".join(content_parts),
                date=None,
                metadata={
                    "query_drug": query,
                    "top_reactions": dict(reactions[:10]),
                    "ncbi_db": "openfda_events",
                },
            )]

        except Exception:
            logger.debug(f"OpenFDA adverse events search failed for {query}", exc_info=True)
            return []
