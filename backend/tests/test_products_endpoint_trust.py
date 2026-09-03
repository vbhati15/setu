"""HTTP-level trust wiring on GET /products/{id} -- the endpoint's own
FastAPI app (`main.get_merchant_agent()`) uses the real Razorpay SDK client,
so only checks that short-circuit *before* `_verify_payment` (kill switch,
spend cap, category, velocity, daily spend -- all in
`TrustGuard.authorize_anonymous_purchase`) can be exercised here without a
real network call to Razorpay. Full-flow checks that need a completed
payment (idempotency returning a cached 200, velocity building up several
successful attempts) are covered against a FakeRazorpayClient in
test_merchant_agent.py instead -- this file proves the wiring reaches the
real endpoint, not the trust-layer logic itself (already covered
elsewhere)."""
import base64
import json

from fastapi.testclient import TestClient

from backend.app.main import app, get_merchant_agent

client = TestClient(app)


def _make_x_payment_header(resource: str, order_id="order_1", payment_id="pay_1", signature="sig_1") -> str:
    payload = {
        "x402Version": 1,
        "scheme": "razorpay-inr",
        "network": "razorpay-test",
        "resource": resource,
        "payload": {"orderId": order_id, "paymentId": payment_id, "signature": signature},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_unpaid_quote_is_unaffected_by_trust_wiring():
    resp = client.get("/products/mechanical-keyboard-65")
    assert resp.status_code == 402


def test_over_spend_cap_purchase_is_rejected_before_any_razorpay_call():
    header = _make_x_payment_header("/products/monitor-27-1440p-144hz", payment_id="pay_http_over_cap")
    resp = client.get("/products/monitor-27-1440p-144hz", headers={"X-PAYMENT": header})
    assert resp.status_code == 402
    assert "spend_cap" in resp.json()["error"]


def test_kill_switch_still_takes_priority_over_anonymous_trust_checks():
    from backend.app.config import get_settings

    admin_key = get_settings().admin_api_key
    client.post("/admin/kill-switch/activate", json={"reason": "test"}, headers={"X-ADMIN-KEY": admin_key})
    try:
        header = _make_x_payment_header("/products/mechanical-keyboard-65", payment_id="pay_http_ks")
        resp = client.get("/products/mechanical-keyboard-65", headers={"X-PAYMENT": header})
        assert resp.status_code == 503
        assert "kill switch" in resp.json()["error"]
    finally:
        client.post("/admin/kill-switch/deactivate", headers={"X-ADMIN-KEY": admin_key})
