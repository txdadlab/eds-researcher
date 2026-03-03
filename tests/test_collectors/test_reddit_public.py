"""Tests for Reddit public JSON API collector with mocked responses."""

from datetime import date, timezone
from unittest.mock import MagicMock, patch

from eds_researcher.collectors.reddit_public import RedditPublicCollector

MOCK_SEARCH_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Low dose naltrexone changed my life with EDS pain",
                    "selftext": "I've been taking LDN for 6 months now and the joint pain has decreased significantly. My rheumatologist recommended it after other treatments failed.",
                    "created_utc": 1700000000.0,
                    "permalink": "/r/ehlersdanlos/comments/abc123/low_dose_naltrexone/",
                    "score": 142,
                    "num_comments": 47,
                    "upvote_ratio": 0.96,
                    "subreddit": "ehlersdanlos",
                }
            },
            {
                "data": {
                    "title": "Magnesium glycinate for neuropathy - anyone tried it?",
                    "selftext": "My PT suggested magnesium glycinate for the tingling in my hands.",
                    "created_utc": 1699900000.0,
                    "permalink": "/r/ehlersdanlos/comments/def456/magnesium/",
                    "score": 38,
                    "num_comments": 12,
                    "upvote_ratio": 0.92,
                    "subreddit": "ehlersdanlos",
                }
            },
        ]
    }
}

MOCK_EMPTY_RESPONSE = {"data": {"children": []}}


@patch("eds_researcher.collectors.reddit_public.requests.Session")
def test_reddit_public_search(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = _mock_response(200, MOCK_SEARCH_RESPONSE)

    collector = RedditPublicCollector(subreddits=["ehlersdanlos"], time_filter="month")
    results = collector.search("EDS pain", max_results=10)

    assert len(results) == 2
    assert results[0].source_type == "reddit"
    assert "naltrexone" in results[0].title.lower()
    assert results[0].metadata["score"] == 142
    assert results[0].metadata["subreddit"] == "ehlersdanlos"
    assert "reddit.com" in results[0].source_url
    assert results[0].date == date(2023, 11, 14)


@patch("eds_researcher.collectors.reddit_public.requests.Session")
def test_reddit_public_empty_results(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = _mock_response(200, MOCK_EMPTY_RESPONSE)

    collector = RedditPublicCollector(subreddits=["ehlersdanlos"])
    results = collector.search("nonexistent_topic_xyz", max_results=5)
    assert results == []


@patch("eds_researcher.collectors.reddit_public.requests.Session")
def test_reddit_public_handles_http_error(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    resp = MagicMock()
    resp.status_code = 429
    resp.raise_for_status.side_effect = Exception("Too Many Requests")
    session.get.return_value = resp

    collector = RedditPublicCollector(subreddits=["ehlersdanlos"])
    results = collector.search_safe("EDS pain")
    assert results == []


@patch("eds_researcher.collectors.reddit_public.requests.Session")
def test_reddit_public_multiple_subreddits(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = _mock_response(200, MOCK_SEARCH_RESPONSE)

    collector = RedditPublicCollector(
        subreddits=["ehlersdanlos", "ChronicPain"], time_filter="year"
    )
    results = collector.search("pain management", max_results=10)

    # Should have called get twice (once per subreddit)
    assert session.get.call_count == 2
    assert len(results) == 4  # 2 results per subreddit


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp
