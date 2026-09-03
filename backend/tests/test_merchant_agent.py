import base64
import json

from app.catalog import get_catalog
from app.config import get_settings
from app.llm.base import LLMClient
from app.merchant_agent import MerchantAgent


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
