"""Gemini implementation of LLMClient, using Google's `google-genai` SDK.

Uses the free-tier Gemini API. Credentials/model name come from Settings.
"""
from __future__ import annotations

import json

from google import genai
from google.genai import types

from backend.app.config import get_settings
from backend.app.llm.base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        settings = get_settings()
        # Without an explicit timeout, a single stalled/rate-limited call has
        # no upper bound -- and a tight-budget negotiation makes up to 32 of
        # these calls sequentially (2 per round, up to negotiation_max_rounds
        # rounds), so one slow call can stall the whole negotiation well past
        # what BuyerAgent's own fallback phrasing (see agent.py `_phrase`)
        # would ever need to kick in. `timeout` is in milliseconds.
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=settings.gemini_timeout_ms),
        )
        self._model = settings.gemini_model

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )
        text = (response.text or "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini returned non-JSON output: {text!r}") from exc

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
            ),
        )
        return (response.text or "").strip()
