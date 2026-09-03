"""Encode/decode helpers for the x402 request/response cycle.

Flow:
  1. Buyer requests a resource with no payment -> merchant returns HTTP 402
     with a JSON body (PaymentRequiredBody) listing what it accepts.
  2. Buyer completes payment out-of-band (Razorpay Checkout / order+payment),
     then retries the request with an `X-PAYMENT` header: base64(JSON of
     XPaymentHeader).
  3. Merchant verifies the payment (see merchant_agent) and, on success,
     returns HTTP 200 with the resource plus an `X-PAYMENT-RESPONSE` header:
     base64(JSON of XPaymentResponse).
"""
from __future__ import annotations

import base64
import json

from pydantic import ValidationError

from app.x402.schema import (
    PaymentRequirement,
    PaymentRequiredBody,
    UpsellOffer,
    XPaymentHeader,
    XPaymentResponse,
)

MAX_HEADER_BYTES = 8192  # refuse to even attempt to parse absurdly large headers


def build_payment_required_body(
    *,
    resource: str,
    description: str,
    price_paise: int,
    merchant_id: str,
    category: str,
    upsell: UpsellOffer | None = None,
) -> dict:
    requirement = PaymentRequirement(
        resource=resource,
        description=description,
        maxAmountRequired=str(price_paise),
        payTo=merchant_id,
        extra={"category": category},
    )
    body = PaymentRequiredBody(accepts=[requirement], upsell=upsell)
    return body.model_dump(by_alias=True, exclude_none=True)


def decode_x_payment_header(raw_header: str) -> XPaymentHeader:
    """Decode and validate an incoming X-PAYMENT header. Raises ValueError on
    anything malformed, oversized, or failing schema validation — this is
    untrusted client input."""
    if not raw_header or len(raw_header) > MAX_HEADER_BYTES:
        raise ValueError("X-PAYMENT header missing or exceeds size limit")
    try:
        decoded = base64.b64decode(raw_header, validate=True)
    except Exception as exc:
        raise ValueError("X-PAYMENT header is not valid base64") from exc
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError("X-PAYMENT header does not decode to valid JSON") from exc
    try:
        return XPaymentHeader.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"X-PAYMENT header failed schema validation: {exc}") from exc


def encode_x_payment_response(*, success: bool, transaction: str, payer: str | None = None) -> str:
    response = XPaymentResponse(success=success, transaction=transaction, payer=payer)
    payload = json.dumps(response.model_dump(by_alias=True, exclude_none=True)).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")
