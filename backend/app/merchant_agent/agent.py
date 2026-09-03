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

import logging
import re
from dataclasses import dataclass, field

from app.bargaining import MerchantParty
from app.catalog import Catalog, Product, get_catalog
from app.config import Settings, get_settings
from app.llm.base import LLMClient
from app.razorpay_client import RazorpayClient
from app.trust.guard import AuthorizationResult, TrustGuard
from app.trust.identity import AgentCredential, SignedRequest
from app.trust.retry import RetryExhausted, retry_with_backoff
from app.x402.protocol import (
    build_payment_required_body,
    decode_x_payment_header,
    encode_x_payment_response,
)
from app.x402.schema import UpsellOffer

logger = logging.getLogger("setu.merchant_agent")

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
        trust_guard: TrustGuard | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or get_catalog()
        self.razorpay_client = razorpay_client or RazorpayClient(self.settings)
        self.llm_client = llm_client
        self.resource_prefix = "/products/"
        self.trust_guard = trust_guard or TrustGuard(settings=self.settings)

    # -- trust/identity ---------------------------------------------------

    def issue_credential(
        self,
        *,
        agent_id: str,
        public_key_b64: str,
        max_spend_paise: int,
        allowed_categories: list[str] | None = None,
        ttl_seconds: float | None = None,
    ) -> AgentCredential:
        """Onboards an agent (e.g. a Buyer Agent) by issuing it a scoped,
        expiring credential -- this merchant is the trust root for its own
        marketplace. See trust/identity.py."""
        return self.trust_guard.issuer.issue(
            agent_id=agent_id,
            public_key_b64=public_key_b64,
            max_spend_paise=max_spend_paise,
            allowed_categories=allowed_categories if allowed_categories is not None else list(self.settings.allowed_categories),
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.settings.agent_credential_ttl_seconds,
        )

    def authorize_purchase(self, request: SignedRequest, *, category: str) -> AuthorizationResult:
        """Runs the full trust pipeline (kill switch, signature/credential
        verification, replay defense, credential scope, idempotency,
        velocity, policy bounds) for a purchase request. Does not itself
        charge anything -- callers still run the actual x402 payment flow
        via `handle_request` and must call `record_purchase_attempt` /
        `store_purchase_result` themselves once it settles."""
        return self.trust_guard.authorize_purchase(request, category=category)

    def record_purchase_attempt(self, agent_id: str) -> None:
        self.trust_guard.record_attempt(agent_id)

    def record_purchase_spend(self, agent_id: str, amount_paise: int) -> None:
        self.trust_guard.record_spend(agent_id, amount_paise)

    def store_purchase_result(self, idempotency_key: str, result) -> None:
        self.trust_guard.store_result(idempotency_key, result)

    # -- public API -----------------------------------------------------

    def handle_request(
        self,
        product_id: str,
        x_payment_header: str | None = None,
        agreed_price_paise: int | None = None,
    ) -> AgentResponse:
        """Handle one x402 resource request. `product_id` and
        `x_payment_header` are both untrusted client input.

        `agreed_price_paise` is set only for a purchase closing out a prior
        negotiation (see `negotiation_party`) -- when present, payment is
        verified against that agreed price instead of the catalog list
        price. It is never taken from client input; only code that already
        ran a Zeuthen negotiation to completion passes it."""
        if not isinstance(product_id, str) or not _PRODUCT_ID_RE.match(product_id):
            return AgentResponse(status_code=400, body={"error": "invalid product_id format"})

        product = self.catalog.get(product_id)
        if product is None:
            return AgentResponse(status_code=404, body={"error": f"unknown product '{product_id}'"})

        resource = f"{self.resource_prefix}{product.id}"
        expected_price_paise = agreed_price_paise if agreed_price_paise is not None else product.price_paise

        if not x_payment_header:
            return self._payment_required(product, resource, expected_price_paise=expected_price_paise)

        try:
            payment_header = decode_x_payment_header(x_payment_header)
        except ValueError as exc:
            return self._payment_required(product, resource, expected_price_paise=expected_price_paise, error=str(exc))

        if payment_header.resource != resource:
            return self._payment_required(
                product, resource, expected_price_paise=expected_price_paise,
                error="X-PAYMENT resource does not match requested product",
            )

        ok, reason, payer = self._verify_payment(product, payment_header, expected_price_paise)
        if not ok:
            return self._payment_required(product, resource, expected_price_paise=expected_price_paise, error=reason)

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

    def min_acceptable_price(self, product: Product) -> int:
        """Merchant's reservation price: won't sell below this. A configured
        fraction of catalog list price -- see `merchant_min_price_factor` in
        Settings and BARGAINING.md for why this is a single global fraction
        rather than a per-product floor."""
        return max(1, round(product.price_paise * self.settings.merchant_min_price_factor))

    def negotiation_party(self, product_id: str) -> MerchantParty | None:
        """Returns this merchant's Zeuthen utility function for `product_id`,
        for a Buyer Agent to negotiate against. Returns None for an unknown
        product -- deterministic, no LLM call."""
        product = self.catalog.get(product_id)
        if product is None:
            return None
        return MerchantParty(min_price_paise=self.min_acceptable_price(product), list_price_paise=product.price_paise)

    # -- internals --------------------------------------------------------

    def _payment_required(
        self, product: Product, resource: str, expected_price_paise: int | None = None, error: str | None = None
    ) -> AgentResponse:
        upsell = self._maybe_build_upsell(product)
        body = build_payment_required_body(
            resource=resource,
            description=product.description,
            price_paise=expected_price_paise if expected_price_paise is not None else product.price_paise,
            merchant_id=self.settings.merchant_id,
            category=product.category,
            upsell=upsell,
        )
        if error:
            body["error"] = error
        return AgentResponse(status_code=402, body=body)

    def _verify_payment(
        self, product: Product, payment_header, expected_price_paise: int
    ) -> tuple[bool, str | None, str | None]:
        payload = payment_header.payload
        try:
            payment = retry_with_backoff(
                lambda: self.razorpay_client.fetch_payment(payload.payment_id),
                retriable_exceptions=(TimeoutError, ConnectionError, OSError),
            )
        except RetryExhausted as exc:
            logger.warning("payment verification failed after retries: %s", exc)
            return False, f"could not verify payment after retries: {exc.last_error}", None
        except Exception as exc:  # pragma: no cover - non-retriable SDK errors
            return False, f"could not verify payment: {exc}", None

        if payment.get("order_id") != payload.order_id:
            return False, "payment order_id does not match X-PAYMENT payload", None
        if int(payment.get("amount", 0)) != expected_price_paise:
            return False, "payment amount does not match agreed price", None
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
