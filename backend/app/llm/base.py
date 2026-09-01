"""Provider-agnostic LLM client interface.

Agent code (merchant_agent, and later buyer_agent) should depend only on
this interface, never on a specific provider SDK. To swap providers, write a
new class implementing LLMClient and change the one line in llm/__init__.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        """Generate a response constrained to the given JSON schema and return
        it as a parsed dict. Raises on malformed/non-conforming output."""
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a free-text response."""
        raise NotImplementedError
