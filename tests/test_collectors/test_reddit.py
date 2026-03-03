"""Tests for Reddit collector with mocked PRAW responses."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from eds_researcher.collectors.reddit import RedditCollector


def _make_submission(title="Test post", selftext="Body text", score=50, num_comments=10):
    sub = MagicMock()
    sub.title = title
    sub.selftext = selftext
    sub.score = score
    sub.num_comments = num_comments
    sub.upvote_ratio = 0.95
    sub.permalink = "/r/ehlersdanlos/comments/abc123/test_post/"
    sub.created_utc = datetime(2025, 3, 15, tzinfo=timezone.utc).timestamp()
    sub.comment_sort = "best"

    # Mock comments
    comment = MagicMock()
    comment.body = "This really helped me too, I've been taking magnesium for months"
    sub.comments = MagicMock()
    sub.comments.replace_more = MagicMock()
    sub.comments.__iter__ = MagicMock(return_value=iter([comment]))
    sub.comments.__getitem__ = MagicMock(return_value=[comment])

    return sub


@patch("eds_researcher.collectors.reddit.praw.Reddit")
def test_reddit_search(mock_reddit_cls):
    mock_reddit = MagicMock()
    mock_reddit_cls.return_value = mock_reddit

    mock_subreddit = MagicMock()
    mock_subreddit.search.return_value = [
        _make_submission("LDN for EDS pain", "Has anyone tried low-dose naltrexone?"),
    ]
    mock_reddit.subreddit.return_value = mock_subreddit

    collector = RedditCollector.__new__(RedditCollector)
    collector.reddit = mock_reddit
    collector.subreddits = ["ehlersdanlos"]
    collector.time_filter = "month"

    results = collector.search("LDN pain EDS", max_results=5)

    assert len(results) == 1
    assert results[0].source_type == "reddit"
    assert "LDN" in results[0].title
    assert "reddit.com" in results[0].source_url


@patch("eds_researcher.collectors.reddit.praw.Reddit")
def test_reddit_handles_subreddit_failure(mock_reddit_cls):
    mock_reddit = MagicMock()
    mock_reddit_cls.return_value = mock_reddit

    mock_subreddit = MagicMock()
    mock_subreddit.search.side_effect = Exception("Forbidden")
    mock_reddit.subreddit.return_value = mock_subreddit

    collector = RedditCollector.__new__(RedditCollector)
    collector.reddit = mock_reddit
    collector.subreddits = ["private_sub"]
    collector.time_filter = "month"

    results = collector.search("test query")
    assert results == []
