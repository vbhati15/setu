"""Merchant Agent: the x402-speaking counterparty a Buyer Agent negotiates with.

Responsibilities today (Day 1 scope):
  - Receive an x402-style resource request for a product_id.
  - Validate it against the catalog (the only source of truth for prices).
  - If unpaid: respond 402 with PaymentRequirements, optionally attaching a
    Gemini-generated but code-bounded upsell offer.
  - If paid (X-PAYMENT header present): verify the payment against Razorpay
    and respond 200 (or 402 again with an error) accordingly.

Nothing here does bargaining/negotiation — that's the Buyer Agent + Zeuthen
strategy, which is explicitly out of scope until Day 2/3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.catalog import Catalog, Product, get_catalog
from backend.app.config import Settings, get_settings
from backend.app.llm.base import LLMClient
from backend.app.razorpay_client import RazorpayClient
from backend.app.x402.protocol import (
    build_payment_required_body,
    decode_x_payment_header,
    encode_x_payment_response,
)
from backend.app.x402.schema import UpsellOffer

_PRODUCT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")

_UPSELL_SCHEMA = {
    "type": "object",
    "properties": {
        "offer_upsell": {"type": "boolean"},
        "product_id": {"type": "string"},
        "discount_percent": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["offer_upsell"],
}


@dataclass
class AgentResponse:
    status_code: int
    body: dict
    headers: dict = field(default_factory=dict)


class MerchantAgent:
    def __init__(
        self,
        catalog: Catalog | None = None,
        razorpay_client: RazorpayClient | None = None,
        llm_client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or get_catalog()
        self.razorpay_client = razorpay_client or RazorpayClient(self.settings)
        self.llm_client = llm_client
        self.resource_prefix = "/products/"

    # -- public API -----------------------------------------------------

    def handle_request(self, product_id: str, x_payment_header: str | None = None) -> AgentResponse:
        """Handle one x402 resource request. `product_id` and
        `x_payment_header` are both untrusted client input."""
        if not isinstance(product_id, str) or not _PRODUCT_ID_RE.match(product_id):
            return AgentResponse(status_code=400, body={"error": "invalid product_id format"})

        product = self.catalog.get(product_id)
        if product is None:
            return AgentResponse(status_code=404, body={"error": f"unknown product '{product_id}'"})

        resource = f"{self.resource_prefix}{product.id}"

        if not x_payment_header:
            return self._payment_required(product, resource)

        try:
            payment_header = decode_x_payment_header(x_payment_header)
        except ValueError as exc:
            return self._payment_required(product, resource, error=str(exc))

        if payment_header.resource != resource:
            return self._payment_required(
                product, resource, error="X-PAYMENT resource does not match requested product"
            )

        ok, reason, payer = self._verify_payment(product, payment_header)
        if not ok:
            return self._payment_required(product, resource, error=reason)

        return AgentResponse(
            status_code=200,
            body={
                "resource": resource,
                "product_id": product.id,
                "name": product.name,
                "access_granted": True,
                "transaction": payment_header.payload.payment_id,
            },
            headers={
                "X-PAYMENT-RESPONSE": encode_x_payment_response(
                    success=True,
                    transaction=payment_header.payload.payment_id,
                    payer=payer,
                )
            },
        )

    # -- internals --------------------------------------------------------

    def _payment_required(self, product: Product, resource: str, error: str | None = None) -> AgentResponse:
        upsell = self._maybe_build_upsell(product)
        body = build_payment_required_body(
            resource=resource,
            description=product.description,
            price_paise=product.price_paise,
            merchant_id=self.settings.merchant_id,
            category=product.category,
            upsell=upsell,
        )
        if error:
            body["error"] = error
        return AgentResponse(status_code=402, body=body)

    def _verify_payment(self, product: Product, payment_header) -> tuple[bool, str | None, str | None]:
        payload = payment_header.payload
        try:
            payment = self.razorpay_client.fetch_payment(payload.payment_id)
        except Exception as exc:  # pragma: no cover - network/SDK errors
            return False, f"could not verify payment: {exc}", None

        if payment.get("order_id") != payload.order_id:
            return False, "payment order_id does not match X-PAYMENT payload", None
        if int(payment.get("amount", 0)) != product.price_paise:
            return False, "payment amount does not match product price", None
        if payment.get("status") not in ("captured", "authorized"):
            return False, f"payment status is '{payment.get('status')}', not captured", None

        signature_ok = self.razorpay_client.verify_payment_signature(
            {
                "razorpay_order_id": payload.order_id,
                "razorpay_payment_id": payload.payment_id,
                "razorpay_signature": payload.signature,
            }
        )
        if not signature_ok:
            return False, "payment signature verification failed", None

        return True, None, payment.get("email") or payment.get("contact")

    def _maybe_build_upsell(self, product: Product) -> UpsellOffer | None:
        if self.llm_client is None:
            return None

        related = self.catalog.related(product.id)
        if not related:
            return None

        # Only trusted, already-validated catalog data goes into the prompt.
        related_summaries = [
            {"id": p.id, "name": p.name, "price_paise": p.price_paise} for p in related[:5]
        ]
        system_prompt = (
            "You are a merchant's upsell assistant. Given a product a buyer is about to "
            "purchase and a short list of related products, decide whether to offer ONE "
            "of the related products as a bounded-discount upsell. You may only choose a "
            "product_id from the provided list. Never invent products or prices. "
            f"discount_percent must never exceed {self.settings.max_upsell_discount_percent}."
        )
        user_prompt = (
            f"Buyer is purchasing: {product.name} (id={product.id}, category={product.category}).\n"
            f"Related products available: {related_summaries}\n"
            "Respond with the required JSON schema only."
        )
        try:
            result = self.llm_client.generate_json(system_prompt, user_prompt, _UPSELL_SCHEMA)
        except Exception:
            # LLM failure should never break the core payment flow.
            return None

        if not result.get("offer_upsell"):
            return None

        candidate_id = result.get("product_id")
        candidate = next((p for p in related if p.id == candidate_id), None)
        if candidate is None:
            return None  # Gemini picked something outside the whitelist -> ignore

        discount = result.get("discount_percent", 0)
        try:
            discount = int(discount)
        except (TypeError, ValueError):
            discount = 0
        discount = max(0, min(discount, self.settings.max_upsell_discount_percent))

        discounted_price = candidate.price_paise * (100 - discount) // 100
        reason = str(result.get("reason", ""))[:200]

        return UpsellOffer(
            productId=candidate.id,
            name=candidate.name,
            originalPricePaise=candidate.price_paise,
            discountedPricePaise=discounted_price,
            discountPercent=discount,
            reason=reason,
        )
