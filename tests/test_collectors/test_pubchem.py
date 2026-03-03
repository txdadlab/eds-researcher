"""Tests for PubChem collector with mocked API responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.collectors.pubchem import PubChemCollector

MOCK_AUTOCOMPLETE = {
    "dictionary_terms": {
        "compound": ["palmitoylethanolamide", "palmitic acid"]
    }
}

MOCK_CID_RESPONSE = {
    "IdentifierList": {"CID": [4671]}
}

MOCK_PROPERTIES = {
    "PropertyTable": {
        "Properties": [{
            "CID": 4671,
            "MolecularFormula": "C18H37NO2",
            "MolecularWeight": 299.49,
            "IUPACName": "N-(2-hydroxyethyl)hexadecanamide",
            "IsomericSMILES": "CCCCCCCCCCCCCCCC(=O)NCCO",
        }]
    }
}

MOCK_DESCRIPTION = {
    "InformationList": {
        "Information": [{
            "Description": "Palmitoylethanolamide (PEA) is an endogenous fatty acid amide that acts as an anti-inflammatory and analgesic agent through multiple mechanisms including PPAR-alpha activation."
        }]
    }
}


@patch("eds_researcher.collectors.pubchem.requests.get")
def test_pubchem_compound_search(mock_get):
    responses = [
        # autocomplete
        _mock_response(200, MOCK_AUTOCOMPLETE),
        # CID lookup for first compound
        _mock_response(200, MOCK_CID_RESPONSE),
        # properties
        _mock_response(200, MOCK_PROPERTIES),
        # description
        _mock_response(200, MOCK_DESCRIPTION),
        # CID lookup for second compound
        _mock_response(200, MOCK_CID_RESPONSE),
        # properties
        _mock_response(200, MOCK_PROPERTIES),
        # description
        _mock_response(200, MOCK_DESCRIPTION),
    ]
    mock_get.side_effect = responses

    collector = PubChemCollector()
    results = collector._search_compounds("palmitoylethanolamide", max_results=5)

    assert len(results) >= 1
    assert results[0].source_type == "pubchem"
    assert "pubchem.ncbi.nlm.nih.gov" in results[0].source_url
    assert results[0].metadata["cid"] == 4671


@patch("eds_researcher.collectors.pubchem.requests.get")
def test_pubchem_handles_no_results(mock_get):
    mock_get.return_value = _mock_response(200, {"dictionary_terms": {"compound": []}})

    collector = PubChemCollector()
    results = collector._search_compounds("nonexistent_compound_xyz", max_results=5)
    assert results == []


@patch("eds_researcher.collectors.pubchem.requests.get")
def test_pubchem_handles_api_error(mock_get):
    mock_get.side_effect = Exception("Connection refused")

    collector = PubChemCollector()
    results = collector.search_safe("BPC-157")
    assert results == []


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp
