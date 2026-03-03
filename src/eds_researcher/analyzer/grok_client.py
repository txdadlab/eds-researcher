"""xAI Grok API client wrapper using OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GrokClient:
    """Wrapper around xAI's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
        screening_model: str = "grok-3-mini-fast",
        analysis_model: str = "grok-3-mini",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        self.client = OpenAI(
            api_key=api_key or os.getenv("XAI_API_KEY", ""),
            base_url=base_url,
        )
        self.screening_model = screening_model
        self.analysis_model = analysis_model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
    def complete(
        self,
        prompt: str,
        system: str = "",
        model: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """Send a chat completion request and return the response text."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": model or self.screening_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def complete_json(
        self,
        prompt: str,
        system: str = "",
        model: str | None = None,
    ) -> dict | list:
        """Send a completion request and parse the response as JSON."""
        raw = self.complete(prompt, system=system, model=model, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            logger.error(f"Failed to parse JSON from Grok response: {raw[:200]}")
            return {}
