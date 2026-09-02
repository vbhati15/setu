"""In-process fake Razorpay client for unattended automated flows.

The real `RazorpayClient` (razorpay_client.py) requires the Checkout widget
and a manual test-card click-through -- fine for the one-off live-integration
demo, unusable for an automated negotiation loop or a test suite. This fake
implements the same surface the Merchant Agent's payment verification path
needs (create an order, "pay" it, fetch it back, verify its signature) purely
in memory, deterministically, with no network calls.

A single instance must be shared between the paying side (Buyer Agent) and
the verifying side (Merchant Agent) -- in production both talk to the same
real Razorpay service; here this object models that shared service.
"""
from __future__ import annotations

import hashlib
import itertools


class FakeRazorpayClient:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._payments: dict[str, dict] = {}

    def create_order(self, amount_paise: int, currency: str = "INR", receipt: str | None = None,
                      notes: dict | None = None) -> dict:
        if amount_paise <= 0:
            raise ValueError("amount_paise must be positive")
        order_id = f"order_fake_{next(self._ids)}"
        return {"id": order_id, "amount": amount_paise, "currency": currency, "status": "created"}

    def pay_order(self, order_id: str, amount_paise: int, payer_email: str = "buyer-agent@setu.test") -> dict:
        """Simulates a successful, captured payment against an order --
        stands in for a completed Checkout flow. Returns the fields a
        buyer needs to build an X-PAYMENT header."""
        payment_id = f"pay_fake_{next(self._ids)}"
        signature = self._signature(order_id, payment_id)
        self._payments[payment_id] = {
            "order_id": order_id,
            "amount": amount_paise,
            "status": "captured",
            "email": payer_email,
        }
        return {"order_id": order_id, "payment_id": payment_id, "signature": signature}

    def fetch_payment(self, payment_id: str) -> dict:
        return self._payments[payment_id]

    def fetch_order(self, order_id: str) -> dict:
        for payment in self._payments.values():
            if payment["order_id"] == order_id:
                return {"id": order_id, "amount": payment["amount"], "status": "paid"}
        return {"id": order_id, "status": "created"}

    def capture_payment(self, payment_id: str, amount_paise: int, currency: str = "INR") -> dict:
        payment = self._payments[payment_id]
        payment["status"] = "captured"
        return payment

    def verify_payment_signature(self, params: dict) -> bool:
        expected = self._signature(params.get("razorpay_order_id", ""), params.get("razorpay_payment_id", ""))
        return params.get("razorpay_signature") == expected

    @staticmethod
    def _signature(order_id: str, payment_id: str) -> str:
        return hashlib.sha256(f"{order_id}:{payment_id}".encode()).hexdigest()[:32]
