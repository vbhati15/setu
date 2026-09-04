#!/usr/bin/env python3
"""Standalone verifier for a Setu transaction certificate.

Runs completely offline -- no network call, no import of this repo's
backend package, no trust in the Setu server at all. It only needs:
  - the certificate JSON file (downloaded from the dashboard), and
  - the `cryptography` package (already in requirements.txt).

The certificate carries the issuer's PUBLIC key (`issuer_public_key_b64`);
this script never sees or needs the private key that signed it. Ed25519
signature verification either succeeds (the JSON is byte-for-byte what was
signed) or fails (anything, even one character, changed since signing) --
there is no partial/fuzzy match.

Usage:
    python verify_certificate.py path/to/certificate.json
"""
from __future__ import annotations

import base64
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _canonical(data: dict) -> bytes:
    # Must exactly match the signer's serialization (backend/app/trust/
    # identity.py `_canonical`): sorted keys, no extra whitespace. Any
    # other serialization of the same JSON would produce different bytes
    # and a signature that (correctly) fails to verify.
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_certificate(certificate: dict) -> tuple[bool, str]:
    required = ("issuer_public_key_b64", "signature")
    missing = [k for k in required if k not in certificate]
    if missing:
        return False, f"certificate is missing required field(s): {', '.join(missing)}"

    payload = {k: v for k, v in certificate.items() if k != "signature"}
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(certificate["issuer_public_key_b64"])
        )
        signature = base64.b64decode(certificate["signature"])
        public_key.verify(signature, _canonical(payload))
    except (InvalidSignature, ValueError, TypeError):
        return False, "signature does not match"
    return True, "signature matches -- certificate content is exactly what was signed"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # stdout doesn't support reconfigure (rare); fall back to default encoding

    if len(sys.argv) != 2:
        print("Usage: python verify_certificate.py path/to/certificate.json")
        return 2

    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            certificate = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ Invalid — could not read certificate file: {exc}")
        return 1

    ok, detail = verify_certificate(certificate)

    print(f"Issuer:          {certificate.get('issuer', '?')}")
    print(f"Transaction ID:  {certificate.get('transaction_id', '?')}")
    product = certificate.get("product") or {}
    print(f"Product:         {product.get('name', '?')} ({product.get('id', '?')})")
    price_paise = certificate.get("agreed_price_paise")
    if isinstance(price_paise, (int, float)):
        print(f"Agreed price:    ₹{price_paise / 100:,.2f}")
    print(f"Issued at:       {certificate.get('issued_at', '?')}")
    print()

    if ok:
        print("✓ Valid — this certificate has not been altered")
        return 0
    else:
        print(f"✗ Invalid — {detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
