"""Buyer Agent: negotiates with the Merchant Agent over the Day-1 x402 flow.

Division of labor (rules-first, LLM-as-fallback):
  - Product matching (does anything in the catalog fit the goal, within a
    plausible price ceiling) -- deterministic keyword match, no LLM call.
  - Whether an offer is affordable, whether negotiation has converged or
    deadlocked -- deterministic (see backend/app/bargaining/zeuthen.py),
    no LLM call.
  - The actual concession amounts each round -- the Zeuthen algorithm,
    no LLM call.
  - Turning a round's numbers into a natural-language offer/response
    message for the trace -- Gemini. This is flavor text for the log; it
    never feeds back into the negotiation math.

Payment is executed against a `FakeRazorpayClient` (see fake_razorpay.py) --
this loop is meant to run fully unattended, which the real Checkout widget
cannot do (see docs/DECISIONS.md, 2026-09-02).
"""
from __future__ import annotations

import base64
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from backend.app.bargaining import BuyerParty, RoundResult, clamp01, run_zeuthen_negotiation
from backend.app.catalog import Catalog, Product, get_catalog
from backend.app.checkout_quote import build_quote_token
from backend.app.config import Settings, get_settings
from backend.app.fake_razorpay import FakeRazorpayClient
from backend.app.formatting import format_rupees
from backend.app.llm.base import LLMClient
from backend.app.merchant_agent import MerchantAgent
from backend.app.trust.identity import AgentIdentity, build_signed_request

_STOPWORDS = {
    "a", "an", "the", "get", "buy", "for", "and", "of", "to", "in", "with",
    "under", "over", "budget", "preferred", "please", "want", "need", "ideally",
}

# Shopper-supplied context, both optional and both real levers, not cosmetic:
#
# `occasion` never touches the negotiation math -- it only flavors the
# system prompt handed to the phrasing LLM (see `_phrase`), so the same
# numbers get described differently ("as a gift" vs "for a work setup").
#
# `priority` genuinely changes the Zeuthen parameters this negotiation runs
# under (see `_priority_negotiation_params`) and how readily an upsell gets
# accepted (see `_upsell_buffer_fraction`) -- a harder-bargaining buyer opens
# lower and concedes less per round; a buyer who wants speed opens closer to
# a workable price and concedes more per round.
_OCCASION_NOTES = {
    "gift": "This purchase is a gift for someone else.",
    "personal": "This purchase is for the buyer's own personal use.",
    "work": "This purchase is for a work setup.",
    "browsing": "The buyer is just browsing and not in any hurry to commit.",
}

_PRIORITY_PARAMS = {
    # (opening_offer_fraction_of_budget, min_concession_multiplier, max_concession_multiplier)
    "best_price": (0.55, 0.85, 0.95),
    "fastest_deal": (0.8, 1.8, 1.3),
}
_DEFAULT_PRIORITY_PARAMS = (0.6, 1.0, 1.0)

_UPSELL_BUFFER_FRACTION = {
    # Fraction of the pre-upsell remaining budget that must be left
    # unspent for the upsell to be accepted. 0.0 (default) = accept
    # whenever it's affordable at all, same as before this field existed.
    "best_price": 0.5,
}


@dataclass
class NegotiationTrace:
    round_number: int
    speaker: str  # "buyer" | "merchant" | "system"
    message: str
    buyer_offer_paise: int | None = None
    merchant_offer_paise: int | None = None
    buyer_risk: float | None = None
    merchant_risk: float | None = None
    # Wall-clock time the phrasing LLM call for THIS message actually took,
    # measured around the real `generate_text` call in `_phrase`. None when
    # no LLM call happened for this line (no llm_client configured) --
    # never a guessed/fabricated number.
    latency_ms: float | None = None


