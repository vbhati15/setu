import base64
import json

from backend.app.catalog import get_catalog
from backend.app.config import get_settings
from backend.app.llm.base import LLMClient
from backend.app.merchant_agent import MerchantAgent


class FakeLLMClient(LLMClient):
    def __init__(self, json_response: dict | None = None):
        self.json_response = json_response or {"offer_upsell": False}

    def generate_json(self, system_prompt, user_prompt, schema):
        return self.json_response

    def generate_text(self, system_prompt, user_prompt):
        return ""


class FakeRazorpayClient:
    def __init__(self, payment: dict | None = None, signature_valid: bool = True):
        self.payment = payment
        self.signature_valid = signature_valid

    def fetch_payment(self, payment_id: str) -> dict:
        return self.payment

    def verify_payment_signature(self, params: dict) -> bool:
        return self.signature_valid


def _make_x_payment_header(resource: str, order_id="order_1", payment_id="pay_1", signature="sig_1") -> str:
    payload = {
        "x402Version": 1,
        "scheme": "razorpay-inr",
        "network": "razorpay-test",
        "resource": resource,
        "payload": {"orderId": order_id, "paymentId": payment_id, "signature": signature},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_unpaid_request_returns_402_with_payment_requirements():
    agent = MerchantAgent(llm_client=FakeLLMClient())
    result = agent.handle_request("mechanical-keyboard-65")
    assert result.status_code == 402
    assert result.body["accepts"][0]["resource"] == "/products/mechanical-keyboard-65"
    assert result.body["accepts"][0]["maxAmountRequired"] == "349900"


def test_unknown_product_returns_404():
    agent = MerchantAgent(llm_client=FakeLLMClient())
    result = agent.handle_request("does-not-exist")
    assert result.status_code == 404


def test_malformed_product_id_returns_400():
    agent = MerchantAgent(llm_client=FakeLLMClient())
    result = agent.handle_request("../etc/passwd")
    assert result.status_code == 400


def test_valid_payment_returns_200_and_access_granted():
    product = get_catalog().get("mechanical-keyboard-65")
    fake_payment = {
        "order_id": "order_1",
        "amount": product.price_paise,
        "status": "captured",
        "email": "buyer@example.com",
    }
    agent = MerchantAgent(
        razorpay_client=FakeRazorpayClient(payment=fake_payment, signature_valid=True),
        llm_client=FakeLLMClient(),
    )
    header = _make_x_payment_header("/products/mechanical-keyboard-65")
    result = agent.handle_request("mechanical-keyboard-65", header)
    assert result.status_code == 200
    assert result.body["access_granted"] is True
    assert result.body["transaction"] == "pay_1"
    assert "X-PAYMENT-RESPONSE" in result.headers


def test_payment_amount_mismatch_returns_402_with_error():
    fake_payment = {"order_id": "order_1", "amount": 1, "status": "captured"}
    agent = MerchantAgent(
        razorpay_client=FakeRazorpayClient(payment=fake_payment, signature_valid=True),
        llm_client=FakeLLMClient(),
    )
    header = _make_x_payment_header("/products/mechanical-keyboard-65")
    result = agent.handle_request("mechanical-keyboard-65", header)
    assert result.status_code == 402
    assert "amount" in result.body["error"]


def test_bad_signature_returns_402_with_error():
    product = get_catalog().get("mechanical-keyboard-65")
    fake_payment = {"order_id": "order_1", "amount": product.price_paise, "status": "captured"}
    agent = MerchantAgent(
        razorpay_client=FakeRazorpayClient(payment=fake_payment, signature_valid=False),
        llm_client=FakeLLMClient(),
    )
    header = _make_x_payment_header("/products/mechanical-keyboard-65")
    result = agent.handle_request("mechanical-keyboard-65", header)
    assert result.status_code == 402
    assert "signature" in result.body["error"]


def test_resource_mismatch_returns_402_with_error():
    agent = MerchantAgent(
        razorpay_client=FakeRazorpayClient(payment={}, signature_valid=True),
        llm_client=FakeLLMClient(),
    )
    header = _make_x_payment_header("/products/some-other-product")
    result = agent.handle_request("mechanical-keyboard-65", header)
    assert result.status_code == 402
    assert "resource" in result.body["error"]


def test_upsell_offer_is_capped_at_configured_discount():
    settings = get_settings()
    huge_discount = settings.max_upsell_discount_percent + 50
    llm = FakeLLMClient(
        {
            "offer_upsell": True,
            "product_id": "keycap-set-pbt-129",
            "discount_percent": huge_discount,
            "reason": "bundle deal",
        }
    )
    agent = MerchantAgent(llm_client=llm)
    result = agent.handle_request("mechanical-keyboard-65")
    assert result.status_code == 402
    upsell = result.body.get("upsell")
    assert upsell is not None
    assert upsell["discountPercent"] <= settings.max_upsell_discount_percent


def test_kill_switch_active_rejects_request_before_any_processing():
    """The kill switch must gate handle_request itself -- the only live HTTP
    endpoint that processes anything (GET /products/{id}) -- not just the
    in-process BuyerAgent purchase path. See Day 3 live-verification
    incident in BUILD_LOG.md: this was found missing by testing against the
    real Render deployment."""
    agent = MerchantAgent(llm_client=FakeLLMClient())
    agent.trust_guard.kill_switch.activate("live verification test")
    result = agent.handle_request("mechanical-keyboard-65")
    assert result.status_code == 503
    assert "kill switch" in result.body["error"]

    agent.trust_guard.kill_switch.deactivate()
    result = agent.handle_request("mechanical-keyboard-65")
    assert result.status_code == 402  # back to normal


def test_upsell_offer_ignores_product_outside_related_whitelist():
    llm = FakeLLMClient(
        {
            "offer_upsell": True,
            "product_id": "not-a-real-related-product",
            "discount_percent": 10,
            "reason": "hallucinated",
        }
    )
    agent = MerchantAgent(llm_client=llm)
    result = agent.handle_request("mechanical-keyboard-65")
    assert result.status_code == 402
    assert result.body.get("upsell") is None


# -- anonymous (caller_id) trust wiring: the GET /products/{id} path -----------
#
# Reproduces, at the MerchantAgent level, the exact gap found by testing
# against the live Render deployment: /products/{id} previously ran no
# trust checks beyond the kill switch. `caller_id` is only set when a real
# HTTP caller (no signed agent credential) is asking -- see main.py.


class CountingFakeRazorpayClient(FakeRazorpayClient):
    def __init__(self, payment: dict | None = None, signature_valid: bool = True):
        super().__init__(payment, signature_valid)
        self.fetch_calls = 0

    def fetch_payment(self, payment_id: str) -> dict:
        self.fetch_calls += 1
        return self.payment


def test_anonymous_purchase_over_spend_cap_is_rejected_before_verifying_payment():
    settings = get_settings()
    razorpay = CountingFakeRazorpayClient(payment={"order_id": "order_1", "amount": 1_899_900, "status": "captured"})
    agent = MerchantAgent(razorpay_client=razorpay, llm_client=FakeLLMClient())

    # monitor-27-1440p-144hz lists at 1,899,900 paise -- well above
    # max_single_transaction_paise (500,000 by default).
    header = _make_x_payment_header("/products/monitor-27-1440p-144hz", payment_id="pay_over_cap")
    result = agent.handle_request("monitor-27-1440p-144hz", header, caller_id="1.2.3.4")

    assert result.status_code == 402
    assert "spend_cap" in result.body["error"]
    assert razorpay.fetch_calls == 0, "a rejected purchase must never reach payment verification"


def test_anonymous_purchase_duplicate_payment_id_is_deduped():
    product = get_catalog().get("mechanical-keyboard-65")
    razorpay = CountingFakeRazorpayClient(
        payment={"order_id": "order_1", "amount": product.price_paise, "status": "captured", "email": "buyer@example.com"}
    )
    agent = MerchantAgent(razorpay_client=razorpay, llm_client=FakeLLMClient())
    header = _make_x_payment_header("/products/mechanical-keyboard-65", payment_id="pay_dup")

    first = agent.handle_request("mechanical-keyboard-65", header, caller_id="1.2.3.4")
    assert first.status_code == 200
    assert razorpay.fetch_calls == 1

    second = agent.handle_request("mechanical-keyboard-65", header, caller_id="1.2.3.4")
    assert second.status_code == 200
    assert second.body["transaction"] == first.body["transaction"]
    assert razorpay.fetch_calls == 1, "duplicate payment_id must not re-verify against Razorpay a second time"


def test_anonymous_purchase_velocity_limit_fires_per_caller():
    settings = get_settings()
    product = get_catalog().get("mechanical-keyboard-65")
    razorpay = CountingFakeRazorpayClient(
        payment={"order_id": "order_1", "amount": product.price_paise, "status": "captured"}
    )
    agent = MerchantAgent(razorpay_client=razorpay, llm_client=FakeLLMClient())

    for i in range(settings.max_purchases_per_minute):
        header = _make_x_payment_header("/products/mechanical-keyboard-65", payment_id=f"pay_velo_{i}")
        result = agent.handle_request("mechanical-keyboard-65", header, caller_id="9.9.9.9")
        assert result.status_code == 200, f"attempt {i} unexpectedly failed: {result.body}"

    header = _make_x_payment_header(
        "/products/mechanical-keyboard-65", payment_id=f"pay_velo_{settings.max_purchases_per_minute}"
    )
    result = agent.handle_request("mechanical-keyboard-65", header, caller_id="9.9.9.9")
    assert result.status_code == 429
    assert "velocity" in result.body["error"]

    # A different caller is unaffected.
    header = _make_x_payment_header("/products/mechanical-keyboard-65", payment_id="pay_velo_other_caller")
    result = agent.handle_request("mechanical-keyboard-65", header, caller_id="1.1.1.1")
    assert result.status_code == 200


def test_signed_buyer_agent_flow_is_unaffected_by_anonymous_trust_wiring():
    """caller_id defaults to None for the in-process BuyerAgent flow -- it
    already ran the full signed TrustGuard.authorize_purchase before
    calling handle_request, so this leg must not re-gate it a second time
    under a different (anonymous) accounting bucket."""
    product = get_catalog().get("mechanical-keyboard-65")
    razorpay = FakeRazorpayClient(payment={"order_id": "order_1", "amount": product.price_paise, "status": "captured"})
    agent = MerchantAgent(razorpay_client=razorpay, llm_client=FakeLLMClient())
    header = _make_x_payment_header("/products/mechanical-keyboard-65", payment_id="pay_signed_1")
    result = agent.handle_request("mechanical-keyboard-65", header)  # no caller_id
    assert result.status_code == 200
