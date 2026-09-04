# DECISIONS.md

Running log of non-obvious decisions and why they were made. Newest first.

## 2026-09-04 — Dashboard's decision-trace panel reconstructs the rule checklist client-side rather than having the backend return it

`GET /negotiate`'s response only ever names the *one* rule that failed (or
that a purchase succeeded) — it never returns "here's every check that ran
and passed before that." Rather than adding a new backend field to carry a
full per-check trace, the dashboard reconstructs it in
`frontend/src/lib/rules.js` from two things that are already true by
construction: `backend/app/trust/guard.py`'s `authorize_purchase` runs its
checks in one fixed, hardcoded, sequential order and returns (short-
circuits) at the first failure — so if the API says rule `daily_spend`
failed, every check earlier in that fixed order (kill switch, signature,
replay, credential scope, velocity) is *mechanically guaranteed* to have
passed. The checklist UI renders exactly that guarantee, and only ever
shows a step as failed when it's literally naming the rule the backend
itself returned, with the backend's own reason text verbatim — nothing
inferred or fabricated, just made visible. Trade-off: if `guard.py`'s check
order ever changes, `SIGNED_PIPELINE` in `rules.js` has to change with it
by hand — there's no shared source of truth between the two. Accepted for
now given the order is unlikely to change casually (see the module
docstring in `guard.py`, which itself documents the order as load-bearing).

## 2026-09-04 — `/negotiate`'s per-round Zeuthen risk numbers exist server-side but weren't exposed, and adding them was left uncommitted this session

`backend/app/buyer_agent/agent.py`'s `NegotiationTrace` dataclass has
always carried `buyer_offer_paise` / `merchant_offer_paise` / `buyer_risk`
/ `merchant_risk` per round — but `main.py`'s `_outcome_to_dict` dropped
them before they ever reached an HTTP response, so no caller (dashboard,
harness, or otherwise) could ever have shown the real risk-of-conflict math
driving a negotiation, only the LLM-phrased sentence. Fixing this (Day 4
Part 3, for the dashboard's live negotiation feed) is a purely additive,
backward-compatible response-shape change — confirmed via the full test
suite (122/122 still passing) — but was deliberately left uncommitted, on
explicit instruction not to commit anything that session. Net effect: the
fix exists locally and was verified end-to-end against a local backend
instance, but the live Render deployment does not have it yet, so the
dashboard's risk chart only renders for negotiations run against a backend
that has this change deployed. See `BUILD_LOG.md` (Day 4 Part 3) for the
exact diff and verification evidence, and deploy `backend/app/main.py`
before relying on this for a production demo.

## 2026-09-03 — Gemini model bumped from `gemini-2.0-flash` to `gemini-flash-lite-latest`

Day 1's configured model (`gemini-2.0-flash`) started 404ing with
`This model ... is no longer available` when the Buyer Agent's negotiation
loop actually started calling it for the first time on Day 2 — Day 1's
upsell path had exercised the code but the demo hadn't been re-run since
before the model was deprecated server-side. `gemini-2.5-flash` also 404s
("no longer available to new users"). Queried
`genai.Client(...).models.list()` against the real API key for what's
currently servable. First tried `gemini-3.6-flash` (the model the 404 error
itself recommended) — it worked, but its free tier caps at **20 requests/day
per project per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`),
which the negotiation demo (~20+ calls across 3 scenarios) exhausted almost
immediately, after which every further call 429'd and silently fell back to
the deterministic non-LLM phrasing (see `BuyerAgent._phrase`'s fallback —
this is by design and didn't break the negotiation, just the trace's
natural-language flavor). Switched to `gemini-flash-lite-latest`, which has
a materially higher free-tier daily quota and produced a full clean run
across all three scenarios with no rate-limit fallbacks. Updated
`Settings.gemini_model` default, `.env`, and `.env.example`. **Action
needed**: the Render deployment's `GEMINI_MODEL` env var also needs
updating to `gemini-flash-lite-latest` on redeploy — see
`docs/DEPLOYMENT.md`.

## 2026-09-03 — Zeuthen negotiation uses a single shared engine, not two independent agents inferring each other's utility

A textbook-faithful distributed implementation would have each agent know
only its own utility function and the other's *offers*, inferring
risk/concession behavior from observed moves. Given the Day 2 time budget,
`run_zeuthen_negotiation` is instead handed both parties' reservation
prices directly and computes the whole round-by-round trace as a single
deterministic function — the Buyer Agent and Merchant Agent each own a
`Party` object (`BuyerParty`/`MerchantParty`) exposing `.utility()`/`.risk()`,
but a single call site runs the protocol. The round-by-round trace still
renders it as an explicit buyer-offer/merchant-counter/system-message
exchange so it reads like two negotiating parties, and the algorithm itself
(who concedes, how much) is the real Zeuthen rule — only the "who holds the
private information" framing is simplified. Documented in full in
`docs/BARGAINING.md`.

## 2026-09-03 — Negotiation concession size is risk-proportional with a floor and a cap, not raw risk

Naive "concede by exactly your opponent's risk value" produces risk=1.0 on
both sides in early rounds (opening offers give each party ~0 utility from
the other's offer), which would jump the very first concession straight to
the opponent's asking price — not a negotiation. Added
`negotiation_max_concession_fraction` (default 0.35) alongside the existing
floor `negotiation_min_concession_fraction` (default 0.15, prevents
near-zero risk from stalling progress). Verified empirically (both in
`test_zeuthen.py` and the real negotiation_demo trace) that this produces
genuine multi-round back-and-forth that still converges within the round
cap.

## 2026-09-03 — Negotiation convergence uses a "close enough" gap threshold, not literal offer-crossing

Because each concession is a multiplicative fraction of the remaining gap,
literal convergence (`buyer_offer >= merchant_offer`) is asymptotic and can
take many rounds to close the last few paise. Added
`negotiation_convergence_fraction` (1% of list price) — a remaining gap at
or below that is treated as agreement, deal price = midpoint clamped into
both parties' feasible range. Kept `negotiation_max_rounds` (12) as a hard
backstop regardless.

## 2026-09-03 — Backend dev port moved from 8000 to 8001

`localhost:8000` on the dev machine is silently claimed by Docker Desktop's
backend/WSL relay (`com.docker.backend.exe`) — any request to it gets
routed to Docker instead of our FastAPI app, with no error, just a
different (and confusing) JSON response. Moved the documented dev port to
8001 everywhere (`Makefile`, `vite.config.js` proxy target, README,
`docs/DEPLOYMENT.md`) rather than working around it per-invocation.
Deployed environments (Render) are unaffected — this is a local dev-machine
quirk, not a hosting decision.

## 2026-09-03 — CORS allow-list is config-driven, scoped to known origins only

Deployed the frontend (Vercel) and backend (Render) to different origins,
which meant the browser would block API calls without explicit CORS
headers. Added `cors_allowed_origins` to `Settings` (same config-driven
pattern as spend limits/categories) rather than a wildcard `allow_origins`
— verified a disallowed origin gets no `Access-Control-Allow-Origin` header
back. `allow_methods` is currently just `["GET"]`, matching what the API
actually exposes to browsers today; will need widening if the dashboard
later needs to POST (approve/deny controls, Day 4 scope).

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
