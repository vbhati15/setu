from backend.app.config import get_settings
from backend.app.trust.guard import TrustGuard
from backend.app.trust.identity import AgentIdentity, build_signed_request


def _guard() -> TrustGuard:
    return TrustGuard(settings=get_settings())


def _identity_and_credential(guard: TrustGuard, agent_id="buyer-1", max_spend_paise=None, categories=None):
    settings = get_settings()
    identity = AgentIdentity.generate(agent_id)
    credential = guard.issuer.issue(
        agent_id=agent_id,
        public_key_b64=identity.public_key_b64,
        max_spend_paise=max_spend_paise if max_spend_paise is not None else settings.max_single_transaction_paise,
        allowed_categories=categories if categories is not None else list(settings.allowed_categories),
        ttl_seconds=3600,
    )
    return identity, credential


def test_unsigned_request_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    request.signature = ""  # strip the signature
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "signature"
    assert "unsigned" in result.reason


def test_request_signed_with_wrong_key_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    impostor = AgentIdentity.generate("buyer-1")  # same agent_id, different keypair
    request = build_signed_request(impostor, credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "signature"


def test_credential_from_untrusted_issuer_is_rejected():
    from backend.app.trust.identity import CredentialIssuer

    guard = _guard()
    rogue_issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    settings = get_settings()
    forged_credential = rogue_issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=settings.max_single_transaction_paise,
        allowed_categories=list(settings.allowed_categories),
        ttl_seconds=3600,
    )
    request = build_signed_request(identity, forged_credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "signature"


def test_correctly_signed_request_outside_credential_scope_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard, max_spend_paise=5000)
    request = build_signed_request(identity, credential, {"price_paise": 6000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "credential_scope"
    assert "max_spend_paise" in result.reason


def test_correctly_signed_request_outside_category_scope_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard, categories=["peripherals"])
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="displays")
    assert not result.approved
    assert result.rule == "credential_scope"


def test_valid_in_scope_request_is_approved():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert result.approved
    assert not result.escalate


def test_out_of_platform_bounds_purchase_is_escalated_not_silently_blocked():
    guard = _guard()
    settings = get_settings()
    # credential itself permits a huge spend, but platform policy caps it lower
    identity, credential = _identity_and_credential(guard, max_spend_paise=10_000_000)
    over_cap = settings.max_single_transaction_paise + 1
    request = build_signed_request(identity, credential, {"price_paise": over_cap}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.escalate
    assert result.rule == "spend_cap"
    assert result.reason is not None


def test_replayed_nonce_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    first = guard.authorize_purchase(request, category="peripherals")
    assert first.approved
    second = guard.authorize_purchase(request, category="peripherals")
    assert not second.approved
    assert second.rule == "replay"


def test_stale_request_is_rejected():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    request.issued_at -= guard.freshness_window_seconds + 10
    request.signature = identity.sign(request.signing_payload())
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "replay"


def test_duplicate_idempotency_key_returns_cached_result_without_recharging():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)

    request_1 = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-dup")
    result_1 = guard.authorize_purchase(request_1, category="peripherals")
    assert result_1.approved and not result_1.is_replay
    guard.record_attempt(identity.agent_id)
    guard.store_result("idem-dup", {"transaction": "pay_fake_1"})

    # A second, independently-signed request reusing the same idempotency key
    request_2 = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-dup")
    result_2 = guard.authorize_purchase(request_2, category="peripherals")
    assert result_2.approved
    assert result_2.is_replay is True
    assert result_2.cached_result == {"transaction": "pay_fake_1"}


def test_velocity_limit_blocks_after_too_many_attempts():
    settings = get_settings()
    guard = TrustGuard(settings=settings)
    identity, credential = _identity_and_credential(guard)

    for i in range(settings.max_purchases_per_minute):
        request = build_signed_request(identity, credential, {"price_paise": 1000}, f"idem-{i}")
        result = guard.authorize_purchase(request, category="peripherals")
        assert result.approved, f"attempt {i} unexpectedly rejected: {result.reason}"
        guard.record_attempt(identity.agent_id)
        guard.store_result(f"idem-{i}", {"transaction": f"pay_fake_{i}"})

    request = build_signed_request(
        identity, credential, {"price_paise": 1000}, f"idem-{settings.max_purchases_per_minute}"
    )
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "velocity"
    assert result.escalate


def test_kill_switch_blocks_otherwise_valid_request():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    guard.kill_switch.activate("manual test")
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.rule == "kill_switch"


def test_daily_spend_cap_fires_after_a_sequence_of_individually_valid_transactions():
    settings = get_settings()
    guard = TrustGuard(settings=settings)
    # Give this agent a generous credential so only the platform's daily cap
    # (not credential scope or per-transaction spend_cap) can be the thing
    # that fires.
    identity, credential = _identity_and_credential(guard, max_spend_paise=settings.max_daily_spend_paise * 10)

    price_paise = settings.max_single_transaction_paise  # each transaction is individually within bounds
    num_that_fit = settings.max_daily_spend_paise // price_paise

    for i in range(num_that_fit):
        request = build_signed_request(identity, credential, {"price_paise": price_paise}, f"idem-{i}")
        result = guard.authorize_purchase(request, category="peripherals")
        assert result.approved, f"transaction {i} unexpectedly rejected: {result.reason}"
        guard.record_attempt(identity.agent_id)
        guard.record_spend(identity.agent_id, price_paise)

    # One more individually-valid transaction pushes cumulative spend over
    # the daily cap.
    request = build_signed_request(identity, credential, {"price_paise": price_paise}, f"idem-{num_that_fit}")
    result = guard.authorize_purchase(request, category="peripherals")
    assert not result.approved
    assert result.escalate
    assert result.rule == "daily_spend"
    assert "max_daily_spend_paise" in result.reason


def test_kill_switch_deactivation_allows_requests_again():
    guard = _guard()
    identity, credential = _identity_and_credential(guard)
    guard.kill_switch.activate("manual test")
    guard.kill_switch.deactivate()
    request = build_signed_request(identity, credential, {"price_paise": 1000}, "idem-1")
    result = guard.authorize_purchase(request, category="peripherals")
    assert result.approved
