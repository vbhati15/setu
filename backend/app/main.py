from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.buyer_agent import BuyerAgent
from backend.app.catalog import get_catalog
from backend.app.config import get_settings
from backend.app.fake_razorpay import FakeRazorpayClient
from backend.app.llm import get_llm_client
from backend.app.merchant_agent import MerchantAgent
from backend.app.trust.guard import TrustGuard

app = FastAPI(title="Setu", description="Agent-to-Agent Commerce Gateway (hackathon project)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@lru_cache
def get_trust_guard() -> TrustGuard:
    """One TrustGuard shared across every agent instance in this process --
    critically, this is what makes the kill switch (and velocity/idempotency/
    daily-spend accounting) actually global across both `/products/{id}`
    (real Razorpay client) and `/negotiate` (fake Razorpay client, see
    `get_negotiation_merchant_agent` below). Two separate TrustGuard
    instances would mean activating the kill switch on one endpoint
    silently leaves the other one running -- exactly the class of gap this
    was built to close."""
    return TrustGuard(settings=get_settings())


@lru_cache
def get_merchant_agent() -> MerchantAgent:
    """Backs GET /products/{id} -- the real x402/Razorpay payment-
    verification path (test-mode Razorpay, real order/payment records)."""
    return MerchantAgent(llm_client=get_llm_client(), trust_guard=get_trust_guard())


@lru_cache
def get_negotiation_razorpay() -> FakeRazorpayClient:
    """Shared in-memory fake payment rail for the /negotiate endpoint --
    same reasoning as the local negotiation_demo.py script (see
    fake_razorpay.py): an unattended negotiation loop must never drive the
    real Checkout widget. One instance shared between the negotiation
    merchant and buyer below, exactly as FakeRazorpayClient's docstring
    requires."""
    return FakeRazorpayClient()


@lru_cache
def get_negotiation_merchant_agent() -> MerchantAgent:
    """A second MerchantAgent instance, backing /negotiate specifically --
    needs its own (fake) Razorpay client, but shares `get_trust_guard()`
    with `get_merchant_agent()` so the kill switch and trust-layer
    accounting are genuinely global, not per-endpoint."""
    return MerchantAgent(
        razorpay_client=get_negotiation_razorpay(),
        llm_client=get_llm_client(),
        trust_guard=get_trust_guard(),
    )


@lru_cache
def get_buyer_agent() -> BuyerAgent:
    """One Buyer Agent per process, reused across every /negotiate call --
    not a fresh identity per request. This is what lets velocity/daily-spend
    accounting actually accumulate across calls (and be tested/observed),
    the same way a single BuyerAgent instance runs multiple scenarios in
    negotiation_demo.py."""
    return BuyerAgent(
        merchant_agent=get_negotiation_merchant_agent(),
        llm_client=get_llm_client(),
        razorpay_client=get_negotiation_razorpay(),
    )


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "env": settings.setu_env.value}


@app.get("/catalog")
def list_catalog() -> list[dict]:
    return [p.model_dump() for p in get_catalog().all()]


def _caller_id(request: Request) -> str:
    """Best-effort identity for an unauthenticated HTTP caller, used only to
    bucket velocity/daily-spend/idempotency accounting for endpoints with no
    signed agent credential (see `MerchantAgent.handle_request`'s
    `caller_id` param). Not an auth boundary -- trivially spoofable/rotated
    by the caller -- see docs/THREAT_MODEL.md."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/products/{product_id}")
def get_product(
    request: Request, product_id: str, x_payment: str | None = Header(default=None, alias="X-PAYMENT")
):
    agent = get_merchant_agent()
    result = agent.handle_request(product_id, x_payment, caller_id=_caller_id(request))
    return JSONResponse(status_code=result.status_code, content=result.body, headers=result.headers)


# -- negotiate: real Buyer/Merchant negotiation over HTTP -------------------
#
# Previously this flow (Zeuthen bargaining, upsell evaluation, payment) only
# existed as a local script (scripts/negotiation_demo.py) -- no deployed
# endpoint ever ran it. Runs against a FakeRazorpayClient (see
# get_negotiation_razorpay above), same as the local script -- an unattended
# HTTP-triggered negotiation must not drive the real Checkout widget.
#
# This endpoint gets full TrustGuard coverage "for free": BuyerAgent already
# signs every purchase attempt with its own issued credential and runs it
# through `MerchantAgent.authorize_purchase` (kill switch, signature,
# credential scope, idempotency, velocity, daily spend, policy bounds)
# before ever touching the payment rail -- see buyer_agent/agent.py
# `_pay_and_collect`. Nothing extra was wired here; using the existing
# signed-agent flow is what closes this gap correctly, rather than building
# a second, weaker anonymous-caller check like /products/{id} needed.


class NegotiateRequest(BaseModel):
    goal_text: str = Field(min_length=1, max_length=500)
    budget_paise: int = Field(gt=0, le=100_000_000)


def _outcome_to_dict(outcome) -> dict:
    return {
        "success": outcome.success,
        "reason": outcome.reason,
        "product": (
            {"id": outcome.product.id, "name": outcome.product.name, "price_paise": outcome.product.price_paise}
            if outcome.product
            else None
        ),
        "agreed_price_paise": outcome.agreed_price_paise,
        "transaction_id": outcome.transaction_id,
        "upsell_purchased": outcome.upsell_purchased,
        "upsell_product": outcome.upsell_product.id if outcome.upsell_product else None,
        "rounds": len(outcome.rounds),
        "trace": [
            {
                "round": t.round_number,
                "speaker": t.speaker,
                "message": t.message,
                "buyer_offer_paise": t.buyer_offer_paise,
                "merchant_offer_paise": t.merchant_offer_paise,
                "buyer_risk": t.buyer_risk,
                "merchant_risk": t.merchant_risk,
            }
            for t in outcome.trace
        ],
    }


@app.post("/negotiate")
def negotiate(body: NegotiateRequest) -> dict:
    buyer = get_buyer_agent()
    outcome = buyer.negotiate_and_purchase(body.goal_text, body.budget_paise)
    return _outcome_to_dict(outcome)


# -- admin: kill switch ---------------------------------------------------
#
# A single global flag that halts all new transaction processing the instant
# it's activated -- see backend/app/trust/kill_switch.py and
# TrustGuard.authorize_purchase, which checks this before any other trust
# check. Protected by a shared admin key (X-ADMIN-KEY header) since it is a
# powerful, deployment-wide control.


class KillSwitchRequest(BaseModel):
    reason: str = "manually triggered"


def _require_admin(x_admin_key: str | None) -> None:
    settings = get_settings()
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="missing or invalid X-ADMIN-KEY header")


@app.get("/admin/kill-switch")
def kill_switch_status() -> dict:
    return get_merchant_agent().trust_guard.kill_switch.status()


@app.post("/admin/kill-switch/activate")
def activate_kill_switch(
    body: KillSwitchRequest, x_admin_key: str | None = Header(default=None, alias="X-ADMIN-KEY")
) -> dict:
    _require_admin(x_admin_key)
    agent = get_merchant_agent()
    agent.trust_guard.kill_switch.activate(body.reason)
    return agent.trust_guard.kill_switch.status()


@app.post("/admin/kill-switch/deactivate")
def deactivate_kill_switch(x_admin_key: str | None = Header(default=None, alias="X-ADMIN-KEY")) -> dict:
    _require_admin(x_admin_key)
    agent = get_merchant_agent()
    agent.trust_guard.kill_switch.deactivate()
    return agent.trust_guard.kill_switch.status()
