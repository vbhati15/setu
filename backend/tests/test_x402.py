import base64
import json

import pytest

from app.x402.protocol import (
    build_payment_required_body,
    decode_x_payment_header,
    encode_x_payment_response,
)


def test_build_payment_required_body_shape():
    body = build_payment_required_body(
        resource="/products/mechanical-keyboard-65",
        description="Hot-swap 65% mechanical keyboard",
        price_paise=349900,
        merchant_id="setu_merchant_test",
        category="peripherals",
    )
    assert body["x402Version"] == 1
    assert len(body["accepts"]) == 1
    requirement = body["accepts"][0]
    assert requirement["scheme"] == "razorpay-inr"
    assert requirement["network"] == "razorpay-test"
    assert requirement["maxAmountRequired"] == "349900"
    assert requirement["payTo"] == "setu_merchant_test"
    assert requirement["resource"] == "/products/mechanical-keyboard-65"


def _make_header(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_decode_x_payment_header_roundtrip():
    raw = _make_header(
        {
            "x402Version": 1,
            "scheme": "razorpay-inr",
            "network": "razorpay-test",
            "resource": "/products/mechanical-keyboard-65",
            "payload": {
                "orderId": "order_abc",
                "paymentId": "pay_abc",
                "signature": "sig_abc",
            },
        }
    )
    decoded = decode_x_payment_header(raw)
    assert decoded.resource == "/products/mechanical-keyboard-65"
    assert decoded.payload.order_id == "order_abc"
    assert decoded.payload.payment_id == "pay_abc"


def test_decode_x_payment_header_rejects_bad_base64():
    with pytest.raises(ValueError):
        decode_x_payment_header("not-valid-base64!!!")


def test_decode_x_payment_header_rejects_bad_json():
    raw = base64.b64encode(b"not json").decode()
    with pytest.raises(ValueError):
        decode_x_payment_header(raw)


def test_decode_x_payment_header_rejects_missing_fields():
    raw = _make_header({"x402Version": 1, "scheme": "razorpay-inr"})
    with pytest.raises(ValueError):
        decode_x_payment_header(raw)


def test_decode_x_payment_header_rejects_oversized_input():
    huge = "A" * 100_000
    with pytest.raises(ValueError):
        decode_x_payment_header(huge)


def test_encode_x_payment_response_roundtrip():
    encoded = encode_x_payment_response(success=True, transaction="pay_abc", payer="buyer@example.com")
    decoded = json.loads(base64.b64decode(encoded))
    assert decoded["success"] is True
    assert decoded["transaction"] == "pay_abc"
    assert decoded["payer"] == "buyer@example.com"
