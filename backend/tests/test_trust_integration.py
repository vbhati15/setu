"""Integration tests: the trust layer (signed identity, policy, idempotency,
velocity, kill switch, retry) wired into the real BuyerAgent/MerchantAgent
purchase path, not just the isolated trust unit tests."""
from app.buyer_agent import BuyerAgent
from app.config import get_settings
from app.fake_razorpay import FakeRazorpayClient
from app.llm.base import LLMClient
from app.merchant_agent import MerchantAgent
from app.trust.retry import RetryExhausted, retry_with_backoff


class FakeLLMClient(LLMClient):
    def generate_json(self, system_prompt, user_prompt, schema):
        return {"offer_upsell": False}

    def generate_text(self, system_prompt, user_prompt):
        return "scripted"


def _make_agents():
    razorpay = FakeRazorpayClient()
    llm = FakeLLMClient()
    merchant = MerchantAgent(razorpay_client=razorpay, llm_client=llm)
    buyer = BuyerAgent(merchant_agent=merchant, llm_client=llm, razorpay_client=razorpay)
    return buyer, merchant, razorpay


def test_genuine_duplicate_purchase_results_in_exactly_one_charge():
    buyer, merchant, razorpay = _make_agents()
    product_id = "mechanical-keyboard-65"
    price = merchant.catalog.get(product_id).price_paise
    category = merchant.catalog.get(product_id).category

    txn_1, reason_1 = buyer._pay_and_collect(product_id, price, category, idempotency_key="dup-key")
    assert txn_1 is not None and reason_1 is None
    payments_after_first = len(razorpay._payments)

    txn_2, reason_2 = buyer._pay_and_collect(product_id, price, category, idempotency_key="dup-key")
    assert txn_2 == txn_1, "duplicate request should return the same transaction, not a new one"
    assert reason_2 is None
    assert len(razorpay._payments) == payments_after_first, "duplicate request must not create a second charge"


def test_different_idempotency_keys_each_charge_independently():
    buyer, merchant, razorpay = _make_agents()
    product_id = "mechanical-keyboard-65"
    price = merchant.catalog.get(product_id).price_paise
    category = merchant.catalog.get(product_id).category

    txn_1, _ = buyer._pay_and_collect(product_id, price, category, idempotency_key="key-a")
    txn_2, _ = buyer._pay_and_collect(product_id, price, category, idempotency_key="key-b")
    assert txn_1 != txn_2
    assert len(razorpay._payments) == 2


def test_purchase_beyond_spend_cap_is_rejected_with_reason_before_charging():
    buyer, merchant, razorpay = _make_agents()
    settings = get_settings()
    product_id = "mechanical-keyboard-65"
    category = merchant.catalog.get(product_id).category
    over_cap_price = settings.max_single_transaction_paise + 1

    txn, reason = buyer._pay_and_collect(product_id, over_cap_price, category, idempotency_key="over-cap")
    assert txn is None
    assert reason is not None
    assert "exceeds" in reason
    assert len(razorpay._payments) == 0, "a rejected purchase must never reach the payment rail"


def test_daily_spend_cap_fires_across_a_sequence_of_individually_valid_purchases():
    """None of these purchases individually violates spend_cap, category,
    velocity, or credential scope -- only their cumulative total exceeds
    max_daily_spend_paise, and only the daily-spend check should catch
    that."""
    buyer, merchant, razorpay = _make_agents()
    settings = get_settings()
    product_id = "mechanical-keyboard-65"
    category = merchant.catalog.get(product_id).category
    price = settings.max_single_transaction_paise  # each purchase is individually within every other bound

    num_that_fit = settings.max_daily_spend_paise // price
    for i in range(num_that_fit):
        txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key=f"daily-{i}")
        assert txn is not None, f"purchase {i} unexpectedly failed: {reason}"

    payments_before_overflow = len(razorpay._payments)

    txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key=f"daily-{num_that_fit}")
    assert txn is None
    assert "daily_spend" in reason
    assert "max_daily_spend_paise" in reason
    assert len(razorpay._payments) == payments_before_overflow, "a daily-cap-exceeding purchase must never charge"


def test_kill_switch_blocks_purchase_in_the_real_flow():
    buyer, merchant, razorpay = _make_agents()
    product_id = "mechanical-keyboard-65"
    price = merchant.catalog.get(product_id).price_paise
    category = merchant.catalog.get(product_id).category

    merchant.trust_guard.kill_switch.activate("mid-run test")
    txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key="ks-1")
    assert txn is None
    assert "kill_switch" in reason
    assert len(razorpay._payments) == 0

    merchant.trust_guard.kill_switch.deactivate()
    txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key="ks-2")
    assert txn is not None
    assert reason is None


def test_kill_switch_triggered_mid_scenario_blocks_the_upsell_leg():
    """Mirrors the real unattended loop: a scenario is in progress (list
    price already purchased), the kill switch is triggered mid-way, and the
    remaining leg (the upsell) must not go through until it's turned back
    on."""
    razorpay = FakeRazorpayClient()
    llm = FakeLLMClient()
    merchant = MerchantAgent(razorpay_client=razorpay, llm_client=llm)
    buyer = BuyerAgent(merchant_agent=merchant, llm_client=llm, razorpay_client=razorpay)

    product_id = "mechanical-keyboard-65"
    price = merchant.catalog.get(product_id).price_paise
    category = merchant.catalog.get(product_id).category

    txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key="scenario-leg-1")
    assert txn is not None and reason is None
    payments_before_kill = len(razorpay._payments)

    merchant.trust_guard.kill_switch.activate("mid-scenario halt")

    upsell_id = "keycap-set-pbt-129"
    upsell_price = merchant.catalog.get(upsell_id).price_paise
    upsell_category = merchant.catalog.get(upsell_id).category
    txn2, reason2 = buyer._pay_and_collect(upsell_id, upsell_price, upsell_category, idempotency_key="scenario-leg-2")
    assert txn2 is None
    assert "kill_switch" in reason2
    assert len(razorpay._payments) == payments_before_kill, "no new charge should occur while halted"

    merchant.trust_guard.kill_switch.deactivate()
    txn3, reason3 = buyer._pay_and_collect(upsell_id, upsell_price, upsell_category, idempotency_key="scenario-leg-2")
    assert txn3 is not None and reason3 is None


def test_velocity_limit_escalates_after_configured_attempts_in_real_flow():
    buyer, merchant, razorpay = _make_agents()
    settings = get_settings()
    product_id = "mechanical-keyboard-65"
    price = merchant.catalog.get(product_id).price_paise
    category = merchant.catalog.get(product_id).category

    for i in range(settings.max_purchases_per_minute):
        txn, reason = buyer._pay_and_collect(product_id, price, category, idempotency_key=f"velo-{i}")
        assert txn is not None, f"attempt {i} unexpectedly failed: {reason}"

    txn, reason = buyer._pay_and_collect(
        product_id, price, category, idempotency_key=f"velo-{settings.max_purchases_per_minute}"
    )
    assert txn is None
    assert "velocity" in reason


def test_simulated_razorpay_timeout_is_retried_and_recovers():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("simulated Razorpay timeout")
        return {"ok": True}

    result = retry_with_backoff(flaky, max_attempts=3, sleep=lambda s: None)
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_persistent_razorpay_failure_is_not_hidden_as_success():
    def always_fails():
        raise TimeoutError("simulated persistent outage")

    try:
        retry_with_backoff(always_fails, max_attempts=3, sleep=lambda s: None)
        assert False, "expected RetryExhausted"
    except RetryExhausted as exc:
        assert exc.attempts == 3
