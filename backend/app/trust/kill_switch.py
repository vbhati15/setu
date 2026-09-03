"""Global kill switch: a single in-process flag that halts all new
transaction processing the instant it's activated. Checked first, before
any other trust check, in `TrustGuard.authorize_purchase` -- so a triggered
kill switch blocks new purchases even for otherwise perfectly valid,
in-scope, in-policy requests.

In-memory and per-process by design (matches this deployment: one Render
web service instance). Toggled via `POST /admin/kill-switch/{activate,
deactivate}` in `main.py`.
"""
from __future__ import annotations

import threading
import time


class KillSwitch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._reason: str | None = None
        self._activated_at: float | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def activate(self, reason: str = "manually triggered") -> None:
        with self._lock:
            self._active = True
            self._reason = reason
            self._activated_at = time.time()

    def deactivate(self) -> None:
        with self._lock:
            self._active = False
            self._reason = None
            self._activated_at = None

    def status(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "reason": self._reason,
                "activated_at": self._activated_at,
            }
