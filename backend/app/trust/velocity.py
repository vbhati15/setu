"""Velocity limiting: caps how many purchase attempts one agent can make per
sliding time window. Config-driven (`max_purchases_per_minute/hour` in
Settings). Exceeding either window blocks/escalates that agent's requests
until enough time has passed for the window to fall below the cap again --
there is no separate reset timer to wait out, so recovery is immediate once
the oldest attempts age out.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class VelocityLimiter:
    def __init__(self, max_per_minute: int, max_per_hour: int) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._lock = threading.Lock()
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, agent_id: str, *, now: float | None = None) -> tuple[bool, str | None]:
        """Read-only check: does the agent have room for one more attempt
        right now? Does not record the attempt."""
        now = now if now is not None else time.time()
        with self._lock:
            attempts = self._attempts[agent_id]
            self._evict_stale(attempts, now)

            last_minute = sum(1 for t in attempts if now - t <= 60)
            if last_minute >= self.max_per_minute:
                return False, (
                    f"agent '{agent_id}' exceeded velocity limit: "
                    f"{last_minute}/{self.max_per_minute} purchase attempts in the last minute"
                )
            last_hour = len(attempts)
            if last_hour >= self.max_per_hour:
                return False, (
                    f"agent '{agent_id}' exceeded velocity limit: "
                    f"{last_hour}/{self.max_per_hour} purchase attempts in the last hour"
                )
            return True, None

    def record(self, agent_id: str, *, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        with self._lock:
            self._attempts[agent_id].append(now)

    @staticmethod
    def _evict_stale(attempts: deque[float], now: float) -> None:
        while attempts and now - attempts[0] > 3600:
            attempts.popleft()
