import time

from backend.app.trust.identity import (
    AgentIdentity,
    CredentialIssuer,
    build_signed_request,
    verify_signature,
)


def test_agent_can_sign_and_verify_its_own_payload():
    identity = AgentIdentity.generate("buyer-1")
    payload = {"a": 1, "b": "x"}
    signature = identity.sign(payload)
    assert verify_signature(identity.public_key_b64, payload, signature)


def test_signature_from_wrong_key_fails_verification():
    identity = AgentIdentity.generate("buyer-1")
    impostor = AgentIdentity.generate("buyer-2")
    payload = {"a": 1}
    signature = impostor.sign(payload)
    assert not verify_signature(identity.public_key_b64, payload, signature)


def test_tampered_payload_fails_verification():
    identity = AgentIdentity.generate("buyer-1")
    signature = identity.sign({"amount": 100})
    assert not verify_signature(identity.public_key_b64, {"amount": 999999}, signature)


def test_issuer_issued_credential_verifies():
    issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    credential = issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=100_000,
        allowed_categories=["peripherals"],
        ttl_seconds=3600,
    )
    ok, reason = issuer.verify(credential)
    assert ok, reason


def test_credential_signed_by_different_issuer_fails():
    real_issuer = CredentialIssuer()
    rogue_issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    credential = rogue_issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=100_000,
        allowed_categories=["peripherals"],
        ttl_seconds=3600,
    )
    ok, reason = real_issuer.verify(credential)
    assert not ok


def test_expired_credential_fails_verification():
    issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    credential = issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=100_000,
        allowed_categories=["peripherals"],
        ttl_seconds=-1,  # already expired
    )
    ok, reason = issuer.verify(credential)
    assert not ok
    assert "expired" in reason


def test_tampering_with_credential_scope_after_issuance_invalidates_signature():
    issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    credential = issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=100_000,
        allowed_categories=["peripherals"],
        ttl_seconds=3600,
    )
    credential.max_spend_paise = 10_000_000  # attacker tries to raise their own limit
    ok, reason = issuer.verify(credential)
    assert not ok


def test_build_signed_request_roundtrips():
    issuer = CredentialIssuer()
    identity = AgentIdentity.generate("buyer-1")
    credential = issuer.issue(
        agent_id="buyer-1",
        public_key_b64=identity.public_key_b64,
        max_spend_paise=100_000,
        allowed_categories=["peripherals"],
        ttl_seconds=3600,
    )
    request = build_signed_request(identity, credential, {"product_id": "x", "price_paise": 500}, "idem-1")
    assert verify_signature(credential.public_key_b64, request.signing_payload(), request.signature)
