"""HTTP-level tests for POST /negotiate -- the first deployed endpoint that
runs the real Buyer/Merchant Zeuthen negotiation flow (previously only
scripts/negotiation_demo.py exercised it). Uses a fake LLM client (real
Gemini is not something an automated test suite should call) and the
endpoint's own FakeRazorpayClient (see main.py `get_negotiation_razorpay`)
-- no real network calls either way."""
import backend.app.main as main
from backend.app.llm.base import LLMClient
from fastapi.testclient import TestClient

client = TestClient(main.app)


class FakeLLMClient(LLMClient):
    def generate_json(self, system_prompt, user_prompt, schema):
        return {"offer_upsell": False}

    def generate_text(self, system_prompt, user_prompt):
        return "scripted negotiation message"


def _use_fake_llm(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: FakeLLMClient())
    main.get_buyer_agent.cache_clear()
    main.get_negotiation_merchant_agent.cache_clear()
    main.get_negotiation_razorpay.cache_clear()


def _deactivate_kill_switch():
    main.get_trust_guard().kill_switch.deactivate()


def test_negotiate_comfortable_budget_succeeds(monkeypatch):
    _use_fake_llm(monkeypatch)
    _deactivate_kill_switch()
    resp = client.post(
        "/negotiate", json={"goal_text": "mechanical keyboard hot-swap", "budget_paise": 500_000}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["transaction_id"] is not None
    assert body["product"]["id"] == "mechanical-keyboard-65"


def test_negotiate_invalid_budget_is_rejected(monkeypatch):
    _use_fake_llm(monkeypatch)
    resp = client.post("/negotiate", json={"goal_text": "keyboard", "budget_paise": -1})
    assert resp.status_code == 422


def test_negotiate_blocked_by_global_kill_switch(monkeypatch):
    """The key proof for task 2: /negotiate shares the same TrustGuard (and
    therefore the same kill switch) as /products/{id} -- activating it via
    the shared admin endpoint halts negotiation too."""
    _use_fake_llm(monkeypatch)
    admin_key = main.get_settings().admin_api_key
    activate = client.post(
        "/admin/kill-switch/activate", json={"reason": "negotiate endpoint test"}, headers={"X-ADMIN-KEY": admin_key}
    )
    assert activate.status_code == 200 and activate.json()["active"] is True
    try:
        resp = client.post(
            "/negotiate", json={"goal_text": "mechanical keyboard hot-swap", "budget_paise": 500_000}
        )
        assert resp.status_code == 200  # negotiate always returns 200; failure is in the body
        body = resp.json()
        assert body["success"] is False
        assert "kill switch" in body["reason"]
        assert body["transaction_id"] is None
    finally:
        client.post("/admin/kill-switch/deactivate", headers={"X-ADMIN-KEY": admin_key})

    # confirm it resumes normally
    resp = client.post("/negotiate", json={"goal_text": "mechanical keyboard hot-swap", "budget_paise": 500_000})
    assert resp.json()["success"] is True


def test_negotiate_over_credential_scope_budget_is_rejected_by_trust_guard(monkeypatch):
    """Budget far beyond the Buyer Agent's own issued credential scope --
    proves the full signed TrustGuard.authorize_purchase path (not just the
    kill switch) is reached from this endpoint."""
    _use_fake_llm(monkeypatch)
    _deactivate_kill_switch()
    settings = main.get_settings()
    resp = client.post(
        "/negotiate",
        json={"goal_text": "27 inch monitor 1440p", "budget_paise": settings.max_single_transaction_paise * 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "trust layer" in body["reason"]
    assert body["transaction_id"] is None
