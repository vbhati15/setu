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
from dataclasses import dataclass, field

from backend.app.bargaining import BuyerParty, RoundResult, run_zeuthen_negotiation
from backend.app.catalog import Catalog, Product, get_catalog
from backend.app.config import Settings, get_settings
from backend.app.fake_razorpay import FakeRazorpayClient
from backend.app.llm.base import LLMClient
from backend.app.merchant_agent import MerchantAgent

_STOPWORDS = {
    "a", "an", "the", "get", "buy", "for", "and", "of", "to", "in", "with",
    "under", "over", "budget", "preferred", "please", "want", "need", "ideally",
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


class BuyerAgent:
    def __init__(
        self,
        merchant_agent: MerchantAgent,
        llm_client: LLMClient | None = None,
        razorpay_client: FakeRazorpayClient | None = None,
        catalog: Catalog | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.merchant_agent = merchant_agent
        self.llm_client = llm_client
        self.razorpay_client = razorpay_client or FakeRazorpayClient()
        self.catalog = catalog or get_catalog()
        self.settings = settings or get_settings()

    # -- public API -------------------------------------------------------

    def negotiate_and_purchase(self, goal_text: str, budget_paise: int) -> NegotiationOutcome:
        trace: list[NegotiationTrace] = []

        candidate = self._find_candidate_product(goal_text, budget_paise)
        if candidate is None:
            reason = (
                f"no catalog product matches goal '{goal_text}' within "
                f"{self.settings.buyer_price_ceiling_factor}x budget ({budget_paise} paise)"
            )
            trace.append(NegotiationTrace(0, "system", reason))
            return NegotiationOutcome(success=False, reason=reason, trace=trace)

        quote = self.merchant_agent.handle_request(candidate.id)
        list_price_paise = int(quote.body["accepts"][0]["maxAmountRequired"])
        trace.append(
            NegotiationTrace(
                0, "system",
                f"Matched product '{candidate.name}' ({candidate.id}), list price {list_price_paise} paise.",
            )
        )

        if budget_paise >= list_price_paise:
            outcome = self._accept_list_price(candidate, list_price_paise, budget_paise, quote, trace)
        else:
            outcome = self._negotiate(candidate, list_price_paise, budget_paise, trace)

        return outcome

    # -- comfortable-budget path (no negotiation needed) -------------------

    def _accept_list_price(
        self, product: Product, list_price_paise: int, budget_paise: int, quote, trace
    ) -> NegotiationOutcome:
        trace.append(
            NegotiationTrace(0, "buyer", f"Budget covers list price ({list_price_paise} paise) -- accepting outright.")
        )
        purchase = self._pay_and_collect(product.id, list_price_paise)
        if purchase is None:
            reason = "payment/verification failed for list-price purchase"
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
            self._maybe_accept_upsell(upsell_body, remaining_budget_paise, outcome)

        return outcome

    def _maybe_accept_upsell(self, upsell_body: dict, remaining_budget_paise: int, outcome: NegotiationOutcome) -> None:
        upsell_product = self.catalog.get(upsell_body["productId"])
        if upsell_product is None:
            return
        discounted_price = int(upsell_body["discountedPricePaise"])
        outcome.trace.append(
            NegotiationTrace(
                0, "merchant",
                f"Upsell offered: {upsell_product.name} at {discounted_price} paise "
                f"({upsell_body['discountPercent']}% off) -- {upsell_body.get('reason', '')}",
            )
        )
        if discounted_price > remaining_budget_paise:
            outcome.trace.append(NegotiationTrace(0, "buyer", "Upsell declined -- exceeds remaining budget."))
            return

        upsell_purchase = self._pay_and_collect(upsell_product.id, discounted_price)
        if upsell_purchase is None:
            outcome.trace.append(NegotiationTrace(0, "system", "Upsell purchase failed verification -- skipped."))
            return

        outcome.trace.append(NegotiationTrace(0, "buyer", f"Upsell accepted: {upsell_product.name}."))
        outcome.upsell_purchased = True
        outcome.upsell_product = upsell_product

    # -- tight-budget path (real Zeuthen negotiation) ----------------------

    def _negotiate(self, product: Product, list_price_paise: int, budget_paise: int, trace) -> NegotiationOutcome:
        merchant_party = self.merchant_agent.negotiation_party(product.id)
        if merchant_party is None:
            reason = "merchant has no negotiation terms for this product"
            trace.append(NegotiationTrace(0, "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, trace=trace)

        buyer_party = BuyerParty(budget_paise=budget_paise)

        # Deterministic opening lowball: leaves genuine room to negotiate up.
        opening_buyer_offer = max(1, round(budget_paise * 0.6))
        opening_merchant_offer = list_price_paise

        rounds = run_zeuthen_negotiation(
            buyer=buyer_party,
            merchant=merchant_party,
            opening_buyer_offer_paise=opening_buyer_offer,
            opening_merchant_offer_paise=opening_merchant_offer,
            max_rounds=self.settings.negotiation_max_rounds,
            min_concession_fraction=self.settings.negotiation_min_concession_fraction,
            max_concession_fraction=self.settings.negotiation_max_concession_fraction,
            convergence_threshold_paise=round(list_price_paise * self.settings.negotiation_convergence_fraction),
        )

        self._render_trace(product, rounds, trace)

        last = rounds[-1]
        if not last.deal:
            reason = f"negotiation ended without a deal: {last.conceder} after {len(rounds)} round(s)"
            trace.append(NegotiationTrace(len(rounds), "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, rounds=rounds, trace=trace)

        agreed_price = last.deal_price_paise
        assert agreed_price is not None and agreed_price <= budget_paise

        purchase = self._pay_and_collect(product.id, agreed_price)
        if purchase is None:
            reason = "payment/verification failed after negotiated agreement"
            trace.append(NegotiationTrace(len(rounds), "system", reason))
            return NegotiationOutcome(success=False, reason=reason, product=product, rounds=rounds, trace=trace)

        return NegotiationOutcome(
            success=True,
            reason=f"negotiated agreement at {agreed_price} paise after {len(rounds)} round(s)",
            product=product,
            agreed_price_paise=agreed_price,
            transaction_id=purchase,
            rounds=rounds,
            trace=trace,
        )

    # -- LLM phrasing (flavor only, never feeds the negotiation math) ------

    def _render_trace(self, product: Product, rounds: list[RoundResult], trace: list[NegotiationTrace]) -> None:
        for r in rounds:
            buyer_msg = self._phrase(
                speaker="buyer",
                purpose="buyer_offer",
                product_name=product.name,
                own_offer=r.buyer_offer_paise,
                other_offer=r.merchant_offer_paise,
                risk=r.buyer_risk,
                deal=r.deal,
                stalemate=r.stalemate,
            )
            trace.append(
                NegotiationTrace(
                    r.round_number, "buyer", buyer_msg,
                    buyer_offer_paise=r.buyer_offer_paise, merchant_offer_paise=r.merchant_offer_paise,
                    buyer_risk=r.buyer_risk, merchant_risk=r.merchant_risk,
                )
            )
            merchant_msg = self._phrase(
                speaker="merchant",
                purpose="merchant_counter",
                product_name=product.name,
                own_offer=r.merchant_offer_paise,
                other_offer=r.buyer_offer_paise,
                risk=r.merchant_risk,
                deal=r.deal,
                stalemate=r.stalemate,
            )
            trace.append(
                NegotiationTrace(
                    r.round_number, "merchant", merchant_msg,
                    buyer_offer_paise=r.buyer_offer_paise, merchant_offer_paise=r.merchant_offer_paise,
                    buyer_risk=r.buyer_risk, merchant_risk=r.merchant_risk,
                )
            )
            if r.deal:
                trace.append(
                    NegotiationTrace(r.round_number, "system", f"Agreement reached at {r.deal_price_paise} paise.")
                )
            elif r.stalemate:
                trace.append(
                    NegotiationTrace(
                        r.round_number, "system",
                        "Both sides at their reservation price with a gap remaining -- no deal possible.",
                    )
                )

    def _phrase(self, *, speaker, purpose, product_name, own_offer, other_offer, risk, deal, stalemate) -> str:
        if self.llm_client is None:
            return f"{speaker} offer: {own_offer} paise (risk={risk:.2f})"
        system_prompt = (
            f"You are the {speaker} in a price negotiation for '{product_name}'. "
            "Write ONE short, natural-language sentence stating your offer. "
            "You must use exactly the price given in paise (INR * 100) -- convert it to "
            "rupees in your sentence. Do not invent a different price. No markdown."
        )
        user_prompt = (
            f"Your offer: {own_offer} paise. Other side's last offer: {other_offer} paise. "
            f"Your current risk of conflict: {risk:.2f} (0=safe to concede, 1=won't budge)."
        )
        try:
            return self.llm_client.generate_text(system_prompt, user_prompt, purpose=purpose)  # type: ignore[call-arg]
        except TypeError:
            # underlying LLMClient (not the logging wrapper) doesn't take `purpose`
            try:
                return self.llm_client.generate_text(system_prompt, user_prompt)
            except Exception:
                return f"{speaker} offer: {own_offer} paise (risk={risk:.2f})"
        except Exception:
            return f"{speaker} offer: {own_offer} paise (risk={risk:.2f})"

    # -- payment ------------------------------------------------------------

    def _pay_and_collect(self, product_id: str, price_paise: int) -> str | None:
        order = self.razorpay_client.create_order(price_paise)
        pay = self.razorpay_client.pay_order(order["id"], price_paise)
        header = self._build_x_payment_header(product_id, pay)
        result = self.merchant_agent.handle_request(product_id, header, agreed_price_paise=price_paise)
        if result.status_code != 200:
            return None
        return result.body.get("transaction")

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
