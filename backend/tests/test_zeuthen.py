from backend.app.bargaining import BuyerParty, MerchantParty, run_zeuthen_negotiation
from backend.app.bargaining.zeuthen import buyer_utility, merchant_utility, risk


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


def test_round_cap_settles_close_gap_instead_of_a_false_no_deal():
    """Reproduces the reported issue: a budget just under list price, with
    the stingier concession floor a real "best price" negotiation uses, can
    still be a small, immaterial gap apart when the round cap hits --
    concession size decays every round, so a genuinely reachable deal can
    miss the mid-negotiation convergence check by a few rupees. Without
    close_threshold_paise this reports a false "no deal"; with it, the round
    cap settles at the midpoint instead."""
    list_price_paise = 89_900  # INR 899.00
    budget_paise = list_price_paise - 10_000  # INR 100 under list price
    buyer = BuyerParty(budget_paise=budget_paise)
    merchant = MerchantParty(min_price_paise=round(list_price_paise * 0.75), list_price_paise=list_price_paise)

    common_kwargs = dict(
        buyer=buyer,
        merchant=merchant,
        opening_buyer_offer_paise=round(budget_paise * 0.55),
        opening_merchant_offer_paise=list_price_paise,
        max_rounds=12,
        min_concession_fraction=0.1275,  # matches "best price" priority's stingier floor
        max_concession_fraction=0.3325,
        convergence_threshold_paise=round(list_price_paise * 0.01),
    )

    rounds_without_rule = run_zeuthen_negotiation(**common_kwargs, close_threshold_paise=0)
    last_without = rounds_without_rule[-1]
    # Confirms this scenario genuinely hits the round cap short of the
    # convergence line -- otherwise this test wouldn't exercise the bug it's
    # meant to catch.
    assert last_without.conceder == "max_rounds_exceeded"
    assert last_without.deal is False
    gap = last_without.merchant_offer_paise - last_without.buyer_offer_paise

    rounds_with_rule = run_zeuthen_negotiation(**common_kwargs, close_threshold_paise=15_000)
    last_with = rounds_with_rule[-1]

    # Never an unclear result or a hang: exactly one of these two, and
    # nothing else, no matter how the numbers above shift in the future.
    if gap <= 15_000:
        assert last_with.deal is True
        assert last_with.conceder == "round_cap_settlement"
        assert last_with.deal_price_paise is not None
        assert merchant.reservation_paise <= last_with.deal_price_paise <= buyer.reservation_paise
    else:
        assert last_with.deal is False
        assert last_with.conceder == "max_rounds_exceeded"
        assert last_with.deal_price_paise is None


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
