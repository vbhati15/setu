from backend.app.llm.base import LLMClient
from backend.app.llm.gemini_client import GeminiClient

__all__ = ["LLMClient", "GeminiClient", "get_llm_client"]


def get_llm_client() -> LLMClient:
    """Provider-swap point: today this always returns GeminiClient. Swapping
    providers later means changing only this function, not agent logic."""
    return GeminiClient()
