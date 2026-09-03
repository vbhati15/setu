"""Idempotency store: dedupes purchase requests by client-supplied key.

If the same `idempotency_key` is seen twice, the second call returns the
first call's stored result instead of re-running the purchase -- this must
be checked *before* any order is created or payment attempted, not after,
otherwise a "duplicate" has already caused a real charge.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class IdempotencyRecord:
    result: Any
    is_replay: bool = False


class IdempotencyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, Any] = {}

    def get(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            if key in self._results:
                return IdempotencyRecord(result=self._results[key], is_replay=True)
            return None

    def store(self, key: str, result: Any) -> None:
        with self._lock:
            self._results[key] = result
