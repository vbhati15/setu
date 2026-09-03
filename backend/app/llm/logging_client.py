"""Wraps any LLMClient to log latency and estimated token cost per call.

Token counts are estimated (chars / 4, the standard rough heuristic) rather
than read from the provider response, since `LLMClient.generate_text` /
`generate_json` return plain values, not usage metadata. Cost is computed
against Gemini 2.0 Flash's *paid-tier* per-token rate for illustrative
purposes -- actual calls in this project run on the free tier, so real spend
is $0, but the estimate is still useful for judging what a negotiation loop
would cost at scale.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.llm.base import LLMClient

# Gemini 2.0 Flash paid-tier rates, USD per 1K tokens (illustrative only).
_INPUT_RATE_PER_1K = 0.0001
_OUTPUT_RATE_PER_1K = 0.0004


@dataclass
class LLMCallLog:
    kind: str  # "json" | "text"
    purpose: str
    latency_ms: float
    est_input_tokens: int
    est_output_tokens: int
    est_cost_usd: float


@dataclass
class LoggingLLMClient(LLMClient):
    inner: LLMClient
    calls: list[LLMCallLog] = field(default_factory=list)

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict, purpose: str = "unspecified") -> dict:
        return self._timed(
            kind="json",
            purpose=purpose,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            call=lambda: self.inner.generate_json(system_prompt, user_prompt, schema),
            serialize=json.dumps,
        )

    def generate_text(self, system_prompt: str, user_prompt: str, purpose: str = "unspecified") -> str:
        return self._timed(
            kind="text",
            purpose=purpose,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            call=lambda: self.inner.generate_text(system_prompt, user_prompt),
            serialize=str,
        )

    def _timed(self, *, kind, purpose, system_prompt, user_prompt, call, serialize):
        start = time.perf_counter()
        result = call()
        latency_ms = (time.perf_counter() - start) * 1000

        est_input_tokens = max(1, len(system_prompt + user_prompt) // 4)
        est_output_tokens = max(1, len(serialize(result)) // 4)
        est_cost_usd = (
            est_input_tokens / 1000 * _INPUT_RATE_PER_1K + est_output_tokens / 1000 * _OUTPUT_RATE_PER_1K
        )

        log = LLMCallLog(
            kind=kind,
            purpose=purpose,
            latency_ms=round(latency_ms, 1),
            est_input_tokens=est_input_tokens,
            est_output_tokens=est_output_tokens,
            est_cost_usd=round(est_cost_usd, 6),
        )
        self.calls.append(log)
        return result

    def total_cost_usd(self) -> float:
        return round(sum(c.est_cost_usd for c in self.calls), 6)

    def total_latency_ms(self) -> float:
        return round(sum(c.latency_ms for c in self.calls), 1)
