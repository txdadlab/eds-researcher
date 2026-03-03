"""Tests for OpenFDA collector with mocked API responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.collectors.openfda import OpenFDACollector

MOCK_LABEL_RESPONSE = {
    "results": [
        {
            "openfda": {
                "brand_name": ["REVIA"],
                "generic_name": ["NALTREXONE HYDROCHLORIDE"],
                "pharm_class_epc": ["Opioid Antagonist"],
                "application_number": ["NDA018932"],
            },
            "mechanism_of_action": [
                "Naltrexone is a pure opioid antagonist that blocks the effects of opioids "
                "by competitive binding at opioid receptors."
            ],
            "clinical_pharmacology": [
                "Naltrexone is a long-acting opioid antagonist with highest affinity for mu receptors."
            ],
            "indications_and_usage": [
                "For the treatment of alcohol dependence and opioid dependence."
            ],
            "drug_interactions": [
                "Patients taking naltrexone should not use opioid-containing medications."
            ],
            "adverse_reactions": [
                "Hepatotoxicity, nausea, headache, dizziness, fatigue, insomnia, anxiety."
            ],
        }
    ]
}

MOCK_EVENTS_RESPONSE = {
    "results": [
        {"term": "NAUSEA", "count": 1500},
        {"term": "HEADACHE", "count": 1200},
        {"term": "FATIGUE", "count": 800},
    ]
}


@patch("eds_researcher.collectors.openfda.requests.get")
def test_openfda_drug_labels(mock_get):
    mock_get.return_value = _mock_response(200, MOCK_LABEL_RESPONSE)

    collector = OpenFDACollector()
    results = collector._search_drug_labels("naltrexone", max_results=5)

    assert len(results) == 1
    assert results[0].source_type == "openfda"
    assert results[0].title == "REVIA"
    assert "opioid antagonist" in results[0].content.lower()
    assert results[0].metadata["has_mechanism"] is True
    assert "Opioid Antagonist" in results[0].metadata["pharm_class"]


@patch("eds_researcher.collectors.openfda.requests.get")
def test_openfda_adverse_events(mock_get):
    mock_get.return_value = _mock_response(200, MOCK_EVENTS_RESPONSE)

    collector = OpenFDACollector()
    results = collector._search_adverse_events("naltrexone", max_results=5)

    assert len(results) == 1
    assert "NAUSEA" in results[0].content
    assert results[0].metadata["top_reactions"]["NAUSEA"] == 1500


@patch("eds_researcher.collectors.openfda.requests.get")
def test_openfda_handles_api_error(mock_get):
    mock_get.side_effect = Exception("Service unavailable")

    collector = OpenFDACollector()
    results = collector.search_safe("naltrexone")
    assert results == []


@patch("eds_researcher.collectors.openfda.requests.get")
def test_openfda_handles_404(mock_get):
    mock_get.return_value = _mock_response(404, {})

    collector = OpenFDACollector()
    results = collector._search_drug_labels("nonexistent_drug_xyz", max_results=5)
    assert results == []


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp
