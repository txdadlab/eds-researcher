"""Integration test: run full pipeline with mocked API responses."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eds_researcher.analyzer.grok_client import GrokClient
from eds_researcher.memory.database import Database
from eds_researcher.memory.embeddings import EmbeddingStore
from eds_researcher.memory.models import (
    BodyRegion,
    EvidenceTier,
    RawFinding,
    Severity,
    Symptom,
)
from eds_researcher.scheduler.pipeline import Pipeline


MOCK_EXTRACTION_RESPONSE = {
    "treatments": [
        {
            "name": "Low-dose naltrexone",
            "category": "medication",
            "description": "Off-label opioid antagonist for pain modulation",
            "mechanism_of_action": "Upregulates endorphin production",
            "legality": "Prescription, off-label",
            "cost_estimate": "$30-50/month",
            "side_effects": "Vivid dreams",
            "relevant_symptoms": ["knee_pain", "neuropathy"],
            "effectiveness_notes": "30% pain reduction in RCT",
        }
    ],
    "providers": [
        {
            "name": "Dr. Chopra",
            "credentials": "MD",
            "specialty": "Pain Management",
            "location": "Providence, RI",
            "contact_info": "",
        }
    ],
    "evidence_summary": "RCT showing 30% pain reduction with LDN",
    "supports_treatment": "true",
    "relevance_score": 0.85,
}

MOCK_LEADS_RESPONSE = {
    "leads": [
        {
            "query": "EDS prolotherapy systematic review",
            "source": "pubmed",
            "priority": 3,
            "rationale": "Follow up on prolotherapy mentions",
        }
    ]
}

MOCK_RAW_FINDING = RawFinding(
    source_type="pubmed",
    source_url="https://pubmed.ncbi.nlm.nih.gov/99999/",
    title="LDN for EDS Pain: A Randomized Controlled Trial",
    content="This randomized controlled trial evaluated low-dose naltrexone (LDN) in 50 hEDS patients...",
    date=date(2025, 1, 15),
)


@pytest.fixture
def mock_config(tmp_path):
    """Create a minimal config for testing."""
    import yaml

    config = {
        "symptoms": [
            {"name": "knee_pain", "body_region": "joint", "severity": "high"},
            {"name": "neuropathy", "body_region": "neurological", "severity": "high"},
            {"name": "brain_fog", "body_region": "cognitive", "severity": "high"},
        ],
        "search": {"max_results_per_source": 5},
        "sources": {
            "pubmed": {"enabled": True, "email": "test@test.com"},
            "reddit": {"enabled": False},
            "xai_search": {"enabled": False},
            "clinical_trials": {"enabled": False},
            "scholar": {"enabled": False},
        },
        "grok": {
            "screening_model": "grok-3-mini-fast",
            "analysis_model": "grok-3-mini",
            "base_url": "https://api.x.ai/v1",
            "max_tokens": 4096,
            "temperature": 0.3,
        },
        "reports": {"output_dir": str(tmp_path / "reports")},
        "database": {
            "path": str(tmp_path / "test.db"),
            "chromadb_path": str(tmp_path / "chromadb"),
        },
    }

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return config_path


@patch("eds_researcher.scheduler.pipeline.PubMedCollector")
@patch("eds_researcher.analyzer.grok_client.OpenAI")
def test_full_pipeline(mock_openai_cls, mock_pubmed_cls, mock_config, tmp_path):
    """Run the full pipeline with mocked APIs and verify output."""
    import json

    # Mock Grok client responses
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    def mock_completion(**kwargs):
        resp = MagicMock()
        messages = kwargs.get("messages", [])
        user_msg = messages[-1]["content"] if messages else ""

        if "extract" in user_msg.lower() or "analyze" in user_msg.lower():
            resp.choices[0].message.content = json.dumps(MOCK_EXTRACTION_RESPONSE)
        else:
            resp.choices[0].message.content = json.dumps(MOCK_LEADS_RESPONSE)
        return resp

    mock_client.chat.completions.create.side_effect = mock_completion

    # Mock PubMed collector
    mock_pubmed = MagicMock()
    mock_pubmed.source_type = "pubmed"
    mock_pubmed.search_safe.return_value = [MOCK_RAW_FINDING]
    mock_pubmed_cls.return_value = mock_pubmed

    # Run pipeline
    pipeline = Pipeline(config_path=str(mock_config))
    # Replace the PubMed collector with our mock
    pipeline.collectors = {"pubmed": mock_pubmed}

    stats = pipeline.run()

    # Verify pipeline produced results
    assert stats["findings"] > 0
    assert stats["treatments"] > 0
    assert stats["evidence"] > 0

    # Verify database was populated
    treatments = pipeline.db.get_all_treatments()
    assert len(treatments) >= 1
    assert any("naltrexone" in t.name.lower() for t in treatments)

    # Verify symptoms were seeded
    symptoms = pipeline.db.get_all_symptoms()
    assert len(symptoms) == 3

    # Verify evidence was added
    for t in treatments:
        evidence = pipeline.db.get_evidence_for_treatment(t.id)
        assert len(evidence) >= 1

    # Verify reports can be generated
    full_path, delta_path = pipeline.generate_reports()
    assert full_path.exists()
    assert delta_path.exists()

    full_content = full_path.read_text()
    assert "naltrexone" in full_content.lower()

    pipeline.close()
