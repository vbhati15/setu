from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, get_merchant_agent

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
