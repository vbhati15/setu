from backend.app.trust.idempotency import IdempotencyStore


def test_unseen_key_returns_none():
    store = IdempotencyStore()
    assert store.get("key-1") is None


def test_seen_key_returns_stored_result_as_replay():
    store = IdempotencyStore()
    store.store("key-1", {"transaction": "pay_fake_1"})
    record = store.get("key-1")
    assert record is not None
    assert record.is_replay is True
    assert record.result == {"transaction": "pay_fake_1"}


def test_different_keys_are_independent():
    store = IdempotencyStore()
    store.store("key-1", "result-1")
    assert store.get("key-2") is None
    assert store.get("key-1").result == "result-1"
