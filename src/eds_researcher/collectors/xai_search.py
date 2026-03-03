"""X/Twitter search collector using xAI API's built-in search tools."""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from openai import OpenAI

from eds_researcher.memory.models import RawFinding

from .base import Collector

logger = logging.getLogger(__name__)


class XAISearchCollector(Collector):
    """Uses xAI's Grok API with built-in x_search and web_search tools."""

    source_type = "xai_search"

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.x.ai/v1"):
        self.client = OpenAI(
            api_key=api_key or os.getenv("XAI_API_KEY", ""),
            base_url=base_url,
        )

    def search(self, query: str, max_results: int = 20) -> list[RawFinding]:
        """Use Grok with x_search tool to find relevant X/Twitter posts and web content."""
        findings = []

        # X/Twitter search
        findings.extend(self._x_search(query, max_results))

        # Web search for additional context
        findings.extend(self._web_search(query, max(5, max_results // 4)))

        return findings[:max_results]

    def _x_search(self, query: str, max_results: int) -> list[RawFinding]:
        """Search X/Twitter via Grok's built-in x_search tool."""
        try:
            response = self.client.chat.completions.create(
                model="grok-3-mini-fast",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search X/Twitter for posts about: {query}\n\n"
                        f"Find up to {max_results} relevant posts. For each post found, provide:\n"
                        "1. The post URL\n"
                        "2. The author's username\n"
                        "3. The full post text\n"
                        "4. The date posted\n\n"
                        "Format as JSON array with keys: url, author, text, date"
                    ),
                }],
                tools=[{"type": "function", "function": {"name": "x_search", "parameters": {}}}],
                temperature=0.1,
            )
            return self._parse_search_response(response, "xai_x")
        except Exception:
            logger.warning("x_search failed", exc_info=True)
            return []

    def _web_search(self, query: str, max_results: int) -> list[RawFinding]:
        """Search the web via Grok's built-in web_search tool."""
        try:
            response = self.client.chat.completions.create(
                model="grok-3-mini-fast",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search the web for: {query}\n\n"
                        f"Find up to {max_results} relevant results. For each result, provide:\n"
                        "1. The page URL\n"
                        "2. The page title\n"
                        "3. A summary of relevant content\n"
                        "4. The date if available\n\n"
                        "Format as JSON array with keys: url, title, summary, date"
                    ),
                }],
                tools=[{"type": "function", "function": {"name": "web_search", "parameters": {}}}],
                temperature=0.1,
            )
            return self._parse_search_response(response, "xai_web")
        except Exception:
            logger.warning("web_search failed", exc_info=True)
            return []

    def _parse_search_response(self, response, sub_source: str) -> list[RawFinding]:
        """Parse Grok's response containing search results."""
        findings = []
        content = response.choices[0].message.content or ""

        # Try to extract JSON from the response
        parsed = False
        try:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                items = json.loads(content[start:end])
                for item in items:
                    findings.append(RawFinding(
                        source_type=self.source_type,
                        source_url=item.get("url", ""),
                        title=item.get("title", item.get("author", "")),
                        content=item.get("summary", item.get("text", "")),
                        date=self._parse_date(item.get("date")),
                        metadata={"sub_source": sub_source},
                    ))
                parsed = True
        except (json.JSONDecodeError, AttributeError):
            pass

        # If no JSON found/parsed, treat the whole response as one finding
        if not parsed and content.strip():
            findings.append(RawFinding(
                source_type=self.source_type,
                source_url="",
                title="xAI search results for query",
                content=content,
                date=date.today(),
                metadata={"sub_source": sub_source, "raw_response": True},
            ))

        return findings

    def _parse_date(self, date_str: str | None) -> date | None:
        if not date_str:
            return None
        try:
            return date.fromisoformat(date_str[:10])
        except (ValueError, TypeError):
            return None
