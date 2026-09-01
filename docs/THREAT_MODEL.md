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

## Known gaps (tracked, not yet mitigated)

- **Payment replay**: a valid `payment_id` is not yet recorded as "spent" —
  the same receipt could in principle be replayed against the same resource
  more than once. Needs an idempotency store (Day 3, policy/trust layer).
- **Velocity/spend limits**: `max_purchases_per_minute/hour` and
  `max_daily_spend_paise` exist in config but are not yet enforced anywhere
  — no request currently increments a counter.
- **Buyer Agent trust boundary**: undefined until Day 2 — what can a
  Buyer Agent claim about itself, and how much does the Merchant Agent
  trust it?

## Out of scope for a hackathon demo

- DoS / rate-limit hardening beyond the config values above.
- Multi-tenant isolation (single merchant, single catalog today).
- Real (live-mode) payment security — test-mode only.
