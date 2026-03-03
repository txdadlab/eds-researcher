"""PubChem collector — compound data, bioactivity, supplement-drug relationships."""

from __future__ import annotations

import logging

import requests

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_SEARCH = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name"


class PubChemCollector(Collector):
    """Searches PubChem for compound info, mechanisms, and supplement-drug relationships.

    Useful for finding:
    - Pharmacological mechanisms of supplements and drugs
    - Structural similarities between supplements and pharmaceuticals
    - Bioactivity data for peptides and compounds
    - Drug repurposing candidates
    """

    source_type = "pubchem"

    def search(self, query: str, max_results: int = 15) -> list[RawFinding]:
        findings = []

        # Strategy 1: Search by compound name / keyword
        findings.extend(self._search_compounds(query, max_results))

        # Strategy 2: If query mentions specific compounds, get detailed pharmacology
        findings.extend(self._search_bioactivity(query, max(3, max_results // 4)))

        return findings[:max_results]

    def _search_compounds(self, query: str, max_results: int) -> list[RawFinding]:
        """Search PubChem compound database via PUG REST."""
        try:
            # Use the autocomplete/search endpoint
            resp = requests.get(
                "https://pubchem.ncbi.nlm.nih.gov/rest/autocomplete/compound",
                params={"q": query, "limit": max_results},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            compound_names = data.get("dictionary_terms", {}).get("compound", [])
            if not compound_names:
                return []

            findings = []
            for name in compound_names[:max_results]:
                finding = self._get_compound_details(name)
                if finding:
                    findings.append(finding)

            return findings

        except Exception:
            logger.warning("PubChem compound search failed", exc_info=True)
            return []

    def _get_compound_details(self, compound_name: str) -> RawFinding | None:
        """Fetch detailed compound info from PubChem."""
        try:
            # Get CID
            resp = requests.get(
                f"{PUBCHEM_SEARCH}/{requests.utils.quote(compound_name)}/cids/JSON",
                timeout=15,
            )
            if resp.status_code != 200:
                return None

            cids = resp.json().get("IdentifierList", {}).get("CID", [])
            if not cids:
                return None

            cid = cids[0]

            # Get compound properties
            props_resp = requests.get(
                f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
                "MolecularFormula,MolecularWeight,IUPACName,IsomericSMILES,"
                "XLogP,HBondDonorCount,HBondAcceptorCount/JSON",
                timeout=15,
            )

            props = {}
            if props_resp.status_code == 200:
                prop_list = props_resp.json().get("PropertyTable", {}).get("Properties", [])
                if prop_list:
                    props = prop_list[0]

            # Get pharmacology/description
            desc_resp = requests.get(
                f"{PUBCHEM_BASE}/compound/cid/{cid}/description/JSON",
                timeout=15,
            )

            descriptions = []
            if desc_resp.status_code == 200:
                for info in desc_resp.json().get("InformationList", {}).get("Information", []):
                    desc = info.get("Description", "")
                    if desc and len(desc) > 50:
                        descriptions.append(desc)

            # Build content
            content_parts = []
            if descriptions:
                content_parts.append(descriptions[0][:2000])
            if props.get("MolecularFormula"):
                content_parts.append(f"Formula: {props['MolecularFormula']}")
            if props.get("MolecularWeight"):
                content_parts.append(f"Molecular weight: {props['MolecularWeight']}")
            if props.get("IUPACName"):
                content_parts.append(f"IUPAC: {props['IUPACName']}")

            if not content_parts:
                content_parts.append(compound_name)

            return RawFinding(
                source_type=self.source_type,
                source_url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                title=compound_name,
                content="\n".join(content_parts),
                date=None,
                metadata={
                    "cid": cid,
                    "molecular_formula": props.get("MolecularFormula", ""),
                    "molecular_weight": props.get("MolecularWeight", ""),
                    "smiles": props.get("IsomericSMILES", ""),
                    "description_count": len(descriptions),
                },
            )

        except Exception:
            logger.debug(f"Failed to get PubChem details for {compound_name}", exc_info=True)
            return None

    def _search_bioactivity(self, query: str, max_results: int) -> list[RawFinding]:
        """Search PubChem BioAssay for bioactivity data."""
        try:
            resp = requests.get(
                f"{PUBCHEM_BASE}/assay/type/all/json",
                params={"query": query, "maxrecords": max_results},
                timeout=30,
            )
            if resp.status_code != 200:
                return []

            # PUG REST assay search is limited — use text search instead
            resp = requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pcassay", "term": query, "retmax": max_results, "retmode": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []

            # Get assay summaries
            summ_resp = requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pcassay", "id": ",".join(id_list[:max_results]), "retmode": "json"},
                timeout=30,
            )
            summ_resp.raise_for_status()
            summ_data = summ_resp.json().get("result", {})

            findings = []
            for aid in id_list[:max_results]:
                info = summ_data.get(aid, {})
                if not info or not isinstance(info, dict):
                    continue

                assay_name = info.get("assayname", "")
                description = info.get("assaydescription", "")
                source = info.get("sourcename", "")

                if not assay_name:
                    continue

                content_parts = [assay_name]
                if description:
                    content_parts.append(description[:1500])
                if source:
                    content_parts.append(f"Source: {source}")

                findings.append(RawFinding(
                    source_type=self.source_type,
                    source_url=f"https://pubchem.ncbi.nlm.nih.gov/bioassay/{aid}",
                    title=assay_name,
                    content="\n".join(content_parts),
                    date=None,
                    metadata={
                        "assay_id": aid,
                        "source": source,
                        "ncbi_db": "pcassay",
                    },
                ))

            return findings

        except Exception:
            logger.warning("PubChem bioassay search failed", exc_info=True)
            return []
