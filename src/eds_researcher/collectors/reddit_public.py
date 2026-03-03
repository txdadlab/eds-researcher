"""Reddit collector using the public JSON API (no authentication required).

Appends .json to Reddit URLs to get structured data.
Rate limited to ~30 requests/minute — enforced via throttling.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

import requests

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ["ehlersdanlos", "eds", "ChronicPain", "autism", "Nootropics"]

# Reddit blocks generic user-agents
USER_AGENT = "eds-researcher/0.1.0 (medical research; no auth)"


class RedditPublicCollector(Collector):
    """Searches Reddit via the public JSON API — no API key needed.

    Rate limit: ~30 requests/minute. We throttle to 2 seconds between requests
    to stay well within limits.
    """

    source_type = "reddit"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        time_filter: str = "month",
    ):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.time_filter = time_filter
        self._min_interval = 2.0  # seconds between requests
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _throttle(self) -> None:
        """Enforce rate limit between requests."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def search(self, query: str, max_results: int = 25) -> list[RawFinding]:
        findings = []
        per_sub = max(1, max_results // len(self.subreddits))

        for sub_name in self.subreddits:
            try:
                results = self._search_subreddit(sub_name, query, per_sub)
                findings.extend(results)
            except Exception:
                logger.warning(f"Failed to search r/{sub_name}", exc_info=True)
                continue

        return findings[:max_results]

    def _search_subreddit(
        self, subreddit: str, query: str, limit: int
    ) -> list[RawFinding]:
        self._throttle()

        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "sort": "relevance",
            "t": self.time_filter,
            "limit": min(limit, 25),  # Reddit caps at 25 per page for public API
            "restrict_sr": "on",
        }

        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        findings = []
        children = data.get("data", {}).get("children", [])
        for child in children:
            try:
                post = child.get("data", {})
                findings.append(self._parse_post(post, subreddit))
            except Exception:
                logger.debug("Failed to parse Reddit post", exc_info=True)

        return findings

    def _parse_post(self, post: dict, subreddit: str) -> RawFinding:
        title = post.get("title", "")
        selftext = post.get("selftext", "")

        content_parts = [title]
        if selftext:
            content_parts.append(selftext[:2000])

        created_utc = post.get("created_utc", 0)
        created = (
            datetime.fromtimestamp(created_utc, tz=timezone.utc).date()
            if created_utc
            else None
        )

        permalink = post.get("permalink", "")

        return RawFinding(
            source_type=self.source_type,
            source_url=f"https://reddit.com{permalink}" if permalink else "",
            title=title,
            content="\n\n".join(content_parts),
            date=created,
            metadata={
                "subreddit": subreddit,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
            },
        )
