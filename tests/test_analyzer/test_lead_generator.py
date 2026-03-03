"""Tests for adaptive lead generation."""

from unittest.mock import MagicMock

from eds_researcher.analyzer.grok_client import GrokClient
from eds_researcher.analyzer.lead_generator import LeadGenerator


MOCK_LEADS_RESPONSE = {
    "leads": [
        {
            "query": "EDS prolotherapy efficacy systematic review",
            "source": "pubmed",
            "priority": 2,
            "rationale": "Prolotherapy mentioned but no evidence gathered yet",
        },
        {
            "query": "hypermobility joint pain physical therapy protocol",
            "source": "scholar",
            "priority": 3,
            "rationale": "PT exercises are commonly recommended but specifics are lacking",
        },
    ]
}


def test_lead_generation():
    mock_grok = MagicMock(spec=GrokClient)
    mock_grok.complete_json.return_value = MOCK_LEADS_RESPONSE
    mock_grok.analysis_model = "grok-3-mini"

    generator = LeadGenerator(mock_grok)
    leads = generator.generate(
        known_treatments=["LDN", "Magnesium", "PT exercises"],
        recent_summary="Found evidence for LDN and magnesium.",
        low_yield_queries=["EDS cure"],
        num_leads=5,
    )

    assert len(leads) == 2
    assert leads[0].query_text == "EDS prolotherapy efficacy systematic review"
    assert leads[0].source_target == "pubmed"
    assert leads[0].priority == 2


def test_lead_generation_fallback():
    mock_grok = MagicMock(spec=GrokClient)
    mock_grok.complete_json.side_effect = Exception("API error")
    mock_grok.analysis_model = "grok-3-mini"

    generator = LeadGenerator(mock_grok)
    leads = generator.generate(
        known_treatments=[],
        recent_summary="",
        low_yield_queries=[],
    )

    # Should return fallback default leads
    assert len(leads) > 0
    assert any("Ehlers-Danlos" in l.query_text for l in leads)
