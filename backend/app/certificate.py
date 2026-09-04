"""Signed transaction certificates.

A small, standalone-verifiable proof that a specific purchase happened at a
specific price and passed the platform's trust checks -- signed with the
same Ed25519 "setu-platform" issuer key already used to sign agent
credentials (see trust/identity.py), not a new key or new crypto.

Anyone holding the certificate JSON and the issuer's PUBLIC key (embedded in
the certificate itself) can confirm the certificate hasn't been altered
since it was signed, completely offline -- see verify_certificate.py. That
is the entire point: the recipient never has to trust or even reach this
backend to check it.

Scope note: this certifies the human-triggered checkout flow specifically
(`POST /checkout/confirm`, see main.py) -- the only path in this codebase
that produces a downloadable result card with a real transaction id. The
checks listed below are exactly and only the ones that flow actually runs
(verify_quote_token -> handle_request's anonymous-caller authorization ->
Razorpay payment verification -- see main.py and trust/guard.py
`authorize_anonymous_purchase`), in the order they run. This is a real but
different pipeline from the fully-signed 8-check one shown in the Decision
Trace panel for scenario-harness runs (see frontend/src/lib/rules.js
SIGNED_PIPELINE) -- reusing those exact labels here would claim checks
(signature, replay, credential_scope) that never ran for this transaction,
so this list is deliberately its own, worded the same way.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.catalog import Product
from backend.app.trust.identity import CredentialIssuer

CERTIFICATE_VERSION = 1

# Order matches the real execution order in main.py `confirm_checkout` ->
# MerchantAgent.handle_request -> TrustGuard.authorize_anonymous_purchase /
# MerchantAgent._verify_payment. Every one of these genuinely ran and
# genuinely passed for any certificate this module produces -- generation
# only ever happens after `handle_request` has already returned 200.
TRUST_CHECKS_PASSED = [
    "Price matches the negotiated agreement (signed checkout token)",
    "Kill switch inactive",
    "Within velocity limit",
    "Within daily spend cap",
    "Within per-transaction spend cap",
    "Category allowed",
    "Payment amount matches agreed price",
    "Payment signature verified (Razorpay)",
]


def build_certificate(
    *,
    issuer: CredentialIssuer,
    product: Product,
    price_paise: int,
    transaction_id: str,
) -> dict:
    """Builds and signs one certificate. `issuer` is the same
    CredentialIssuer (trust_guard.issuer) that already signs agent
    credentials -- this reuses its keypair rather than minting a new one."""
    certificate = {
        "certificate_version": CERTIFICATE_VERSION,
        "issuer": issuer.issuer_id,
        "issuer_public_key_b64": issuer.public_key_b64,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "transaction_id": transaction_id,
        "product": {"id": product.id, "name": product.name},
        "agreed_price_paise": price_paise,
        "currency": "INR",
        "trust_checks_passed": TRUST_CHECKS_PASSED,
    }
    certificate["signature"] = issuer.sign_payload(certificate)
    return certificate
