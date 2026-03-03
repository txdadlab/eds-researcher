"""Reddit collector using PRAW."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

import praw

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ["ehlersdanlos", "eds", "ChronicPain", "autism", "Nootropics"]


class RedditCollector(Collector):
    source_type = "reddit"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        subreddits: list[str] | None = None,
        time_filter: str = "month",
    ):
        self.reddit = praw.Reddit(
            client_id=client_id or os.getenv("REDDIT_CLIENT_ID", ""),
            client_secret=client_secret or os.getenv("REDDIT_CLIENT_SECRET", ""),
            user_agent=user_agent or os.getenv("REDDIT_USER_AGENT", "eds-researcher/0.1.0"),
        )
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.time_filter = time_filter

    def search(self, query: str, max_results: int = 25) -> list[RawFinding]:
        findings = []
        per_sub = max(1, max_results // len(self.subreddits))

        for sub_name in self.subreddits:
            try:
                subreddit = self.reddit.subreddit(sub_name)
                for submission in subreddit.search(
                    query, sort="relevance", time_filter=self.time_filter, limit=per_sub
                ):
                    findings.append(self._parse_submission(submission, sub_name))
            except Exception:
                logger.warning(f"Failed to search r/{sub_name}", exc_info=True)
                continue

        return findings[:max_results]

    def _parse_submission(self, submission, subreddit: str) -> RawFinding:
        # Combine title + selftext for content
        content_parts = [submission.title]
        if submission.selftext:
            content_parts.append(submission.selftext[:2000])  # Cap length

        # Get top comments for additional context
        submission.comment_sort = "best"
        submission.comments.replace_more(limit=0)
        top_comments = []
        for comment in submission.comments[:5]:
            if hasattr(comment, "body") and len(comment.body) > 20:
                top_comments.append(comment.body[:500])

        if top_comments:
            content_parts.append("\n--- Top comments ---\n")
            content_parts.extend(top_comments)

        created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).date()

        return RawFinding(
            source_type=self.source_type,
            source_url=f"https://reddit.com{submission.permalink}",
            title=submission.title,
            content="\n\n".join(content_parts),
            date=created,
            metadata={
                "subreddit": subreddit,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": submission.upvote_ratio,
                "top_comment_count": len(top_comments),
            },
        )
