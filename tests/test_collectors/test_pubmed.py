"""Tests for PubMed collector with mocked Entrez responses."""

from unittest.mock import MagicMock, patch
from io import StringIO

from eds_researcher.collectors.pubmed import PubMedCollector


MOCK_SEARCH_RESULT = {"IdList": ["12345", "67890"], "Count": "2"}

MOCK_FETCH_RESULT = {
    "PubmedArticle": [
        {
            "MedlineCitation": {
                "PMID": "12345",
                "Article": {
                    "ArticleTitle": "Low-dose naltrexone in EDS pain management",
                    "Abstract": {
                        "AbstractText": [
                            "Background: EDS causes chronic pain.",
                            "Results: LDN reduced pain scores by 30%.",
                        ]
                    },
                    "AuthorList": [
                        {"LastName": "Smith", "ForeName": "John"},
                        {"LastName": "Doe", "ForeName": "Jane"},
                    ],
                    "Journal": {
                        "Title": "Pain Medicine",
                        "JournalIssue": {
                            "PubDate": {"Year": "2024", "Month": "Mar"}
                        },
                    },
                },
                "MeshHeadingList": [
                    {"DescriptorName": "Ehlers-Danlos Syndrome"},
                    {"DescriptorName": "Naltrexone"},
                ],
            }
        }
    ]
}


@patch("eds_researcher.collectors.pubmed.Entrez")
def test_pubmed_search(mock_entrez):
    # Mock esearch
    mock_entrez.esearch.return_value = MagicMock()
    mock_entrez.read.side_effect = [MOCK_SEARCH_RESULT, MOCK_FETCH_RESULT]
    mock_entrez.efetch.return_value = MagicMock()

    collector = PubMedCollector(email="test@test.com")
    results = collector.search("EDS pain treatment", max_results=5)

    assert len(results) == 1
    assert results[0].source_type == "pubmed"
    assert "naltrexone" in results[0].title.lower()
    assert "12345" in results[0].source_url
    assert results[0].metadata["pmid"] == "12345"
    assert len(results[0].metadata["authors"]) == 2


@patch("eds_researcher.collectors.pubmed.Entrez")
def test_pubmed_empty_results(mock_entrez):
    mock_entrez.esearch.return_value = MagicMock()
    mock_entrez.read.return_value = {"IdList": [], "Count": "0"}

    collector = PubMedCollector(email="test@test.com")
    results = collector.search("nonexistent query xyz")

    assert results == []


@patch("eds_researcher.collectors.pubmed.Entrez")
def test_pubmed_search_safe_handles_errors(mock_entrez):
    mock_entrez.esearch.side_effect = Exception("Network error")

    collector = PubMedCollector(email="test@test.com")
    results = collector.search_safe("failing query")

    assert results == []
