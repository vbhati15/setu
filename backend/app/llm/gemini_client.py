"""Gemini implementation of LLMClient, using Google's `google-genai` SDK.

Uses the free-tier Gemini API. Credentials/model name come from Settings.
"""
from __future__ import annotations

import json

from google import genai
from google.genai import types

from app.config import get_settings
from app.llm.base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
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
