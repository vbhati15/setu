from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app, get_merchant_agent

client = TestClient(app)
ADMIN_KEY = get_settings().admin_api_key


def teardown_function(_fn):
    get_merchant_agent().trust_guard.kill_switch.deactivate()


def test_status_starts_inactive():
    resp = client.get("/admin/kill-switch")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_activate_without_admin_key_is_rejected():
    resp = client.post("/admin/kill-switch/activate", json={"reason": "test"})
    assert resp.status_code == 401


def test_activate_with_wrong_admin_key_is_rejected():
    resp = client.post(
        "/admin/kill-switch/activate", json={"reason": "test"}, headers={"X-ADMIN-KEY": "wrong-key"}
    )
    assert resp.status_code == 401


def test_activate_and_deactivate_with_correct_key():
    resp = client.post(
        "/admin/kill-switch/activate", json={"reason": "test halt"}, headers={"X-ADMIN-KEY": ADMIN_KEY}
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert resp.json()["reason"] == "test halt"

    status = client.get("/admin/kill-switch").json()
    assert status["active"] is True

    resp = client.post("/admin/kill-switch/deactivate", headers={"X-ADMIN-KEY": ADMIN_KEY})
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_kill_switch_blocks_the_live_products_endpoint():
    """The real regression test: this is the exact sequence run against
    production (https://setu-59l6.onrender.com) that first exposed the gap
    -- GET /products/{id} used to return its normal 402 completely
    unaffected by kill-switch state. Reproduced here against the real
    FastAPI app (TestClient), not a bypassed in-process call."""
    baseline = client.get("/products/mechanical-keyboard-65")
    assert baseline.status_code == 402

    activate = client.post(
        "/admin/kill-switch/activate", json={"reason": "blocking live traffic test"}, headers={"X-ADMIN-KEY": ADMIN_KEY}
    )
    assert activate.status_code == 200 and activate.json()["active"] is True

    blocked = client.get("/products/mechanical-keyboard-65")
    assert blocked.status_code == 503
    assert "kill switch" in blocked.json()["error"]

    still_active = client.get("/admin/kill-switch").json()
    assert still_active["active"] is True

    deactivate = client.post("/admin/kill-switch/deactivate", headers={"X-ADMIN-KEY": ADMIN_KEY})
    assert deactivate.status_code == 200 and deactivate.json()["active"] is False

    resumed = client.get("/products/mechanical-keyboard-65")
    assert resumed.status_code == 402  # back to normal, matching the pre-kill-switch baseline
