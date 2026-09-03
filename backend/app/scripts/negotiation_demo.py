"""Runs the Buyer Agent <-> Merchant Agent Zeuthen negotiation loop,
unattended, against the fake Razorpay client, across three scenarios:

  1. Comfortable budget, clean match, upsell accepted -- no negotiation
     needed, list price + LLM-proposed upsell both purchased.
  2. Tight budget requiring real back-and-forth to close the gap.
  3. Budget with no viable match -- confirms a graceful, explicit failure
     (not a silent one).

Uses the real Gemini client (per Day-1's `get_llm_client()`) for offer
phrasing, wrapped in `LoggingLLMClient` to log latency/estimated cost per
call -- this is what "unattended" actually means here: no manual
click-through, no mocked LLM, only the payment rail (fake Razorpay) is
simulated, per the Day-1 decision that automated flows never drive the real
Checkout widget.

Run with (from the backend/ directory): python -m app.scripts.negotiation_demo
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.buyer_agent import BuyerAgent, NegotiationOutcome
from app.fake_razorpay import FakeRazorpayClient
from app.llm import get_llm_client
from app.llm.logging_client import LoggingLLMClient
from app.merchant_agent import MerchantAgent

SCENARIOS = [
    (
        "Scenario 1: comfortable budget, clean match, upsell accepted",
        "get a mechanical keyboard under 6000, hot-swap preferred",
        500_000,  # INR 5,000 -- comfortably above the 349900-paise list price
    ),
    (
        "Scenario 2: tight budget, requires real negotiation",
        "get a mechanical keyboard under 3000, hot-swap preferred",
        300_000,  # INR 3,000 -- below list price, above merchant's floor
    ),
    (
        "Scenario 3: budget with no viable match",
        "get a mechanical keyboard under 2400, hot-swap preferred",
        240_000,  # INR 2,400 -- below merchant's floor, negotiation must fail cleanly
    ),
]


def print_trace(outcome: NegotiationOutcome) -> None:
    for entry in outcome.trace:
        prefix = f"[round {entry.round_number}] {entry.speaker:>8}:"
        print(f"{prefix} {entry.message}")
        if entry.buyer_risk is not None:
            print(
                f"{'':>18}(buyer_offer={entry.buyer_offer_paise}p merchant_offer={entry.merchant_offer_paise}p "
                f"buyer_risk={entry.buyer_risk:.3f} merchant_risk={entry.merchant_risk:.3f})"
            )


def run_scenario(title: str, goal: str, budget_paise: int, razorpay: FakeRazorpayClient, llm: LoggingLLMClient) -> None:
    print("\n" + "=" * 90)
    print(title)
    print(f"goal={goal!r} budget_paise={budget_paise}")
    print("=" * 90)

    merchant = MerchantAgent(razorpay_client=razorpay, llm_client=llm)
    buyer = BuyerAgent(merchant_agent=merchant, llm_client=llm, razorpay_client=razorpay)

    calls_before = len(llm.calls)
    outcome = buyer.negotiate_and_purchase(goal, budget_paise)
    calls_after = len(llm.calls)

    print_trace(outcome)

    print("-" * 90)
    print(f"SUCCESS: {outcome.success}")
    print(f"REASON: {outcome.reason}")
    if outcome.product:
        print(f"PRODUCT: {outcome.product.name} ({outcome.product.id})")
    print(f"AGREED PRICE (paise): {outcome.agreed_price_paise}")
    print(f"TRANSACTION ID: {outcome.transaction_id}")
    print(f"UPSELL PURCHASED: {outcome.upsell_purchased}"
          + (f" ({outcome.upsell_product.name})" if outcome.upsell_product else ""))
    print(f"LLM calls this scenario: {calls_after - calls_before}")


def main() -> None:
    razorpay = FakeRazorpayClient()
    llm = LoggingLLMClient(inner=get_llm_client())

    for title, goal, budget in SCENARIOS:
        run_scenario(title, goal, budget, razorpay, llm)

    print("\n" + "=" * 90)
    print("LLM CALL LOG (all scenarios)")
    print("=" * 90)
    for i, call in enumerate(llm.calls, 1):
        print(
            f"{i:>3}. kind={call.kind:<4} purpose={call.purpose:<18} "
            f"latency_ms={call.latency_ms:>7} est_in_tok={call.est_input_tokens:>4} "
            f"est_out_tok={call.est_output_tokens:>4} est_cost_usd={call.est_cost_usd}"
        )
    print(f"\nTotal LLM calls: {len(llm.calls)}")
    print(f"Total latency: {llm.total_latency_ms()} ms")
    print(f"Total estimated cost (paid-tier equivalent): ${llm.total_cost_usd()}")


if __name__ == "__main__":
    main()
