# THREAT_MODEL.md

> Status: skeleton (Day 1). Expand as the Buyer Agent and policy/trust layer
> land — that's where most of the interesting attack surface is.

## Assets

- Razorpay test-mode credentials (`.env`, never committed).
- Gemini API key (`.env`, never committed).
- Merchant catalog integrity (prices/categories must not be attacker-
  influenced).
- Payment verification correctness (no double-spend, no under-payment).

## Known risks already mitigated (Day 1)

- **Prompt injection via catalog/request data**: catalog fields are
  Pydantic-validated (id pattern, length caps, control-character rejection)
  before ever reaching a Gemini prompt; only the pre-validated
  `related()` whitelist is ever shown to the model. See
  `backend/app/catalog/catalog.py` and `merchant_agent/agent.py`.
- **X-PAYMENT header abuse**: size-capped, base64/JSON/schema validated
  before use; a `resource` mismatch (paying for product A, replaying against
  product B) is rejected. See `x402/protocol.py`.
- **LLM-controlled discount escalation**: `discount_percent` from Gemini is
  clamped server-side to `settings.max_upsell_discount_percent`; a
  hallucinated `product_id` outside the catalog whitelist is discarded.
- **Live-mode credential leakage**: `config.py` refuses to boot if
  `SETU_ENV=test` but the Razorpay key looks like a live key, and refuses to
  boot in live mode at all (not yet supported).
- **Cross-origin API abuse**: now that the backend is deployed and publicly
  reachable (Render), `CORSMiddleware` restricts browser-originated requests
  to an explicit allow-list (`config.cors_allowed_origins`: the deployed
  Vercel origin + local dev). Verified: a disallowed `Origin` header gets a
  response with no `Access-Control-Allow-Origin` header, so a browser
  blocks script access to it. Note this only constrains *browser* JS
  callers — it is not an auth boundary, and any non-browser client (curl,
  another server) can call the API directly regardless of CORS. Real
  authorization is still the x402 payment-verification path, not CORS.

## Known risks already mitigated (Day 2)

- **Negotiated-price tampering**: a buyer cannot pay less than what the
  Zeuthen engine actually agreed to and claim the resource — payment
  verification checks the fake-Razorpay payment amount against
  `agreed_price_paise`, a value only code that ran a full negotiation to
  completion can produce (never taken from client/buyer input). See
  `MerchantAgent.handle_request` / `_verify_payment`.
- **LLM cannot move the price**: the negotiation math
  (`backend/app/bargaining/zeuthen.py`) has no LLM involvement at all;
  Gemini only phrases a round's already-decided numbers as a sentence for
  the trace. A malformed or adversarial LLM response degrades trace
  readability, not the negotiated price — see `BuyerAgent._phrase`'s
  fallback and `BARGAINING.md`.
- **Merchant's reservation price is never exposed to the buyer's decision
  logic**: `BuyerAgent` only ever calls `MerchantParty.risk()`/`.utility()`
  through the shared negotiation engine, never reads `min_price_paise`
  directly to decide its own offers.

## Known gaps (tracked, not yet mitigated)

- **Payment replay**: a valid `payment_id` is not yet recorded as "spent" —
  the same receipt could in principle be replayed against the same resource
  more than once. Needs an idempotency store (Day 3, policy/trust layer).
- **Velocity/spend limits**: `max_purchases_per_minute/hour` and
  `max_daily_spend_paise` exist in config but are not yet enforced anywhere
  — no request currently increments a counter. This now matters more: an
  unattended negotiation loop could in principle be pointed at many
  products back-to-back with no per-run spend cap beyond each negotiation's
  own budget parameter.
- **Negotiation engine holds both parties' private reservation prices in
  one process** — a simulation simplification, not a real two-party
  protocol; see "What this does not model" in `BARGAINING.md`. Not a
  vulnerability in this codebase today (single process, no real
  information asymmetry to violate), but would need addressing before a
  Buyer Agent and Merchant Agent ever ran as separate services.
- **Buyer Agent has no policy/spend-approval layer yet** — it will
  negotiate up to whatever `budget_paise` it's called with; there's no
  Day-3 human-approval-above-threshold gate in front of it yet.

## Out of scope for a hackathon demo

- DoS / rate-limit hardening beyond the config values above.
- Multi-tenant isolation (single merchant, single catalog today).
- Real (live-mode) payment security — test-mode only.
