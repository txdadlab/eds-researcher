"""Tests for the Grok-powered extractor with mocked API responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.analyzer.extractor import Extractor
from eds_researcher.analyzer.grok_client import GrokClient
from eds_researcher.memory.models import EvidenceSupport, RawFinding


MOCK_EXTRACTION = {
    "treatments": [
        {
            "name": "Low-dose naltrexone",
            "category": "medication",
            "description": "Off-label opioid antagonist for pain modulation",
            "mechanism_of_action": "Blocks opioid receptors briefly, upregulating endorphins",
            "legality": "Prescription, off-label",
            "cost_estimate": "$30-50/month compounded",
            "side_effects": "Vivid dreams, initial headache",
            "relevant_symptoms": ["knee_pain", "hip_pain", "neuropathy"],
            "effectiveness_notes": "30% pain reduction in RCT",
        }
    ],
    "providers": [
        {
            "name": "Dr. Pradeep Chopra",
            "credentials": "MD",
            "specialty": "Pain Management, EDS specialist",
            "location": "Providence, RI",
            "contact_info": "",
        }
    ],
    "evidence_summary": "RCT showing 30% pain reduction with LDN in fibromyalgia patients, relevant to EDS",
    "supports_treatment": "true",
    "relevance_score": 0.85,
}


def test_extraction():
    mock_grok = MagicMock(spec=GrokClient)
    mock_grok.complete_json.return_value = MOCK_EXTRACTION

    extractor = Extractor(mock_grok)
    finding = RawFinding(
        source_type="pubmed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345/",
        title="LDN for EDS Pain",
        content="A randomized controlled trial showing 30% pain reduction...",
    )

    result = extractor.extract(finding)

    assert len(result.treatments) == 1
    assert result.treatments[0]["name"] == "Low-dose naltrexone"
    assert len(result.providers) == 1
    assert result.supports_treatment == EvidenceSupport.SUPPORTS
    assert result.relevance_score == 0.85


def test_extraction_handles_failure():
    mock_grok = MagicMock(spec=GrokClient)
    mock_grok.complete_json.side_effect = Exception("API error")

    extractor = Extractor(mock_grok)
    finding = RawFinding(
        source_type="reddit",
        source_url="https://reddit.com/r/eds/123",
        title="Test",
        content="Test content",
    )

    result = extractor.extract(finding)
    assert result.treatments == []
    assert result.relevance_score == 0.0


def test_batch_extraction_filters_low_relevance():
    mock_grok = MagicMock(spec=GrokClient)
    mock_grok.complete_json.side_effect = [
        {**MOCK_EXTRACTION, "relevance_score": 0.85},
        {"treatments": [], "providers": [], "evidence_summary": "Irrelevant", "supports_treatment": "false", "relevance_score": 0.05},
        {**MOCK_EXTRACTION, "relevance_score": 0.7},
    ]

    extractor = Extractor(mock_grok)
    findings = [
        RawFinding(source_type="pubmed", source_url="url1", title="T1", content="C1"),
        RawFinding(source_type="pubmed", source_url="url2", title="T2", content="C2"),
        RawFinding(source_type="pubmed", source_url="url3", title="T3", content="C3"),
    ]

    results = extractor.extract_batch(findings)
    # Second finding should be filtered out (low relevance, no treatments)
    assert len(results) == 2
