# ARCHITECTURE.md

> Status: Foundation + Merchant Agent + Buyer Agent + Zeuthen bargaining +
> TrustGuard (kill switch, signature/credential/replay, velocity, daily
> spend, policy bounds) + public dashboard, all live-deployed and
> real-data-verified. See `BUILD_LOG.md` (Day 4 Part 3) for the dashboard
> build and its one open item (a small additive backend change awaiting
> deploy).

## System overview

- **Backend**: FastAPI service (`backend/app`), packaged as `backend.app.*`.
  Deployed on Render.
- **Frontend**: React + Tailwind + Framer Motion dashboard (`frontend/`,
  see `src/App.jsx` and `src/components/`). A real single-page dashboard,
  not a placeholder: a live negotiation trigger against `POST /negotiate`
  with a Zeuthen risk-of-conflict chart, a TrustGuard decision-trace panel,
  the Part 2 scenario-harness's real headline numbers and audit log, and a
  working kill switch against `/admin/kill-switch/*`. Deployed on Vercel —
  see `BUILD_LOG.md` (Day 4 Part 3) for what's built and one pending
  backend deploy needed for full fidelity.
- **Payments**: Razorpay test-mode (Orders + Payments API), via
  `backend/app/razorpay_client.py`.
- **LLM**: Gemini (free tier), behind a provider-agnostic interface
  (`backend/app/llm/base.py`) so the provider can be swapped without
  touching agent logic.
- **Protocol**: x402 subset (`backend/app/x402/`) — see `PROTOCOL.md`.
- **Merchant Agent**: `backend/app/merchant_agent/` — catalog-backed, speaks
  x402, offers bounded upsells, exposes a Zeuthen negotiation party
  (`negotiation_party()`) and verifies payment against either catalog list
  price or a prior negotiated price (`handle_request(..., agreed_price_paise=)`).
- **Buyer Agent**: `backend/app/buyer_agent/` — matches a catalog product to
  a free-text goal + budget (deterministic keyword match), either accepts
  list price outright (budget comfortable) or runs a Zeuthen negotiation,
  then pays via the fake Razorpay client and re-requests the resource with
  an `X-PAYMENT` header at the agreed price.
- **Bargaining (Zeuthen strategy)**: `backend/app/bargaining/zeuthen.py` —
  pure, deterministic utility/risk/concession math, no LLM. See
  `docs/BARGAINING.md` for the full writeup.
- **Fake Razorpay client**: `backend/app/fake_razorpay.py` — in-memory
  order/payment simulation for unattended automated flows (negotiation loop,
  tests). The real `RazorpayClient` (Checkout widget, manual click-through)
  is reserved for the one-off live-integration demo (`make demo`) — see
  `docs/DECISIONS.md`, 2026-09-02.
- **LLM call logging**: `backend/app/llm/logging_client.py` — wraps any
  `LLMClient`, records latency + estimated token cost per call.
- **Policy/trust layer**: `backend/app/trust/` — `TrustGuard`
  (`guard.py`) is the single choke point every purchase passes through:
  kill switch, signature/credential verification, replay defense
  (`identity.py`), credential-scope check, idempotency (`idempotency.py`),
  velocity (`velocity.py`), daily spend cap (`daily_spend.py`), and policy
  bounds (`policy.py` — spend cap, category). One `TrustGuard` instance is
  shared across every agent in the process, so the kill switch and
  velocity/spend accounting are genuinely global across `/negotiate` and
  `/products/{id}`. Every rule is live-verified against production — see
  `BUILD_LOG.md`'s Day 4 entries and `docs/THREAT_MODEL.md`.

## Component diagram

```
BuyerAgent.negotiate_and_purchase(goal, budget)
  |
  +--> _find_candidate_product()            [deterministic keyword match]
  +--> MerchantAgent.handle_request()       [get list price + any upsell]
  |
  +-- budget >= list price? --------------- yes --> pay list price, maybe upsell
  |
  +-- no --> MerchantAgent.negotiation_party()
              |
              v
        run_zeuthen_negotiation(BuyerParty, MerchantParty)  [deterministic]
              |
              v
        deal / stalemate / max_rounds_exceeded
              |
        (LLM phrases each round for the trace -- flavor only)
              |
        deal --> FakeRazorpayClient.pay_order() --> MerchantAgent.handle_request(
                    agreed_price_paise=deal_price)  [verifies against agreed price]
```

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

```
Browser --> Vercel (frontend, static + client fetch)
                |
                v  fetch(<VITE_API_URL> + /health | /catalog | /negotiate
                |         | /admin/kill-switch[/activate|/deactivate])
            Render (backend, FastAPI/uvicorn)
                |
                v
            Razorpay test-mode API + Gemini API
```

CORS on the backend (`backend/app/config.py: cors_allowed_origins`) allows
only the Vercel origin and `localhost:5173` — see `THREAT_MODEL.md`. Full
walkthrough in `DEPLOYMENT.md`.
