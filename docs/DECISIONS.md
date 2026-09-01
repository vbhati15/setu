# DECISIONS.md

Running log of non-obvious decisions and why they were made. Newest first.

## 2026-09-02 — `make demo` is semi-automated (one manual Checkout click), not headless

Tried two fully-automated payment-completion paths and rejected both:
S2S UPI Collect (`/v1/payments/create/upi`) 404s because it needs Razorpay
Support to enable VPA validation per-account, and headless Playwright
automation of the real Checkout widget hangs forever on "Sending OTP"
behind Razorpay's PerimeterX/HUMAN Security bot detection. Chose not to
pursue defeating that bot detection further — even in test mode, that's
adversarial automation against a payment provider's fraud tooling, not a
reasonable thing to engineer around for a demo script. Instead, `make demo`
creates a real order via the SDK, opens the real Checkout widget in a
visible browser, and waits for a human to complete it with the official
test card. Verified working end-to-end (real captured payment, signature
verified). See `docs/DEPLOYMENT.md`.

## 2026-09-02 — Real catalog swapped in; `related_ids` added for cross-category upsells

User supplied the real 8-product catalog (keyboards/mice/monitors/
accessories) replacing the Day-1 placeholder. Its upsell pairing table
crosses categories (e.g. the 27" monitor pairs with the monitor arm, which
is in `accessories` not `displays`), so same-category matching alone
couldn't express it. Added an explicit `related_ids` field to `Product`
(validated to reference real catalog ids); `Catalog.related()` now prefers
curated `related_ids` and falls back to same-category matching only when a
product has none set.

## 2026-09-02 — x402 adapted to a `razorpay-inr` scheme, not literal crypto x402

Confirmed with the user before implementation. The real x402 spec assumes
on-chain settlement (EIP-3009, a facilitator). Setu settles via Razorpay INR
test-mode. Kept the 402/X-PAYMENT/X-PAYMENT-RESPONSE shape; replaced the
`exact`/EVM scheme with a custom `razorpay-inr` scheme whose payload is a
Razorpay order/payment reference, verified inline by the Merchant Agent
instead of a separate facilitator. Full rationale in `PROTOCOL.md`.

## 2026-09-02 — Placeholder product catalog, not a real one

No real product list was available on Day 1; used a plausible 9-item
digital-goods catalog (confirmed with the user) so the Merchant Agent could
be built and tested end-to-end today. `backend/app/catalog/products.json`
is meant to be swapped for a real list without any code changes.

## 2026-09-02 — LLM provider behind an interface (`llm/base.py`)

Using Gemini (free tier) for all agent LLM calls per user requirement, but
agent code depends only on `LLMClient` (abstract), constructed via
`llm/get_llm_client()`. Swapping providers later (e.g. adding a paid
fallback) means adding one class and changing one function — no agent code
changes.

## 2026-09-02 — Upsell discount enforced in code, not just prompted

Gemini proposes *whether* and *which* related product to upsell, but the
discount percentage is clamped server-side to
`settings.max_upsell_discount_percent` and the product id is checked against
a pre-computed whitelist (same-category catalog entries) regardless of what
the model returns. Treats LLM output as untrusted, not as policy.

## 2026-09-02 — `make demo` uses Razorpay S2S UPI Collect with `success@razorpay`

A pure backend script cannot complete a real card payment (Razorpay
requires Checkout.js/hosted page for PCI compliance). Used Razorpay's own
documented test-mode automation path instead: S2S UPI Collect
(`POST /v1/payments/create/upi`) with the auto-success test VPA. Noted the
Feb 2026 UPI Collect deprecation risk in `DEPLOYMENT.md`.
