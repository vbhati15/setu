"""Round-trips a signed transaction certificate through the actual standalone
verify_certificate.py script (imported directly, not reimplemented here) --
the thing that matters is that the real verifier accepts a real certificate
and rejects a tampered one, not a duplicate of its verification logic."""
import importlib.util
import sys
from pathlib import Path

from backend.app.catalog import get_catalog
from backend.app.certificate import TRUST_CHECKS_PASSED, build_certificate
from backend.app.trust.identity import CredentialIssuer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("verify_certificate", _REPO_ROOT / "verify_certificate.py")
verify_certificate_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_certificate_module)
sys.modules.setdefault("verify_certificate", verify_certificate_module)


def _sample_certificate():
    issuer = CredentialIssuer()
    product = get_catalog().all()[0]
    return build_certificate(
        issuer=issuer, product=product, price_paise=product.price_paise, transaction_id="pay_test_123"
    )


def test_certificate_carries_expected_fields():
    cert = _sample_certificate()
    assert cert["transaction_id"] == "pay_test_123"
    assert cert["trust_checks_passed"] == TRUST_CHECKS_PASSED
    assert "signature" in cert and "issuer_public_key_b64" in cert


def test_real_certificate_verifies_with_the_standalone_script():
    cert = _sample_certificate()
    ok, detail = verify_certificate_module.verify_certificate(cert)
    assert ok, detail


def test_tampered_certificate_fails_verification():
    cert = _sample_certificate()
    tampered = dict(cert)
    tampered["agreed_price_paise"] = tampered["agreed_price_paise"] + 1
    ok, detail = verify_certificate_module.verify_certificate(tampered)
    assert not ok
    assert "does not match" in detail


def test_certificate_signed_by_a_different_key_fails_verification():
    cert = _sample_certificate()
    other_issuer = CredentialIssuer()
    forged = dict(cert)
    forged["issuer_public_key_b64"] = other_issuer.public_key_b64
    ok, _ = verify_certificate_module.verify_certificate(forged)
    assert not ok
