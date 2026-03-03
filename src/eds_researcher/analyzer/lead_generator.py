"""Adaptive lead generation — produces follow-up search queries based on gaps and findings."""

from __future__ import annotations

import logging

from eds_researcher.memory.models import SearchLead

from .grok_client import GrokClient

logger = logging.getLogger(__name__)

LEAD_SYSTEM = """You are a medical research strategist specializing in Ehlers-Danlos Syndrome (EDS).
Your job is to identify knowledge gaps and generate targeted search queries to fill them.
Focus on treatments for a 17-year-old with hEDS and autism experiencing joint pain, neuropathy, muscle pain, and brain fog.
Always respond in valid JSON."""

LEAD_PROMPT = """Based on the following context, generate targeted search queries to expand our knowledge.

Known treatments (already in database):
{known_treatments}

Recent findings summary:
{recent_summary}

Previous search queries that had low results:
{low_yield_queries}

Symptoms we're tracking: knee pain, hip pain, shoulder pain, neuropathy, muscle pain, brain fog

Generate {num_leads} new search queries. For each, specify:
1. The query text (specific, targeted)
2. Which source to search (pubmed, reddit, xai_search, clinical_trials, scholar)
3. Priority 1-10 (1=highest)
4. Why this query is worth pursuing

Return JSON:
{{
  "leads": [
    {{
      "query": "search query text",
      "source": "pubmed|reddit|xai_search|clinical_trials|scholar",
      "priority": 1-10,
      "rationale": "why this is worth searching"
    }}
  ]
}}"""


class LeadGenerator:
    """Generates adaptive search leads using Grok."""

    def __init__(self, grok: GrokClient):
        self.grok = grok

    def generate(
        self,
        known_treatments: list[str],
        recent_summary: str,
        low_yield_queries: list[str],
        num_leads: int = 10,
    ) -> list[SearchLead]:
        """Generate new search leads based on current knowledge state."""
        prompt = LEAD_PROMPT.format(
            known_treatments=", ".join(known_treatments[:30]) if known_treatments else "None yet (first run)",
            recent_summary=recent_summary[:2000] if recent_summary else "No recent findings yet.",
            low_yield_queries=", ".join(low_yield_queries[:10]) if low_yield_queries else "None",
            num_leads=num_leads,
        )

        try:
            data = self.grok.complete_json(prompt, system=LEAD_SYSTEM, model=self.grok.analysis_model)
        except Exception:
            logger.warning("Lead generation failed", exc_info=True)
            return self._fallback_leads()

        if not isinstance(data, dict):
            return self._fallback_leads()

        leads = []
        for item in data.get("leads", []):
            leads.append(SearchLead(
                query_text=item.get("query", ""),
                source_target=item.get("source", "pubmed"),
                priority=int(item.get("priority", 5)),
                origin=f"grok_lead_gen: {item.get('rationale', '')[:100]}",
            ))

        return leads

    def _fallback_leads(self) -> list[SearchLead]:
        """Default leads if Grok fails — cover the basics."""
        base_queries = [
            ("Ehlers-Danlos syndrome pain management treatment", "pubmed", 1),
            ("EDS hypermobility joint pain medication", "pubmed", 2),
            ("hEDS neuropathy treatment", "pubmed", 2),
            ("EDS brain fog treatment cognitive", "pubmed", 3),
            ("ehlers danlos pain what helps", "reddit", 3),
            ("EDS supplement pain neuropathy", "reddit", 4),
            ("Ehlers-Danlos syndrome clinical trial", "clinical_trials", 2),
            ("hypermobile EDS pain management systematic review", "scholar", 3),
            ("EDS pain treatment autism comorbidity", "xai_search", 4),
            ("low dose naltrexone EDS", "pubmed", 3),
        ]
        return [
            SearchLead(query_text=q, source_target=s, priority=p, origin="fallback_defaults")
            for q, s, p in base_queries
        ]
