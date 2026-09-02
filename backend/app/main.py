from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
