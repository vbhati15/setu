"""Cumulative daily spend cap per agent: bounds total spend across many
individually-valid transactions, not just any single transaction's size
(`PolicyEngine`/credential scope) or attempt count (`VelocityLimiter`). A
sequence of transactions that each pass every other check can still add up
to more than an agent should be trusted with in a day.

Rolling 24-hour window per agent, keyed off actual charged amounts -- only
transactions that actually completed should count, so this is recorded by
the caller after a purchase succeeds, not on every attempt (see
`TrustGuard.record_spend`).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

DAY_SECONDS = 86_400


class DailySpendTracker:
    def __init__(self, window_seconds: float = DAY_SECONDS) -> None:
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, deque[tuple[float, int]]] = defaultdict(deque)

    def total_spent(self, agent_id: str, *, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        with self._lock:
            entries = self._entries[agent_id]
            self._evict_stale(entries, now)
            return sum(amount for _, amount in entries)

    def check(
        self, agent_id: str, amount_paise: int, cap_paise: int, *, now: float | None = None
    ) -> tuple[bool, str | None]:
        """Read-only: would adding `amount_paise` to what this agent has
        already spent in the last 24h push it over `cap_paise`? Does not
        record anything."""
        now = now if now is not None else time.time()
        already_spent = self.total_spent(agent_id, now=now)
        projected = already_spent + amount_paise
        if projected > cap_paise:
            return False, (
                f"agent '{agent_id}' would exceed its daily spend cap: "
                f"{already_spent} paise already spent in the last 24h + {amount_paise} paise "
                f"requested = {projected} paise, cap is max_daily_spend_paise={cap_paise} paise"
            )
        return True, None

    def record(self, agent_id: str, amount_paise: int, *, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        with self._lock:
            self._entries[agent_id].append((now, amount_paise))

    def _evict_stale(self, entries: deque[tuple[float, int]], now: float) -> None:
        while entries and now - entries[0][0] > self.window_seconds:
            entries.popleft()
