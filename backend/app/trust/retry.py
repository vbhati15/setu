"""Retry-with-backoff for calls to an external payment provider (the
Razorpay client). A timeout/transient error should be retried a bounded
number of times with exponential backoff, not left to hang or crash the
request -- but a definitive rejection (bad signature, amount mismatch)
should never be retried, since retrying a wrong answer just returns the
same wrong answer.
"""
from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryExhausted(Exception):
    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(f"gave up after {attempts} attempt(s): {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.05,
    max_delay_seconds: float = 2.0,
    retriable_exceptions: tuple[type[Exception], ...] = (TimeoutError, ConnectionError, OSError),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Calls `fn()`, retrying on any exception matching
    `retriable_exceptions` with exponential backoff + jitter. Re-raises the
    last error once `max_attempts` is exhausted. Any exception not in
    `retriable_exceptions` propagates immediately, unretried."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retriable_exceptions as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.1)
            sleep(delay)
    assert last_error is not None
    raise RetryExhausted(max_attempts, last_error)
