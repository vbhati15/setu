from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.catalog import get_catalog
from backend.app.config import get_settings
from backend.app.llm import get_llm_client
from backend.app.merchant_agent import MerchantAgent

app = FastAPI(title="Setu", description="Agent-to-Agent Commerce Gateway (hackathon project)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache
def get_merchant_agent() -> MerchantAgent:
    return MerchantAgent(llm_client=get_llm_client())


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "env": settings.setu_env.value}


@app.get("/catalog")
def list_catalog() -> list[dict]:
    return [p.model_dump() for p in get_catalog().all()]


@app.get("/products/{product_id}")
def get_product(product_id: str, x_payment: str | None = Header(default=None, alias="X-PAYMENT")):
    agent = get_merchant_agent()
    result = agent.handle_request(product_id, x_payment)
    return JSONResponse(status_code=result.status_code, content=result.body, headers=result.headers)


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
