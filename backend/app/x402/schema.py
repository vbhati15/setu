"""Pydantic models for Setu's x402 subset.

Field names/shape follow the real x402 spec (x402Version, accepts[],
maxAmountRequired, payTo, X-PAYMENT / X-PAYMENT-RESPONSE headers). The one
deliberate substitution: `scheme`/`network` identify a Razorpay INR test
payment instead of an EVM "exact" transfer, and `payload` carries a Razorpay
order/payment reference instead of a signed EIP-3009 authorization. See
docs/PROTOCOL.md for the full rationale.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEME: Literal["razorpay-inr"] = "razorpay-inr"
NETWORK: Literal["razorpay-test"] = "razorpay-test"
X402_VERSION = 1


class PaymentRequirement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scheme: Literal["razorpay-inr"] = SCHEME
    network: Literal["razorpay-test"] = NETWORK
    resource: str
    description: str
    mime_type: str = Field(default="application/json", alias="mimeType")
    max_amount_required: str = Field(alias="maxAmountRequired")  # paise, as a string (atomic unit convention)
    asset: str = "INR"
    pay_to: str = Field(alias="payTo")
    extra: dict = Field(default_factory=dict)


class UpsellOffer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(alias="productId")
    name: str
    original_price_paise: int = Field(alias="originalPricePaise")
    discounted_price_paise: int = Field(alias="discountedPricePaise")
    discount_percent: int = Field(alias="discountPercent")
    reason: str


class PaymentRequiredBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    x402_version: int = Field(default=X402_VERSION, alias="x402Version")
    accepts: list[PaymentRequirement]
    upsell: UpsellOffer | None = None
    error: str | None = None


class RazorpayPaymentPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order_id: str = Field(alias="orderId")
    payment_id: str = Field(alias="paymentId")
    signature: str


class XPaymentHeader(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    x402_version: int = Field(default=X402_VERSION, alias="x402Version")
    scheme: Literal["razorpay-inr"] = SCHEME
    network: Literal["razorpay-test"] = NETWORK
    resource: str
    payload: RazorpayPaymentPayload


class XPaymentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    transaction: str
    network: str = NETWORK
    payer: str | None = None
