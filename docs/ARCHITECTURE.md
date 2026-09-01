# ARCHITECTURE.md

> Status: skeleton (Day 1). Fill in as the Buyer Agent, bargaining layer, and
> policy/trust layer land (Day 2-3).

## System overview

- **Backend**: FastAPI service (`backend/app`), packaged as `backend.app.*`.
- **Frontend**: React + Tailwind dashboard (`frontend/`), placeholder today.
- **Payments**: Razorpay test-mode (Orders + Payments API), via
  `backend/app/razorpay_client.py`.
- **LLM**: Gemini (free tier), behind a provider-agnostic interface
  (`backend/app/llm/base.py`) so the provider can be swapped without
  touching agent logic.
- **Protocol**: x402 subset (`backend/app/x402/`) — see `PROTOCOL.md`.
- **Merchant Agent**: `backend/app/merchant_agent/` — catalog-backed, speaks
  x402, offers bounded upsells.
- **Buyer Agent**: not yet built (Day 2).
- **Bargaining (Zeuthen strategy)**: not yet built (Day 2/3).
- **Policy/trust layer**: not yet built (Day 3).

## Component diagram

_TODO: add once Buyer Agent + negotiation loop exist._

## Data flow (today)

```
client --GET /products/{id}--> Merchant Agent --check--> Catalog
                                     |
                                     v (unpaid)
                              402 + PaymentRequirements (+ optional upsell)

client --GET /products/{id} + X-PAYMENT--> Merchant Agent --verify--> Razorpay
                                     |
                                     v (verified)
                              200 + resource + X-PAYMENT-RESPONSE
```

## Deployment topology

_TODO — see `DEPLOYMENT.md`._