@dataclass
class NegotiationOutcome:
    success: bool
    reason: str
    product: Product | None = None
    agreed_price_paise: int | None = None
    transaction_id: str | None = None
    upsell_purchased: bool = False
    upsell_product: Product | None = None
    rounds: list[RoundResult] = field(default_factory=list)
    trace: list[NegotiationTrace] = field(default_factory=list)
    # Set when a deal was reached with `auto_pay=False` (a human-triggered
    # negotiation): the price is agreed but nothing has been charged yet --
    # `checkout_token` is what the frontend hands to /checkout/order and
    # /checkout/confirm to complete a *real* Razorpay Checkout for exactly
    # this agreed price. See checkout_quote.py.
    payment_pending: bool = False
    checkout_token: str | None = None


class BuyerAgent:
    def __init__(
        self,
        merchant_agent: MerchantAgent,
        llm_client: LLMClient | None = None,
        razorpay_client: FakeRazorpayClient | None = None,
        catalog: Catalog | None = None,
        settings: Settings | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.merchant_agent = merchant_agent
        self.llm_client = llm_client
        self.razorpay_client = razorpay_client or FakeRazorpayClient()
        self.catalog = catalog or get_catalog()
        self.settings = settings or get_settings()

        # Signed identity: this agent is onboarded (issued a scoped, expiring
        # credential) by the merchant it will negotiate with. See
        # backend/app/trust/identity.py.
        self.identity = AgentIdentity.generate(agent_id or f"buyer-{uuid.uuid4().hex[:8]}")
        self.credential = self.merchant_agent.issue_credential(
            agent_id=self.identity.agent_id,
            public_key_b64=self.identity.public_key_b64,
            max_spend_paise=self.settings.max_single_transaction_paise,
        )

    # -- public API -------------------------------------------------------

    def negotiate_and_purchase(
        self,
        goal_text: str,
        budget_paise: int,
        product_id: str | None = None,
        occasion: str | None = None,
        priority: str | None = None,
        auto_pay: bool = True,
    ) -> NegotiationOutcome:
        """`auto_pay=True` (default -- the scenario harness and any other
        backend-automated caller) completes the purchase itself against
        `self.razorpay_client` (the fake rail for unattended flows -- see
        module docstring). `auto_pay=False` (the frontend's human-triggered
        "try it yourself"/"surprise me" flows) stops once a price is agreed
        and returns a `checkout_token` instead: a real human then completes
        a real Razorpay Checkout for that exact price via /checkout/order
        and /checkout/confirm, since an unattended agent can't click through
        Razorpay's own Checkout widget (see docs/DECISIONS.md)."""
        trace: list[NegotiationTrace] = []

        # A caller that already knows exactly which catalog product it wants
        # (e.g. the dashboard's product picker) pins that product directly,
        # bypassing keyword/price-ceiling matching entirely -- that matching
        # is a *discovery* aid for free-text goals, not a filter that should
        # override an explicit choice.
        if product_id is not None:
            candidate = self.catalog.get(product_id)
            if candidate is None:
                reason = f"no catalog product with id '{product_id}'"
                trace.append(NegotiationTrace(0, "system", reason))
                return NegotiationOutcome(success=False, reason=reason, trace=trace)
        else:
            candidate = self._find_candidate_product(goal_text, budget_paise)
            if candidate is None:
                reason = (
                    f"no catalog product matches goal '{goal_text}' within "
                    f"{self.settings.buyer_price_ceiling_factor}x budget ({format_rupees(budget_paise)})"
                )
                trace.append(NegotiationTrace(0, "system", reason))
                return NegotiationOutcome(success=False, reason=reason, trace=trace)

        quote = self.merchant_agent.handle_request(candidate.id)
        if quote.status_code != 402:
            reason = quote.body.get("error", f"merchant returned unexpected status {quote.status_code} for a quote")
            trace.append(NegotiationTrace(0, "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=candidate, trace=trace)
        list_price_paise = int(quote.body["accepts"][0]["maxAmountRequired"])
        match_note = f"Matched product '{candidate.name}' ({candidate.id}), list price {format_rupees(list_price_paise)}."
        occasion_note = _OCCASION_NOTES.get(occasion)
        if occasion_note:
            match_note += f" {occasion_note}"
        trace.append(NegotiationTrace(0, "system", match_note))

        if budget_paise >= list_price_paise:
            outcome = self._accept_list_price(candidate, list_price_paise, budget_paise, quote, trace, priority, auto_pay)
        else:
            outcome = self._negotiate(candidate, list_price_paise, budget_paise, trace, occasion, priority, auto_pay)

        return outcome

    # -- comfortable-budget path (no negotiation needed) -------------------

    def _accept_list_price(
        self,
        product: Product,
        list_price_paise: int,
        budget_paise: int,
        quote,
        trace,
        priority: str | None = None,
        auto_pay: bool = True,
    ) -> NegotiationOutcome:
        trace.append(
            NegotiationTrace(0, "buyer", f"Budget covers list price ({format_rupees(list_price_paise)}) -- accepting outright.")
        )

        if not auto_pay:
            # A real human will complete a real Razorpay Checkout for this
            # price via /checkout/order + /checkout/confirm -- upsell isn't
            # offered here since that would mean a second, separate real
            # charge in the same flow, out of scope for this handoff.
            trace.append(NegotiationTrace(0, "system", "Awaiting your payment to confirm this purchase."))
            return NegotiationOutcome(
                success=True,
                reason="list price accepted (comfortable budget) -- awaiting your payment",
                product=product,
                agreed_price_paise=list_price_paise,
                trace=trace,
                payment_pending=True,
                checkout_token=build_quote_token(product.id, list_price_paise),
            )

        purchase, failure_reason = self._pay_and_collect(product.id, list_price_paise, product.category)
        if purchase is None:
            reason = failure_reason or "payment/verification failed for list-price purchase"
            trace.append(NegotiationTrace(0, "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, trace=trace)

        outcome = NegotiationOutcome(
            success=True,
            reason="accepted list price (comfortable budget, no negotiation needed)",
            product=product,
            agreed_price_paise=list_price_paise,
            transaction_id=purchase,
            trace=trace,
        )

        upsell_body = quote.body.get("upsell")
        remaining_budget_paise = budget_paise - list_price_paise
        if upsell_body:
            self._maybe_accept_upsell(upsell_body, remaining_budget_paise, outcome, priority)

        return outcome

    def _maybe_accept_upsell(
        self, upsell_body: dict, remaining_budget_paise: int, outcome: NegotiationOutcome, priority: str | None = None
    ) -> None:
        upsell_product = self.catalog.get(upsell_body["productId"])
        if upsell_product is None:
            return
        discounted_price = int(upsell_body["discountedPricePaise"])
        outcome.trace.append(
            NegotiationTrace(
                0, "merchant",
                f"Upsell offered: {upsell_product.name} at {format_rupees(discounted_price)} "
                f"({upsell_body['discountPercent']}% off) -- {upsell_body.get('reason', '')}",
            )
        )
        # `best_price` holds back a chunk of the remaining budget instead of
        # spending it on an add-on the instant it's technically affordable --
        # everyone else (including no preference stated) keeps the original
        # "accept whenever it fits" behavior.
        buffer_fraction = _UPSELL_BUFFER_FRACTION.get(priority, 0.0)
        max_upsell_spend = round(remaining_budget_paise * (1 - buffer_fraction))
        if discounted_price > max_upsell_spend:
            reason = "exceeds remaining budget" if discounted_price > remaining_budget_paise else "held back for a better price"
            outcome.trace.append(NegotiationTrace(0, "buyer", f"Upsell declined -- {reason}."))
            return

        upsell_purchase, failure_reason = self._pay_and_collect(upsell_product.id, discounted_price, upsell_product.category)
        if upsell_purchase is None:
            reason = failure_reason or "Upsell purchase failed verification -- skipped."
            outcome.trace.append(NegotiationTrace(0, "system", reason))
            return

        outcome.trace.append(NegotiationTrace(0, "buyer", f"Upsell accepted: {upsell_product.name}."))
        outcome.upsell_purchased = True
        outcome.upsell_product = upsell_product

    # -- tight-budget path (real Zeuthen negotiation) ----------------------

    def _negotiate(
        self,
        product: Product,
        list_price_paise: int,
        budget_paise: int,
        trace,
        occasion: str | None = None,
        priority: str | None = None,
        auto_pay: bool = True,
    ) -> NegotiationOutcome:
        merchant_party = self.merchant_agent.negotiation_party(product.id)
        if merchant_party is None:
            reason = "merchant has no negotiation terms for this product"
            trace.append(NegotiationTrace(0, "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, trace=trace)

        buyer_party = BuyerParty(budget_paise=budget_paise)

        opening_fraction, min_mult, max_mult = _PRIORITY_PARAMS.get(priority, _DEFAULT_PRIORITY_PARAMS)
        # Deterministic opening lowball: leaves genuine room to negotiate up.
        # `priority` shifts the anchor itself (how aggressive the opening bid
        # is) and the concession bounds the whole negotiation runs under --
        # a real strategy change, not a cosmetic label.
        opening_buyer_offer = max(1, round(budget_paise * opening_fraction))
        opening_merchant_offer = list_price_paise
        min_concession_fraction = clamp01(self.settings.negotiation_min_concession_fraction * min_mult)
        max_concession_fraction = clamp01(self.settings.negotiation_max_concession_fraction * max_mult)

        rounds = run_zeuthen_negotiation(
            buyer=buyer_party,
            merchant=merchant_party,
            opening_buyer_offer_paise=opening_buyer_offer,
            opening_merchant_offer_paise=opening_merchant_offer,
            max_rounds=self.settings.negotiation_max_rounds,
            min_concession_fraction=min_concession_fraction,
            max_concession_fraction=max_concession_fraction,
            convergence_threshold_paise=round(list_price_paise * self.settings.negotiation_convergence_fraction),
            close_threshold_paise=self.settings.negotiation_close_threshold_paise,
        )

        self._render_trace(product, rounds, trace, occasion)

        last = rounds[-1]
        if not last.deal:
            if last.conceder == "max_rounds_exceeded":
                gap = last.merchant_offer_paise - last.buyer_offer_paise
                reason = (
                    f"No deal — reached round limit without agreement after {len(rounds)} round(s) "
                    f"(final gap {format_rupees(gap)}, exceeds the {format_rupees(self.settings.negotiation_close_threshold_paise)} settlement threshold)"
                )
            else:
                reason = f"negotiation ended without a deal: {last.conceder} after {len(rounds)} round(s)"
            trace.append(NegotiationTrace(len(rounds), "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, rounds=rounds, trace=trace)

        agreed_price = last.deal_price_paise
        assert agreed_price is not None and agreed_price <= budget_paise

        if not auto_pay:
            trace.append(NegotiationTrace(len(rounds), "system", "Awaiting your payment to confirm this purchase."))
            return NegotiationOutcome(
                success=True,
                reason=f"negotiated agreement at {format_rupees(agreed_price)} after {len(rounds)} round(s) -- awaiting your payment",
                product=product,
                agreed_price_paise=agreed_price,
                rounds=rounds,
                trace=trace,
                payment_pending=True,
                checkout_token=build_quote_token(product.id, agreed_price),
            )

        purchase, failure_reason = self._pay_and_collect(product.id, agreed_price, product.category)
        if purchase is None:
            reason = failure_reason or "payment/verification failed after negotiated agreement"
            trace.append(NegotiationTrace(len(rounds), "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, rounds=rounds, trace=trace)

        return NegotiationOutcome(
            success=True,
            reason=f"negotiated agreement at {format_rupees(agreed_price)} after {len(rounds)} round(s)",
            product=product,
            agreed_price_paise=agreed_price,
            transaction_id=purchase,
            rounds=rounds,
            trace=trace,
        )

    # -- LLM phrasing (flavor only, never feeds the negotiation math) ------

    def _render_trace(
        self, product: Product, rounds: list[RoundResult], trace: list[NegotiationTrace], occasion: str | None = None
    ) -> None:
        # All of `rounds`' numbers are already final by this point -- the
        # Zeuthen math in `run_zeuthen_negotiation` has fully run, and
        # phrasing never feeds back into it (see module docstring). That
        # means every buyer/merchant phrasing call below is independent of
        # every other one, so we fire them all at once instead of making up
        # to `negotiation_max_rounds` * 2 live Gemini calls back-to-back --
        # sequentially that was the dominant cost of a negotiation (up to
        # ~a minute), in parallel it's roughly the cost of one call.
        jobs: list[dict] = []
        for r in rounds:
            jobs.append(dict(
                speaker="buyer", purpose="buyer_offer", product_name=product.name,
                own_offer=r.buyer_offer_paise, other_offer=r.merchant_offer_paise,
                risk=r.buyer_risk, deal=r.deal, stalemate=r.stalemate, occasion=occasion,
            ))
            jobs.append(dict(
                speaker="merchant", purpose="merchant_counter", product_name=product.name,
                own_offer=r.merchant_offer_paise, other_offer=r.buyer_offer_paise,
                risk=r.merchant_risk, deal=r.deal, stalemate=r.stalemate,
            ))

        with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
            results = list(pool.map(lambda kw: self._phrase(**kw), jobs))

        for i, r in enumerate(rounds):
            buyer_msg, buyer_latency_ms = results[2 * i]
            merchant_msg, merchant_latency_ms = results[2 * i + 1]
            trace.append(
                NegotiationTrace(
                    r.round_number, "buyer", buyer_msg,
                    buyer_offer_paise=r.buyer_offer_paise, merchant_offer_paise=r.merchant_offer_paise,
                    buyer_risk=r.buyer_risk, merchant_risk=r.merchant_risk,
                    latency_ms=buyer_latency_ms,
                )
            )
            trace.append(
                NegotiationTrace(
                    r.round_number, "merchant", merchant_msg,
                    buyer_offer_paise=r.buyer_offer_paise, merchant_offer_paise=r.merchant_offer_paise,
                    buyer_risk=r.buyer_risk, merchant_risk=r.merchant_risk,
                    latency_ms=merchant_latency_ms,
                )
            )
            if r.deal:
                message = (
                    f"Round limit reached with a negligible gap left -- settled at the midpoint, {format_rupees(r.deal_price_paise)}."
                    if r.conceder == "round_cap_settlement"
                    else f"Agreement reached at {format_rupees(r.deal_price_paise)}."
                )
                trace.append(NegotiationTrace(r.round_number, "system", message))
            elif r.stalemate:
                trace.append(
                    NegotiationTrace(
                        r.round_number, "system",
                        "Both sides at their reservation price with a gap remaining -- no deal possible.",
                    )
                )

    @staticmethod
    def _fallback_phrase(speaker: str, own_offer: int) -> str:
        # Used when no llm_client is configured, or the real LLM call fails --
        # deliberately phrased in rupees (never paise) via the same
        # _format_rupees every other user-facing trace message uses, since
        # this text can surface directly as a chat message, not just an
        # internal log line.
        amount = format_rupees(own_offer)
        if speaker == "buyer":
            return f"I can offer {amount} for this."
        return f"I can offer this to you for {amount}."

    def _phrase(
        self, *, speaker, purpose, product_name, own_offer, other_offer, risk, deal, stalemate, occasion=None
    ) -> tuple[str, float | None]:
        if self.llm_client is None:
            return self._fallback_phrase(speaker, own_offer), None
        system_prompt = (
            f"You are the {speaker} in a price negotiation for '{product_name}'. "
            "Write ONE short, natural-language sentence stating your offer. "
            "You must use exactly the price given in paise (INR * 100) -- convert it to "
            "rupees in your sentence. Do not invent a different price. No markdown."
        )
        occasion_note = _OCCASION_NOTES.get(occasion) if speaker == "buyer" else None
        if occasion_note:
            system_prompt += f" {occasion_note} Let that context come through in tone, without changing the price."
        user_prompt = (
            f"Your offer: {own_offer} paise. Other side's last offer: {other_offer} paise. "
            f"Your current risk of conflict: {risk:.2f} (0=safe to concede, 1=won't budge)."
        )
        start = time.perf_counter()
        try:
            text = self.llm_client.generate_text(system_prompt, user_prompt, purpose=purpose)  # type: ignore[call-arg]
        except TypeError:
            # underlying LLMClient (not the logging wrapper) doesn't take `purpose`
            try:
                text = self.llm_client.generate_text(system_prompt, user_prompt)
            except Exception:
                return self._fallback_phrase(speaker, own_offer), round((time.perf_counter() - start) * 1000, 1)
        except Exception:
            return self._fallback_phrase(speaker, own_offer), round((time.perf_counter() - start) * 1000, 1)
        return text, round((time.perf_counter() - start) * 1000, 1)

    # -- payment ------------------------------------------------------------

    def _pay_and_collect(
        self, product_id: str, price_paise: int, category: str, idempotency_key: str | None = None
    ) -> tuple[str | None, str | None]:
        """Runs one purchase through the full trust pipeline before ever
        touching a payment rail. Returns (transaction_id, failure_reason) --
        exactly one is None. `idempotency_key` defaults to a fresh key per
        call; pass an explicit one to test/trigger dedup behavior."""
        idempotency_key = idempotency_key or f"{product_id}:{uuid.uuid4().hex}"
        request = build_signed_request(
            self.identity, self.credential, {"product_id": product_id, "price_paise": price_paise}, idempotency_key
        )
        auth = self.merchant_agent.authorize_purchase(request, category=category)
        if not auth.approved:
            kind = "escalated for review" if auth.escalate else "rejected"
            return None, f"purchase {kind} by trust layer ({auth.rule}): {auth.reason}"
        if auth.is_replay:
            # A previously-completed purchase with this idempotency key --
            # return its result without creating a new order/charge.
            return auth.cached_result, None if auth.cached_result else "cached purchase attempt had previously failed"

        order = self.razorpay_client.create_order(price_paise)
        pay = self.razorpay_client.pay_order(order["id"], price_paise)
        header = self._build_x_payment_header(product_id, pay)
        result = self.merchant_agent.handle_request(product_id, header, agreed_price_paise=price_paise)
        self.merchant_agent.record_purchase_attempt(self.identity.agent_id)

        transaction_id = result.body.get("transaction") if result.status_code == 200 else None
        if transaction_id is not None:
            self.merchant_agent.record_purchase_spend(self.identity.agent_id, price_paise)
        self.merchant_agent.store_purchase_result(idempotency_key, transaction_id)
        if transaction_id is None:
            return None, result.body.get("error", "payment/verification failed")
        return transaction_id, None

    @staticmethod
    def _build_x_payment_header(product_id: str, pay: dict) -> str:
        payload = {
            "x402Version": 1,
            "scheme": "razorpay-inr",
            "network": "razorpay-test",
            "resource": f"/products/{product_id}",
            "payload": {
                "orderId": pay["order_id"],
                "paymentId": pay["payment_id"],
                "signature": pay["signature"],
            },
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()

    # -- product matching (deterministic) ------------------------------------

    def _find_candidate_product(self, goal_text: str, budget_paise: int) -> Product | None:
        keywords = [
            w for w in re.findall(r"[a-z0-9]+", goal_text.lower())
            if w not in _STOPWORDS and not w.isdigit()
        ]
        ceiling = round(budget_paise * self.settings.buyer_price_ceiling_factor)

        scored: list[tuple[int, Product]] = []
        for product in self.catalog.all():
            haystack = f"{product.name} {product.description} {product.category}".lower()
            score = sum(1 for kw in keywords if kw in haystack)
            if score > 0 and product.price_paise <= ceiling:
                scored.append((score, product))

        if not scored:
            return None
        scored.sort(key=lambda t: (-t[0], t[1].price_paise))
        return scored[0][1]
