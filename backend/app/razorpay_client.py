"""Thin wrapper around the official Razorpay Python SDK.

All credentials come from Settings (config.py) — never hardcoded here.
"""
from __future__ import annotations

import razorpay

from backend.app.config import Settings, get_settings


class RazorpayClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = razorpay.Client(
            auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret)
        )

    def create_order(self, amount_paise: int, currency: str = "INR", receipt: str | None = None,
                      notes: dict | None = None) -> dict:
        """Create a Razorpay order. amount_paise is INR * 100 (Razorpay's unit)."""
        if amount_paise <= 0:
            raise ValueError("amount_paise must be positive")
        if amount_paise > self.settings.max_single_transaction_paise:
            raise ValueError(
                f"amount_paise {amount_paise} exceeds configured "
                f"max_single_transaction_paise {self.settings.max_single_transaction_paise}"
            )
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "payment_capture": 1,
        }
        if receipt:
            payload["receipt"] = receipt
        if notes:
            payload["notes"] = notes
        return self._client.order.create(data=payload)

    def fetch_payment(self, payment_id: str) -> dict:
        return self._client.payment.fetch(payment_id)

    def fetch_order(self, order_id: str) -> dict:
        return self._client.order.fetch(order_id)

    def capture_payment(self, payment_id: str, amount_paise: int, currency: str = "INR") -> dict:
        return self._client.payment.capture(payment_id, amount_paise, {"currency": currency})

    def verify_payment_signature(self, params: dict) -> bool:
        """params must contain razorpay_order_id, razorpay_payment_id, razorpay_signature."""
        try:
            self._client.utility.verify_payment_signature(params)
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
