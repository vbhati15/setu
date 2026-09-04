"""Short-lived, HMAC-signed "checkout quote" tokens.

When a human-triggered negotiation closes (see `BuyerAgent.negotiate_and_purchase`,
`auto_pay=False`), the Buyer Agent has already run the real Zeuthen negotiation
and arrived at an agreed price -- but instead of paying it itself (the fake
rail), it hands the frontend a token binding that exact `(product_id,
price_paise)` pair, signed server-side. `/checkout/order` and
`/checkout/confirm` (see main.py) both require this token and derive the
product/price from it -- never from separate client-supplied fields -- so a
tampered request can never get a real Razorpay order created for anything
other than the price the negotiation actually agreed to.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from backend.app.config import get_settings


class InvalidQuoteToken(ValueError):
    pass


def _sign(body: str) -> str:
    secret = get_settings().checkout_quote_secret.encode()
    return hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()


def build_quote_token(product_id: str, price_paise: int, ttl_seconds: float | None = None) -> str:
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().checkout_quote_ttl_seconds
    payload = {"product_id": product_id, "price_paise": price_paise, "exp": time.time() + ttl}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_sign(body)}"


def verify_quote_token(token: str) -> tuple[str, int]:
    """Returns (product_id, price_paise). Raises InvalidQuoteToken for a
    malformed, tampered, or expired token."""
    if not token or "." not in token:
        raise InvalidQuoteToken("malformed checkout token")
    body, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(body)):
        raise InvalidQuoteToken("checkout token signature does not match")
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception as exc:
        raise InvalidQuoteToken("checkout token payload is not valid") from exc
    if payload.get("exp", 0) < time.time():
        raise InvalidQuoteToken("checkout token has expired")
    return payload["product_id"], int(payload["price_paise"])
