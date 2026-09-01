from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"


def test_catalog_returns_products():
    resp = client.get("/catalog")
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) >= 5
    assert all("id" in p and "price_paise" in p for p in products)
