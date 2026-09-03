from app.config import get_settings
from app.trust.policy import PolicyEngine


def _engine() -> PolicyEngine:
    return PolicyEngine(get_settings())


def test_within_bounds_purchase_is_approved():
    settings = get_settings()
    engine = PolicyEngine(settings)
    decision = engine.evaluate_purchase(
        price_paise=settings.max_single_transaction_paise - 1,
        category=settings.allowed_categories[0],
    )
    assert decision.approved
    assert not decision.escalate


def test_spend_cap_rule_fires_and_escalates():
    settings = get_settings()
    engine = PolicyEngine(settings)
    decision = engine.evaluate_purchase(
        price_paise=settings.max_single_transaction_paise + 1,
        category=settings.allowed_categories[0],
    )
    assert not decision.approved
    assert decision.escalate
    assert decision.rule == "spend_cap"
    assert "max_single_transaction_paise" in decision.reason


def test_category_rule_fires_and_escalates():
    settings = get_settings()
    engine = PolicyEngine(settings)
    decision = engine.evaluate_purchase(price_paise=1000, category="not-an-allowed-category")
    assert not decision.approved
    assert decision.escalate
    assert decision.rule == "category"
    assert "not-an-allowed-category" in decision.reason


def test_discount_within_bounds_is_approved():
    settings = get_settings()
    engine = PolicyEngine(settings)
    decision = engine.evaluate_discount(discount_percent=settings.max_upsell_discount_percent)
    assert decision.approved


def test_discount_rule_fires_and_escalates():
    settings = get_settings()
    engine = PolicyEngine(settings)
    decision = engine.evaluate_discount(discount_percent=settings.max_upsell_discount_percent + 1)
    assert not decision.approved
    assert decision.escalate
    assert decision.rule == "discount_bounds"
