# DECISIONS.md

Running log of non-obvious decisions and why they were made. Newest first.

## 2026-09-05 — Negotiation-round phrasing calls parallelized: ~24 sequential Gemini calls to ~1

"Start negotiation" could take close to a minute. Root cause: a tight-budget
negotiation makes up to `negotiation_max_rounds` (12) × 2 live Gemini
phrasing calls, and `BuyerAgent._render_trace` made them one at a time. By
the time that function runs, `run_zeuthen_negotiation` has already produced
every round's final numbers — phrasing never feeds back into the math (see
`docs/BARGAINING.md`) — so every one of those ~24 calls is independent of
every other. `_render_trace` now submits all of them to a
`ThreadPoolExecutor` at once and reassembles the trace in original round
order afterward. Turns wall-clock cost from "sum of ~24 calls" into
"roughly the slowest single call." A negotiation's fallback phrasing path
(used when an individual call fails or times out) is untouched — a
rate-limited call under load still degrades to the templated sentence, same
as before, just now possibly for several rounds in parallel rather than one
that stalls everything behind it.

## 2026-09-05 — Found and fixed: a stale local backend process was silently serving pre-`auto_pay` code

While live-testing the certificate feature, a real multi-round negotiation
converged to a genuine deal but the result card showed "Couldn't be
completed" instead of a checkout button. `frontend/src/lib/rules.js`'s
`classifyOutcome` only reaches that verdict when the backend's `reason` text
contains "rejected by trust layer" — text the *current* `_negotiate` code
cannot produce when `auto_pay=false`, since it returns a `checkout_token`
before ever calling `_pay_and_collect`/`TrustGuard` (see the "Two payment
rails" entry below). The only way to see that text is a backend still
running code from before the `auto_pay`/checkout-token feature existed,
which pays immediately regardless of the request field — and, having been
running since well before this session's edits, its shared `BuyerAgent`
singleton had also accumulated enough local-testing purchases to trip
`velocity`/`daily_spend` on top of that.

**Not a code bug — a stale dev-process trap worth naming**: `uvicorn --reload`
watches file changes, but a process started before a large batch of backend
edits (or one whose reloader silently died) keeps serving the old module
indefinitely with no visible warning; the frontend (Vite HMR) reloads
instantly, so only the backend half of the stack goes stale, and the
symptom (a plausible-looking trust-layer rejection) looks like a real logic
bug rather than a stale-process problem. Fixed by killing the stale process
and starting a fresh one; confirmed via a direct `curl POST /negotiate` that
the new process correctly returns `payment_pending: true` + a real
`checkout_token`. No code changed.

## 2026-09-05 — Signed transaction certificates: reused the existing Ed25519 issuer key, didn't mint new crypto

When a human-triggered checkout actually completes (`POST /checkout/confirm`
returns 200 — see the entry directly below this one for that flow), the
backend now also returns a small `certificate` object: product, agreed
price, transaction id, timestamp, and the list of trust checks that
transaction actually passed, all signed with Ed25519
(`backend/app/certificate.py`). The dashboard's result card gets a
"Download verification certificate" button that saves this JSON verbatim.

**Why this is worth doing at all:** every other "proof" in this dashboard
(the audit log, the decision trace) is us describing our own trust layer.
A certificate the visitor can download and check *without calling our API
again* is a different, stronger claim — the recipient never has to trust
this backend at all, only basic Ed25519 math.

**Key reuse, not new crypto:** the certificate is signed with
`trust_guard.issuer`'s keypair — the exact same `CredentialIssuer` that
already signs every `AgentCredential` (see `backend/app/trust/identity.py`).
`CredentialIssuer.sign_payload` is a two-line addition reusing the same
canonical-JSON-then-Ed25519-sign convention `issue()` already uses; no new
key generation, storage, or algorithm choice was needed.

**Why the checklist isn't literally `SIGNED_PIPELINE`:** the frontend's
Decision Trace panel (`frontend/src/lib/rules.js`) shows the *signed-agent*
8-check pipeline (`TrustGuard.authorize_purchase`) — kill switch, request
signature, replay, credential scope, velocity, daily spend, spend cap,
category. But a human-triggered checkout never goes through that path; it
runs `authorize_anonymous_purchase` (no signed agent request exists to
check a signature/replay/credential-scope against — see
`backend/app/trust/guard.py`) plus the Razorpay payment-verification checks
in `MerchantAgent._verify_payment`. Reusing `SIGNED_PIPELINE`'s labels
verbatim would have claimed checks that never ran for this transaction.
`certificate.py`'s `TRUST_CHECKS_PASSED` instead lists, in real execution
order, exactly the checks `POST /checkout/confirm` actually runs — still
worded the same way as the Decision Trace panel, just honest about which
ones apply here.

**Standalone verification, deliberately outside the backend package:**
`verify_certificate.py` lives at the repo root and only imports `cryptography`
(already in `requirements.txt`) — no import of `backend.app`, no network
call. It recomputes the same canonical JSON encoding the signer used,
verifies the Ed25519 signature with the certificate's own embedded
*public* key, and prints a plain valid/invalid verdict. See
`README.md` for the exact command.

**What this does and doesn't prove:** a valid signature proves the JSON is
byte-for-byte what `setu-platform`'s issuer key signed — tampering with
any field (price, product, transaction id, even one character) breaks
verification, which is the property that matters for "is this receipt
real." It does not, on its own, prove that key belongs to a trustworthy
Setu instance (there's no CA chain here) — same self-signed-cert caveat as
the credentials this reuses. Scoped deliberately to the checkout-confirm
flow only (the one path with a downloadable result card); the scenario
harness's `auto_pay=true` path was left alone.

**Closed with a real end-to-end run, not just the code-path demo above**:
after fixing the stale-backend issue (see the entry above), an actual
person completed a real Razorpay test-mode Checkout in their own browser,
downloaded the certificate the button produced from their actual Downloads
folder, and ran `verify_certificate.py` against that exact file:

```
Transaction ID:  pay_TY6AQ50iNNS6nZ
Product:         Mechanical Keyboard — Hot-swap, 65% (mechanical-keyboard-65)
Agreed price:    ₹3,499.00
✓ Valid — this certificate has not been altered
```

Then, on a copy of that same real (not synthetic) file with one digit
changed:

```
✗ Invalid — signature does not match
```

## 2026-09-05 — Two payment rails, split by who's actually clicking: fake for automation, real Razorpay Checkout for a human

`POST /negotiate` now has an `auto_pay` field (default `true`) that decides
which of two genuinely different payment paths a completed negotiation
takes:

- **`auto_pay=true` (default) — the fake rail, unchanged.** The scenario
  harness (`backend/app/scripts/scenario_harness.py`) and any other
  backend-automated caller never sets this field, so `BuyerAgent` keeps
  paying itself against `FakeRazorpayClient` exactly as before (see the
  2026-09-02 entry below on why: an unattended loop can't click through
  Razorpay's real Checkout widget without tripping its own bot detection).
  Nothing about this path changed.
- **`auto_pay=false` — real Razorpay test-mode Checkout, only for a human.**
  The dashboard's "try it yourself" and "surprise me" flows always send
  `auto_pay: false`. `BuyerAgent.negotiate_and_purchase` still runs the real
  Zeuthen negotiation (or accepts list price) exactly as before, but stops
  *before* paying: it returns `payment_pending: true` and a short-lived,
  HMAC-signed `checkout_token` (`backend/app/checkout_quote.py`) binding the
  exact `(product_id, agreed_price_paise)` the negotiation actually closed
  at. The frontend then calls `POST /checkout/order` (creates a real
  Razorpay order for that exact amount) and opens the real Checkout widget
  in the visitor's own browser; on success it calls `POST /checkout/confirm`
  with the widget's own `razorpay_order_id`/`razorpay_payment_id`/
  `razorpay_signature`, which is verified through the *same*
  `MerchantAgent.handle_request` / `agreed_price_paise` code path
  `GET /products/{id}` already uses — no new payment-verification logic, no
  parallel trust-checking path to keep in sync.

**Why the token, not a client-supplied price:** if the frontend could just
tell `/checkout/order` "create an order for this amount," a tampered
request could get a real (if test-mode) order created for any price. The
token is signed server-side at the moment the negotiation actually agreed
to a price, and `/checkout/order`/`/checkout/confirm` both derive
`product_id`/`price_paise` from the token itself — never from separate
request fields — so the real order can never be for anything other than
what was actually negotiated.

**Why this doesn't reopen the bot-detection problem the fake rail exists
to avoid:** the thing that gets blocked is a *script* driving the Checkout
widget's own form (typing a card number, clicking through OTP) — not a real
person doing that themselves. `auto_pay=false` hands control to an actual
human clicking a real "Complete your purchase" button in their own browser;
nothing on our side scripts the widget itself. This is the same distinction
`backend/app/scripts/demo_payment.py` already relies on (real order, real
Checkout widget, one manual human click-through) — this feature is that
same pattern, reached through the dashboard instead of a local script.

## 2026-09-04 — Product-mismatch bug: routed around via `product_id`, not fixed at the root

The entry directly below this one ("USB-C Hub → Cable Organizer Kit
mismatch") root-caused but deliberately left unfixed a bug where the "try
it yourself" picker's exact product selection could silently get swapped
for a different, cheaper one. Rather than fixing
`BuyerAgent._find_candidate_product`'s keyword-matching heuristic itself
(the short-token/substring-containment issue described below, which is
inherent to *free-text* product discovery), added an optional `product_id`
to `NegotiateRequest`/`negotiate_and_purchase` (`backend/app/main.py`,
`backend/app/buyer_agent/agent.py`) that, when present, looks the product
up directly via `catalog.get()` and skips keyword matching entirely.

This was the better fix specifically *because* the picker case doesn't need
matching at all — the frontend already knows the exact catalog id the
visitor selected (`selectedProduct.id` from `GET /catalog`), so keyword
scoring was never the right tool for that call site; it exists to serve the
"Surprise me" scenario button, which only ever has free text
(`SCENARIOS[i].goal_text`) and no id to pin to. Fixing the scoring
heuristic instead would have been the *more correct* general fix (it would
also help "Surprise me"), but was a larger, riskier change to a shared
matching function with no test coverage for the specific short-token
failure mode — deferred, not ruled out.

**The `_find_candidate_product` bug described below is still live** for
any caller that doesn't pass `product_id` — currently only the "Surprise
me" path, whose five hardcoded `SCENARIOS` are chosen not to trigger it,
so it doesn't currently manifest in the shipped UI, but a new freeform-text
entry point would hit it again.

Verified live (local backend, two real multi-round Zeuthen negotiations):
pinning `product_id="wireless-mouse-ergo"` at a too-low budget now
correctly stalemates on the wireless mouse instead of silently substituting
`mouse-pad-xl`; the same id at a workable budget closes a real deal on the
wireless mouse. See `BUILD_LOG.md`, 2026-09-04 Day 4 Part 5.

## 2026-09-04 — USB-C Hub → Cable Organizer Kit mismatch: root-caused, deliberately not fixed yet

A `backend/app/llm/logging_client.py::LoggingLLMClient` wrapper already
existed that records latency + estimated cost per LLM call — but it was
never wired into `get_llm_client()` (`backend/app/llm/__init__.py` always
returns a bare `GeminiClient`), so `/negotiate` had no real per-message
timing to pace the dashboard's chat-replay typing indicator against.
Rather than wiring the logging wrapper into the live DI path (a larger,
riskier change touching cost-tracking semantics not otherwise needed),
`BuyerAgent._phrase()` now measures its own call with `time.perf_counter()`
and returns `(message, latency_ms)`, stored on `NegotiationTrace.latency_ms`
and exposed through `_outcome_to_dict`. This measures around *the exact
call site the trace text comes from*, including the exception-fallback
path (a failed/rate-limited Gemini call still reports its real elapsed
time, never `None` used as a stand-in for "fast"). `None` is reserved
for the one case where no LLM call happened at all (`llm_client is None`).

## 2026-09-04 — USB-C Hub → Cable Organizer Kit mismatch: root-caused, deliberately not fixed yet

Investigated a report that selecting "USB-C Hub" with a small budget in the
"try it yourself" form negotiated for a "Cable Organizer Kit" instead, with
no explanation shown. Root cause in
`BuyerAgent._find_candidate_product` (`backend/app/buyer_agent/agent.py`):
tokenizing "USB-C Hub — 7-in-1" splits on non-alphanumerics into
`["usb", "c", "hub"]` — the single letter `"c"` survives (no minimum
token-length filter) and scoring uses substring containment
(`kw in haystack`), so `"c"` spuriously matches almost any product's
name/description/category (e.g. "ac*c*essories", "*c*able"). When the
real match (priced above the visitor's 1.5x-budget ceiling) gets filtered
out, the algorithm falls back to whatever else scored `> 0` — which,
because of the spurious `"c"` match, can be nearly any cheaper product.
Confirmed via direct backend calls, not just log reading. Left unfixed on
explicit instruction ("show me... before fixing anything") — the two
candidate fixes (filter short tokens / require word-boundary matching, and
separately, surfacing an honest "couldn't afford your exact pick" message
when a real substitution *is* intended) are different in scope and the
user hadn't picked between them as of this session's end.

## 2026-09-04 — `scroll-snap-type` changed from `mandatory` to `proximity`

The dashboard's full-viewport snap-scroll sections used
`scroll-snap-type: y mandatory`, which forces an instant, physics-free jump
to the next section on a single wheel tick — fast enough that a section's
scroll-triggered entrance animation (`SectionReveal`, gated on
`whileInView`) often didn't even finish, or finished after the snap had
already settled, reading as "nothing happened" rather than a reveal.
`proximity` still locks each section into place once the scroll is close to
it, but doesn't force that jump mid-transit, so the scroll itself moves at
a pace the entrance animation can actually play alongside. `SectionReveal`
was also changed to trigger earlier (a positive `viewport.margin` that
extends the trigger zone past the visible viewport) rather than waiting for
~35% visibility, so the animation starts before the section has fully
snapped into place instead of after.

## 2026-09-04 — Primary-flow UI never renders raw backend strings; a plain-language layer sits in front of them

Several backend-generated strings that are perfectly fine for a technical
audit view leak implementation detail when shown verbatim in the
visitor-facing negotiation replay: `reason` text embeds trust-layer
internals (`"...paise"`, `max_spend_paise=`, rule names), the round-0
system trace message embeds the internal product slug
(`"Matched product 'X' (usb-c-hub-7in1), list price 189900 paise."`), and
the deterministic LLM-fallback phrase template used to read literally as
`"buyer offer: 189900 paise (risk=1.00)"`. Fixed at two levels rather than
patched per-string: (1) the *fallback phrase template itself*
(`BuyerAgent._fallback_phrase`) was rewritten to speak in rupees and drop
the raw risk readout, since that text can end up as an actual chat message,
not just a log line; (2) `NegotiationChat.jsx` never renders `outcome.reason`
or the raw trace message directly — `plainOutcomeMessage()` derives a
human sentence from the classified verdict, and the "matched product" line
is composed client-side from the clean `outcome.product.name` field instead
of the backend's trace text. The raw strings are untouched and still
correct for `AuditLog`/`DecisionTrace`, which are explicitly the technical
views. Same reasoning extended to the cooldown UI (no "Wait 51s" clock
badge in the primary flow — a plain "Try again in 51s") and to removing any
rendering of `API_BASE_URL` from user-facing copy.

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
