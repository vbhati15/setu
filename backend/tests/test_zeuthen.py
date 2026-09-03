from app.bargaining import BuyerParty, MerchantParty, run_zeuthen_negotiation
from app.bargaining.zeuthen import buyer_utility, merchant_utility, risk


def test_buyer_utility_bounds():
    assert buyer_utility(0, 100_000) == 1.0
    assert buyer_utility(100_000, 100_000) == 0.0
    assert buyer_utility(150_000, 100_000) == 0.0  # over budget clamps to 0, doesn't go negative
    assert 0 < buyer_utility(50_000, 100_000) < 1


def test_merchant_utility_bounds():
    assert merchant_utility(349_900, 262_425, 349_900) == 1.0
    assert merchant_utility(262_425, 262_425, 349_900) == 0.0
    assert merchant_utility(200_000, 262_425, 349_900) == 0.0  # below floor clamps to 0
    assert 0 < merchant_utility(300_000, 262_425, 349_900) < 1


def test_risk_is_one_when_own_utility_is_zero():
    assert risk(0.0, 0.5) == 1.0


def test_risk_is_zero_when_offers_are_equal():
    assert risk(0.5, 0.5) == 0.0


def test_negotiation_converges_when_budget_covers_merchant_floor():
    buyer = BuyerParty(budget_paise=300_000)
    merchant = MerchantParty(min_price_paise=262_425, list_price_paise=349_900)
    rounds = run_zeuthen_negotiation(
        buyer, merchant,
        opening_buyer_offer_paise=180_000,
        opening_merchant_offer_paise=349_900,
        max_rounds=12,
        min_concession_fraction=0.15,
        max_concession_fraction=0.35,
        convergence_threshold_paise=3_499,
    )
    last = rounds[-1]
    assert last.deal is True
    assert last.deal_price_paise is not None
    assert 262_425 <= last.deal_price_paise <= 300_000
    # genuine back-and-forth, not an instant first-round cave
    assert len(rounds) > 2
    conceders = {r.conceder for r in rounds}
    assert "buyer" in conceders and "merchant" in conceders


def test_negotiation_stalemates_when_budget_below_merchant_floor():
    buyer = BuyerParty(budget_paise=240_000)
    merchant = MerchantParty(min_price_paise=262_425, list_price_paise=349_900)
    rounds = run_zeuthen_negotiation(
        buyer, merchant,
        opening_buyer_offer_paise=144_000,
        opening_merchant_offer_paise=349_900,
        max_rounds=12,
        min_concession_fraction=0.15,
        max_concession_fraction=0.35,
        convergence_threshold_paise=3_499,
    )
    last = rounds[-1]
    assert last.deal is False
    assert last.conceder in ("stalemate", "max_rounds_exceeded")
    assert last.deal_price_paise is None


def test_negotiation_closes_instantly_when_offers_already_cross():
    buyer = BuyerParty(budget_paise=400_000)
    merchant = MerchantParty(min_price_paise=262_425, list_price_paise=349_900)
    rounds = run_zeuthen_negotiation(
        buyer, merchant,
        opening_buyer_offer_paise=349_900,
        opening_merchant_offer_paise=349_900,
        max_rounds=12,
        min_concession_fraction=0.15,
        max_concession_fraction=0.35,
    )
    assert len(rounds) == 1
    assert rounds[0].deal is True
    assert rounds[0].deal_price_paise == 349_900
