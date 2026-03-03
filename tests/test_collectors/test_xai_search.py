"""Tests for xAI search collector with mocked API responses."""

from unittest.mock import MagicMock, patch

from eds_researcher.collectors.xai_search import XAISearchCollector


def _mock_response(content: str):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp.choices = [choice]
    return resp


@patch("eds_researcher.collectors.xai_search.OpenAI")
def test_xai_search_parses_json(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    json_response = """Here are the results:
[
  {"url": "https://x.com/user/status/123", "author": "@edswarrior", "text": "LDN has been amazing for my EDS pain", "date": "2025-02-15"},
  {"url": "https://x.com/user/status/456", "author": "@chronicpain", "text": "Magnesium glycinate changed my life", "date": "2025-01-20"}
]"""
    mock_client.chat.completions.create.return_value = _mock_response(json_response)

    collector = XAISearchCollector.__new__(XAISearchCollector)
    collector.client = mock_client

    results = collector._x_search("EDS pain treatment", max_results=5)

    assert len(results) == 2
    assert results[0].source_url == "https://x.com/user/status/123"
    assert "LDN" in results[0].content


@patch("eds_researcher.collectors.xai_search.OpenAI")
def test_xai_search_handles_non_json(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_response(
        "I found several posts about EDS treatments but cannot format as JSON."
    )

    collector = XAISearchCollector.__new__(XAISearchCollector)
    collector.client = mock_client

    results = collector._x_search("EDS", max_results=5)

    # Should still return something — the raw text as a single finding
    assert len(results) == 1
    assert results[0].metadata.get("raw_response") is True


@patch("eds_researcher.collectors.xai_search.OpenAI")
def test_xai_search_handles_api_error(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    collector = XAISearchCollector.__new__(XAISearchCollector)
    collector.client = mock_client

    results = collector._x_search("EDS", max_results=5)
    assert results == []
