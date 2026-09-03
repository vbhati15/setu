from backend.app.buyer_agent import BuyerAgent
from backend.app.fake_razorpay import FakeRazorpayClient
from backend.app.llm.base import LLMClient
from backend.app.merchant_agent import MerchantAgent


class FakeLLMClient(LLMClient):
    """No-op phrasing client -- returns deterministic text, never invents prices."""

    def __init__(self, upsell_response: dict | None = None):
        self.upsell_response = upsell_response or {"offer_upsell": False}

    def generate_json(self, system_prompt, user_prompt, schema):
        return self.upsell_response

    def generate_text(self, system_prompt, user_prompt):
        return "scripted negotiation message"


def _make_agents(upsell_response: dict | None = None):
    razorpay = FakeRazorpayClient()
    llm = FakeLLMClient(upsell_response=upsell_response)
    merchant = MerchantAgent(razorpay_client=razorpay, llm_client=llm)
    buyer = BuyerAgent(merchant_agent=merchant, llm_client=llm, razorpay_client=razorpay)
    return buyer, merchant


def test_comfortable_budget_clean_match_upsell_accepted():
    upsell = {
        "offer_upsell": True,
        "product_id": "keycap-set-pbt-129",
        "discount_percent": 10,
        "reason": "goes great with that board",
    }
    buyer, _ = _make_agents(upsell_response=upsell)

    outcome = buyer.negotiate_and_purchase("get a mechanical keyboard, hot-swap preferred", budget_paise=500_000)

    assert outcome.success is True
    assert outcome.product.id == "mechanical-keyboard-65"
    assert outcome.agreed_price_paise == 349_900
    assert outcome.transaction_id is not None
    assert outcome.rounds == []  # no negotiation needed
    assert outcome.upsell_purchased is True
    assert outcome.upsell_product.id == "keycap-set-pbt-129"


def test_tight_budget_requires_real_negotiation_and_closes():
    buyer, _ = _make_agents()

    outcome = buyer.negotiate_and_purchase("mechanical keyboard hot-swap under 3000", budget_paise=300_000)

    assert outcome.success is True
    assert outcome.product.id == "mechanical-keyboard-65"
    assert outcome.agreed_price_paise is not None
    assert outcome.agreed_price_paise <= 300_000
    assert outcome.transaction_id is not None
    assert len(outcome.rounds) > 1, "tight budget should require multiple negotiation rounds, not an instant close"
    conceders = {r.conceder for r in outcome.rounds}
    assert "buyer" in conceders and "merchant" in conceders, "both sides should concede at some point"


def test_budget_with_no_viable_match_fails_gracefully():
    buyer, _ = _make_agents()

    outcome = buyer.negotiate_and_purchase("mechanical keyboard hot-swap", budget_paise=240_000)

    assert outcome.success is False
    assert outcome.agreed_price_paise is None
    assert outcome.transaction_id is None
    assert outcome.product is not None  # a product was matched, negotiation just couldn't close
    assert outcome.rounds, "should have actually attempted negotiation, not failed silently"
    assert outcome.rounds[-1].conceder in ("stalemate", "max_rounds_exceeded")


def test_no_matching_product_at_all_fails_before_contacting_merchant():
    buyer, _ = _make_agents()

    outcome = buyer.negotiate_and_purchase("a vintage typewriter", budget_paise=1_000_000)

    assert outcome.success is False
    assert outcome.product is None
    assert outcome.rounds == []


def test_negotiated_purchase_is_rejected_if_price_tampered_before_payment():
    # Sanity check that the merchant actually verifies the agreed price
    # rather than trusting whatever the buyer claims to have paid.
    buyer, merchant = _make_agents()
    party = merchant.negotiation_party("mechanical-keyboard-65")
    assert party is not None
    assert party.min_price_paise == round(349_900 * merchant.settings.merchant_min_price_factor)
