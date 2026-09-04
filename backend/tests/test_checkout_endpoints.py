"""HTTP-level tests for /checkout/order and /checkout/confirm.

Like test_products_endpoint_trust.py, this only exercises what short-
circuits *before* a real network call to Razorpay (invalid/tampered token,
kill switch) -- a real order-creation/payment-verification round trip is
verified live, the same way GET /products/{id}'s real-Razorpay path always
has been (see docs/DECISIONS.md, 2026-09-02 and 2026-09-05)."""
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.checkout_quote import build_quote_token

client = TestClient(main.app)


def _deactivate_kill_switch():
    main.get_trust_guard().kill_switch.deactivate()


def test_checkout_order_rejects_invalid_token():
    resp = client.post("/checkout/order", json={"checkout_token": "not-a-real-token"})
    assert resp.status_code == 400


def test_checkout_order_rejects_expired_token():
    token = build_quote_token("cable-organizer-kit", 44_900, ttl_seconds=-1)
    resp = client.post("/checkout/order", json={"checkout_token": token})
    assert resp.status_code == 400


def test_checkout_order_blocked_by_kill_switch_before_any_real_razorpay_call():
    admin_key = main.get_settings().admin_api_key
    activate = client.post(
        "/admin/kill-switch/activate", json={"reason": "checkout order test"}, headers={"X-ADMIN-KEY": admin_key}
    )
    assert activate.status_code == 200
    try:
        token = build_quote_token("cable-organizer-kit", 44_900)
        resp = client.post("/checkout/order", json={"checkout_token": token})
        assert resp.status_code == 503
    finally:
        client.post("/admin/kill-switch/deactivate", headers={"X-ADMIN-KEY": admin_key})


def test_checkout_order_rejects_unknown_product():
    # A validly-signed token (this process's own secret) for a product that
    # no longer exists in the catalog -- still must not proceed to Razorpay.
    _deactivate_kill_switch()
    token = build_quote_token("does-not-exist-in-catalog", 44_900)
    resp = client.post("/checkout/order", json={"checkout_token": token})
    assert resp.status_code == 404


def test_checkout_confirm_rejects_invalid_token():
    resp = client.post(
        "/checkout/confirm",
        json={
            "checkout_token": "not-a-real-token",
            "razorpay_order_id": "order_x",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "sig_x",
        },
    )
    assert resp.status_code == 400


def test_checkout_confirm_rejects_tampered_token():
    token = build_quote_token("cable-organizer-kit", 44_900)
    body, _, signature = token.partition(".")
    tampered = f"{body[:-1]}{'a' if body[-1] != 'a' else 'b'}.{signature}"
    resp = client.post(
        "/checkout/confirm",
        json={
            "checkout_token": tampered,
            "razorpay_order_id": "order_x",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "sig_x",
        },
    )
    assert resp.status_code == 400
