"""Tests for ClinicalTrials.gov collector with mocked API responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.collectors.clinical_trials import ClinicalTrialsCollector

MOCK_API_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Low-Dose Naltrexone for Ehlers-Danlos Syndrome Pain",
                },
                "descriptionModule": {
                    "briefSummary": "This study evaluates LDN for chronic pain in hEDS patients.",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "startDateStruct": {"date": "2025-01"},
                },
                "designModule": {
                    "phases": ["PHASE2"],
                },
                "armsInterventionsModule": {
                    "interventions": [
                        {"name": "Naltrexone 4.5mg", "type": "DRUG"},
                    ],
                },
                "contactsLocationsModule": {
                    "locations": [
                        {"facility": "Mayo Clinic", "city": "Rochester", "state": "MN", "country": "US"},
                    ],
                    "centralContacts": [
                        {"name": "Dr. Smith", "email": "smith@mayo.edu"},
                    ],
                },
            }
        }
    ]
}


@patch("eds_researcher.collectors.clinical_trials.requests.get")
def test_clinical_trials_search(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    collector = ClinicalTrialsCollector()
    results = collector.search("Ehlers-Danlos syndrome pain", max_results=5)

    assert len(results) == 1
    assert results[0].source_type == "clinical_trials"
    assert "NCT12345678" in results[0].source_url
    assert "naltrexone" in results[0].title.lower()
    assert results[0].metadata["status"] == "RECRUITING"
    assert "Mayo Clinic" in results[0].metadata["locations"][0]


@patch("eds_researcher.collectors.clinical_trials.requests.get")
def test_clinical_trials_empty(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"studies": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    collector = ClinicalTrialsCollector()
    results = collector.search("nonexistent condition xyz")
    assert results == []


@patch("eds_researcher.collectors.clinical_trials.requests.get")
def test_clinical_trials_network_error(mock_get):
    mock_get.side_effect = Exception("Connection timeout")

    collector = ClinicalTrialsCollector()
    results = collector.search_safe("EDS")
    assert results == []
