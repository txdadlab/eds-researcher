"""Tests for Google Scholar collector with mocked scholarly responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.collectors.scholar import ScholarCollector

MOCK_PUB = {
    "bib": {
        "title": "Hypermobility and chronic pain in Ehlers-Danlos syndrome",
        "abstract": "We review the mechanisms of chronic pain in hEDS.",
        "author": ["Smith J", "Doe A", "Brown K"],
        "pub_year": "2024",
        "venue": "Journal of Rheumatology",
    },
    "eprint_url": "https://example.com/paper.pdf",
    "pub_url": "https://scholar.google.com/...",
    "num_citations": 42,
}


@patch("eds_researcher.collectors.scholar.scholarly")
def test_scholar_search(mock_scholarly):
    mock_scholarly.search_pubs.return_value = iter([MOCK_PUB])

    collector = ScholarCollector.__new__(ScholarCollector)
    results = collector.search("EDS chronic pain", max_results=5)

    assert len(results) == 1
    assert results[0].source_type == "scholar"
    assert "Hypermobility" in results[0].title
    assert results[0].metadata["cited_by"] == 42
    assert results[0].metadata["year"] == "2024"


@patch("eds_researcher.collectors.scholar.scholarly")
def test_scholar_handles_rate_limit(mock_scholarly):
    mock_scholarly.search_pubs.side_effect = Exception("429 Too Many Requests")

    collector = ScholarCollector.__new__(ScholarCollector)
    results = collector.search("EDS pain")
    assert results == []


@patch("eds_researcher.collectors.scholar.scholarly")
def test_scholar_search_safe(mock_scholarly):
    mock_scholarly.search_pubs.side_effect = Exception("Blocked")

    collector = ScholarCollector.__new__(ScholarCollector)
    results = collector.search_safe("EDS pain")
    assert results == []
