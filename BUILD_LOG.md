# BUILD_LOG.md

## 2026-09-05 — Day 7: full raw-paise audit, root-caused and closed with a shared formatter

**Requested**: this exact bug — a raw paise integer showing up somewhere a
person reads it as rupees — had already been found and fixed piecemeal
several times before. Asked for one complete, final sweep instead of
another one-off patch: grep the whole frontend, check the backend for
unconverted API values, confirm every display location shares one
formatting utility (creating one if it didn't exist), and prove it with
real triggered negotiations, not just a code read.

**Frontend: clean.** `grep -rn "paise" frontend/src/` — every match was the
`_paise` variable-name suffix, the shared `paise()` formatter itself
(`frontend/src/lib/rules.js`), or a comment. The bug was never in the
frontend; it was in backend-generated text the frontend renders verbatim.

**Found: two live, currently-visible bugs in
`backend/app/buyer_agent/agent.py`** — the "accept list price outright" and
"upsell offered" trace lines were plain f-strings with raw
`{amount} paise` in them, sent to the chat as `buyer`/`merchant`-speaker
lines (unlike the per-round negotiation messages, which already went
through correct rupee formatting). One of these was already sitting,
unnoticed, in a real screenshot from earlier in this same session:
`"Budget covers list price (349900 paise) -- accepting outright."`

**Found: a third, more consequential bug class in `backend/app/trust/`**
(`daily_spend.py`, `guard.py`, `policy.py`) — every TrustGuard
rejection/escalation reason string embedded raw paise. Assumed safe at
first, since the primary chat card never shows raw `reason` text — but
tracing `frontend/src/App.jsx` (`liveDecisionExample`) showed it injects
the **real, live** `/negotiate` response into the Decision Trace panel,
which renders raw backend reason text verbatim *by design*. A live
TrustGuard rejection would have put "1809400 paise already spent... cap is
max_daily_spend_paise=2000000 paise" directly into a real, visible panel —
the one leak none of the earlier piecemeal fixes had ever caught.

**Fixed structurally, not per-spot**: new `backend/app/formatting.py`
(`format_rupees`), adopted at every call site that states a rupee amount in
user-facing text — 8 in `buyer_agent/agent.py` plus one each in
`daily_spend.py`/`guard.py`/`policy.py`. Config field names
(`max_daily_spend_paise=`, `max_spend_paise=`) were kept in reasons as
useful technical identifiers; only the numeric values changed. One test
(`test_daily_spend.py::test_recorded_spend_accumulates_toward_cap`) was
itself asserting on a raw paise number (`"5000" in reason`) — updated to
assert the rupee-formatted value instead, since the test was validating the
exact thing this sweep exists to eliminate.

**Verified live, not just read** — and this surfaced an unrelated but real
second issue along the way: restarting the local backend to test the fix
revealed an *orphaned* uvicorn worker process (a leftover multiprocessing
child of a reloader killed earlier in the session) still silently serving
stale pre-fix responses on the same port. Killed the full process tree,
started one clean instance, then ran real requests against it:
- Comfortable-budget accept: `"Budget covers list price (₹3,499.00) --
  accepting outright."`
- An 11-round real Zeuthen negotiation: every offer and the closing
  `"Agreement reached at ₹352.12."` correctly formatted.
- A deliberate credential-scope breach (₹18,999 item, ₹5,000 cap):
  `"requested amount ₹18,999.00 exceeds this agent's credential scope
  (max_spend_paise=₹5,000.00)"` — the exact string that reaches the live
  Decision Trace panel.

`pytest backend/tests` → 140/140 passing; `npm run build` clean. Full
reasoning in `docs/DECISIONS.md`.

**Closed.** Nothing else remains — a final backend-wide grep for
`"} paise"` returns only the one intentional line (the LLM prompt in
`_phrase()`, which correctly needs the raw value to convert accurately, and
is never shown to a user).

## 2026-09-05 — Day 6: signed transaction certificates, negotiation-latency fix, judge-facing README rewrite, and the last open gap closed for real

**Requested across the session**: fix "Start negotiation" taking close to a
minute; add a lightweight but *genuinely verifiable* transaction-certificate
feature (Ed25519-signed, standalone-verifiable, reusing existing crypto, not
a new subsystem); rewrite `README.md` for a judge audience; then, live
debugging of the actual dashboard: a stale local backend process serving
pre-`auto_pay` code, Razorpay test-card/OTP mechanics, and finally a real
human click-through of the whole certificate flow end to end.

**Negotiation latency fix** (`backend/app/buyer_agent/agent.py`) — root
cause: up to 12 rounds × 2 live Gemini phrasing calls, run fully
sequentially, each up to the 20s per-call timeout — the dominant cost of a
negotiation. The phrasing calls are pure flavor text (never feed back into
the Zeuthen math, and by the time `_render_trace` runs, every round's
numbers are already final), so every one of them is independent of every
other. `_render_trace` now fires all of them at once via a
`ThreadPoolExecutor` instead of one-by-one, then reassembles the trace in
original round order. Turns wall-clock cost from "sum of ~24 sequential
calls" into "roughly one call's latency." All 136 backend tests passed
unchanged after the change.

**Signed transaction certificates** — new, tightly scoped feature:
`backend/app/certificate.py` (`build_certificate`), a `CredentialIssuer.sign_payload`
addition reusing the *existing* Ed25519 issuer key (`trust/identity.py`) —
no new crypto, no new key. Wired into `POST /checkout/confirm` (`main.py`):
once a human-triggered purchase actually completes, the response carries a
signed `certificate` — product, price, transaction id, timestamp, and the
real (not `SIGNED_PIPELINE`-copied) list of checks that specific
anonymous-checkout transaction passed. Frontend: a "Download verification
certificate" button + explanatory copy on `NegotiationChat.jsx`'s result
card, wired through `CheckoutButton.jsx`'s `onSuccess` callback. Standalone
verifier `verify_certificate.py` (repo root) — only depends on
`cryptography` (already in `requirements.txt`), no import of this repo's
backend package, no network call; reads the certificate's own embedded
public key and checks the Ed25519 signature against a re-canonicalized copy
of the payload. New test file `backend/tests/test_certificate.py` (4 tests:
expected fields, real verification round-trip through the actual standalone
script, tampering detection, wrong-key forgery detection) — 140/140 backend
tests passing. Full reasoning (especially *why* the certificate's checklist
is deliberately its own wording rather than a copy of the Decision Trace
panel's `SIGNED_PIPELINE`, since the anonymous-checkout path runs a
genuinely different, real pipeline) in `docs/DECISIONS.md`.

**First verified with a code-path-equivalent demo, not yet a live click**: a
real 11-round Zeuthen negotiation run in-process, certificate built with the
same `build_certificate()` main.py calls, verified — `✓ Valid`; one digit
tampered — `✗ Invalid — signature does not match`. Flagged explicitly at the
time as *not* a substitute for an actual human completing a real Razorpay
Checkout and downloading the real button's output.

**`README.md` rewritten for a judge audience** — badges, a "why it's
different" comparison table (deterministic Zeuthen math vs. an LLM
freestyling a price; live-verified trust checks vs. a README claim; a
downloadable signed certificate vs. "trust our database"), two Mermaid
diagrams (system architecture, the 8-step trust pipeline as a flowchart),
tech stack table, project structure tree, an honest "Known limitations"
section, and four image placeholders (`docs/screenshots/*.png`, each with an
`<!-- TODO -->` comment) with a `docs/screenshots/README.md` explaining
exactly what to capture for each filename.

**Live debugging session, three real issues found and fixed in sequence**:

1. **A stale local backend process was serving pre-`auto_pay` code.**
   Symptom: a real multi-round negotiation completed, converged to a genuine
   deal, but the result card showed "Couldn't be completed" /
   `verdict === "rejected"` instead of a checkout button. Root-caused by
   reading `classifyOutcome` (`frontend/src/lib/rules.js`): that verdict is
   only reachable when the backend's `reason` text contains "rejected by
   trust layer" — which the *current* `_negotiate` code cannot produce when
   `auto_pay=false`, since it returns a `checkout_token` before ever calling
   `_pay_and_collect`/`TrustGuard`. The only way to see that text is a
   backend still running pre-`auto_pay` code that pays immediately
   regardless of the request field, hitting the shared `BuyerAgent`
   singleton's accumulated velocity/daily-spend state from a session's worth
   of repeated local testing. Confirmed via process inspection: the running
   `uvicorn` process had started well before this session's edits. Killed it
   (`taskkill /F`) and restarted fresh (`uvicorn --reload`); confirmed via a
   direct `curl POST /negotiate` that the new process correctly returns
   `payment_pending: true` + a real `checkout_token` instead of attempting
   payment.
2. **Razorpay test-mode mechanics** — talked through live: the generic
   `4111 1111 1111 1111` test Visa number was rejected as an "international
   card" (this test account is domestic-only), a placeholder-looking mobile
   number (`9876543210`) was rejected by client-side fraud heuristics that
   run even in test mode. Resolved with Razorpay's actual documented
   domestic test Mastercard (`5267 3181 8797 5449`) / Netbanking's mock
   Success/Failure page, and a less obviously-fake mobile number.
3. **The real end-to-end click-through, finally done by an actual human** —
   closes the gap named explicitly in the 2026-09-05 (Day 5) entry below
   ("the final manual click-through needs to be done and confirmed by an
   actual person"). A comfortable-budget negotiation (Mechanical Keyboard,
   budget covering list price) → real Razorpay test-mode Checkout, completed
   by the user in their own browser → `pay_TY6AQ50iNNS6nZ`, a **real**
   transaction id → "Download verification certificate" button appeared →
   downloaded `setu-certificate-pay_TY6AQ50iNNS6nZ.json` from the browser's
   actual Downloads folder → `python verify_certificate.py` against that
   exact file:
   ```
   Issuer:          setu-platform
   Transaction ID:  pay_TY6AQ50iNNS6nZ
   Product:         Mechanical Keyboard — Hot-swap, 65% (mechanical-keyboard-65)
   Agreed price:    ₹3,499.00
   ✓ Valid — this certificate has not been altered
   ```
   Then, on a copy of that same real file, one digit changed
   (`agreed_price_paise` 349900 → 349800, i.e. ₹3,499.00 → ₹3,498.00):
   ```
   ✗ Invalid — signature does not match
   ```
   This is the strongest available proof for this feature: a real
   negotiation, a real human-completed Razorpay payment, a real downloaded
   file (not a code-path stand-in), verified by the actual standalone
   script, correctly accepting the untouched file and correctly rejecting a
   one-character tamper.

**Closed.** Both gaps named at the end of the 2026-09-05 (Day 5) entry below
— "the real-Checkout flow's actual payment completion... needs to be done
and confirmed by an actual person" and the certificate feature's own
click-through gap — are now closed with real evidence, not a code-path
stand-in. **Still not committed** — see `git status`.

## 2026-09-05 — Day 5: hero redesign, gold theme restored, proof-tab plain-language pass, real negotiation levers (occasion/priority), real Razorpay Checkout for human-triggered deals

**Requested across the session**: a long, iterative round of hero visual
work; reverting the color theme back to black/gold; making every proof-tab
panel actually fit one screen; a full plain-language copy pass across Kill
switch / Decision trace / Test results / Audit log (the previous pass had
missed several of these); diagnosing why negotiations were taking minutes;
two new negotiation-form fields that need to *genuinely* change agent
behavior, not just look like they do; and, as the last and largest piece,
routing real-human negotiations to a real Razorpay Checkout instead of the
fake rail.

**Hero backdrop, iterated to "two connected worlds"**
(`AgentConnectionBackdrop.jsx`) — went through several passes on request:
two small pulsing dot-nodes → bigger Earth-styled spheres (filled
radial-gradient continents, rejected as "too matte") → Lucide's `Earth`
icon (line-art, rejected as too abstract, no visible network) → the
final version: a hand-built SVG globe per side (shaded sphere via
`radialGradient`, five stylized continent paths, a ~24-node scattered
network mesh with connecting lines, all in the gold/ink palette) linked by
the same pulsing offer-packet beam as before. Sized down and requested
smaller twice more (168/190px → 178px both equal → 128px both equal);
animation intensity (opacity, glow, spin speed) reduced on request after
the first "make it real" pass read as too busy.

**Theme reverted crimson → gold/black**: `tailwind.config.js`'s `crimson`
scale (added in an earlier session) replaced back with the original `gold`
scale (`#f0cd7c`/`#e6b95a`/`#d9a441`/`#b8842e`, recovered from git history),
and every `crimson-*` Tailwind class plus hardcoded crimson hex/`rgba(...)`
value across ~15 files mechanically renamed/swapped (`sed`, matching how
the original gold→emerald→crimson renames were done). `ink`/`parchment`
and the separate danger-red states (kill switch active, rejected outcomes)
were untouched — same overlap-with-red-family caveat as before, now with
gold as the brand color instead of crimson.

**Global 80% scale** (`index.css`): `html { font-size: 80%; }`. Since
Tailwind's spacing/sizing/type utilities are rem-based, this scales nearly
the entire UI uniformly — the same lever a browser's own 80% zoom pulls —
requested after the redesigned hero read as too large at 100%. Went via an
intermediate 90% first, then to 80% on request.

**Proof tabs made to actually fit one viewport** — the "Test results" tab
(and, once checked, "Decision trace" too) were taller than a real laptop
viewport, meaning `scroll-snap-stop: always` locked visitors into a partial
view. Fixed by compacting `ProofTabs.jsx`, `StatsHeadline.jsx`,
`OutcomeDonut.jsx`, `DecisionTrace.jsx`, `KillSwitch.jsx`, and `AuditLog.jsx`
(smaller headings, tighter padding/gaps, a smaller donut chart, a capped
audit-log scroll height) until each tab's real rendered height, verified
via a headless-browser screenshot at 1440×816, exactly matched the
viewport with no overflow. A second bug from the same fix: the tab bar was
rendering *under* the page's fixed header (visible cropped at the top of a
screenshot) because the section's top padding (40px) was less than the
header's real height (~57px); fixed by rebalancing the section's padding
(`pt-16 pb-4` instead of a uniform `py-10`) rather than adding padding,
which would have pushed the section taller than the viewport again.

**Plain-language copy pass, completed** — the previous session's pass had
only reached the Test results panel; this session found and fixed the
same problem in the other three tabs, since "it says it's fixed but isn't
everywhere" was flagged directly:
- **Kill switch**: the `/negotiate`/`/products/{id}`/`/admin/kill-switch/*`
  paragraph replaced with "One switch, complete control. If something
  looks wrong, this instantly stops every new transaction — no exceptions,
  no delay. This isn't a demo toggle — it's connected to the real, live
  system." Default activation-reason text changed from the code-comment-ish
  "manually triggered from dashboard" to "Activated manually from the
  dashboard"; the `X-ADMIN-KEY` placeholder changed to "Enter your admin
  key" (the field's function — same header, same value — is unchanged).
- **Decision trace**: the TrustGuard-pipeline paragraph (which named a
  backend file path, `backend/app/trust/guard.py`, directly in user-facing
  copy) replaced with "Before any purchase goes through, we run 8
  independent safety checks, in order. If any single one fails, everything
  stops right there — no partial approvals, no guessing." The per-example
  scenario line (raw harness shorthand like `cable-organizer-kit @
  budget=44900 (exact budget, no upsell room)`) replaced with a
  `friendlySummary()` built from the same response data ("Buying: Cable
  Organizer Kit · Budget: ₹449 (exact match, no room for extras)"), with a
  distinct plain-language note per verdict (approved-with-upsell,
  escalated/daily-spend, rejected/credential-scope). The footer line
  (`verdict: APPROVED · POST /negotiate · 200 · 15001.7ms`) replaced with
  "Result: Approved · Completed in 15 seconds" — raw HTTP method/status
  gone, milliseconds converted to a readable duration.
- **Test results**: the remaining raw backend URL
  (`https://setu-59l6.onrender.com`) removed from the intro line, replaced
  with "We tested Setu against 22 real-world situations — including ones
  designed to try to break it. Here's exactly what happened, every time.";
  `base_url` dropped from the destructured summary entirely so it can't
  silently leak back in. Outcome category labels relabeled
  (`compliant`→"Completed successfully", `escalated`→"Flagged for review",
  `rejected`→"Blocked automatically", `graceful_no_match`→"No good deal
  found", with an added note clarifying that one is a *good* outcome — the
  system correctly recognized no deal made sense rather than forcing a bad
  one). `verification_failed` was deliberately **not** relabeled yet —
  investigated first (it's the harness's own deliberate fake-payment-id
  test methodology working as intended, not a real failure — see
  `scenario_harness.py:190`) and left pending an explicit label choice
  rather than guessing friendly copy that could hide a real problem. The
  rule-breach box's header changed from all-caps mono ("BLOCKED, BY RULE
  (real breaches this run deliberately triggered)") to a small sentence-case
  line, and each rule's presentation redesigned from a two-column grid of
  run-on text into individual rows (a `ShieldAlert` icon, the description,
  and the count as a rounded gold pill), each its own bordered mini-card
  with real spacing between them.
- **Audit log**: description line replaced with "Every single test, in the
  order it happened — with real order numbers, real timestamps, and how
  long each one took." Filter chips and log rows were still showing the raw
  outcome slugs, `POST /negotiate`, HTTP status codes, raw milliseconds, and
  `tx=pay_fake_22` — none of that had actually been touched despite being
  asked for previously. Fixed: filter chips and rows now use the same
  `OUTCOME_LABELS` as the other tabs; `describeEndpoint()` turns
  `POST /negotiate` into "Negotiation"; raw status codes removed entirely;
  `formatDuration()` turns milliseconds into "15 seconds"/"2m 22s";
  `orderNumber()` turns `pay_fake_22` into "Order #22".
- **Consistency fix**: `OUTCOME_LABELS`, `RULE_LABELS`, and `formatDuration`
  were previously duplicated (and, in the audit log's case, simply never
  applied) across `StatsHeadline.jsx`, `OutcomeDonut.jsx`, and
  `DecisionTrace.jsx`. Centralized into `frontend/src/lib/rules.js` as the
  single source of truth, so the same category can no longer read three
  different ways across tabs.

**Root-caused why negotiations were taking minutes**: `GeminiClient`
(`backend/app/llm/gemini_client.py`) never set a request timeout, and a
tight-budget negotiation makes up to 24 real Gemini calls sequentially (2
per round × up to 12 rounds) — one stalled/rate-limited call had no upper
bound at all. Fixed with a 20-second per-call timeout
(`Settings.gemini_timeout_ms`, wired via `genai.Client(http_options=...)`);
a call that would have hung now fails at 20s into the existing fallback
phrasing path (templated sentence, negotiation math unaffected). Verified
live: a negotiation that previously hung indefinitely completed in 164s,
with real per-call latencies showing several genuine ~20.7s timeouts mixed
with several fast (1.7–8s) successful calls — the mechanism, not a guess.
Separately diagnosed a "stuck" report as a distinct issue: an
already-in-flight request (from an infeasible budget/product combo — see
below) left `LiveFeed.jsx`'s `state === "loading"` guard blocking a second
submit; the fix there was "refresh the page," not a code change.

**Two new "try it yourself" form fields, both genuinely behavioral, not
cosmetic** (`LiveFeed.jsx`, `backend/app/buyer_agent/agent.py`,
`backend/app/main.py`):
- **Occasion** ("Gift"/"Personal use"/"Work setup"/"Just browsing") flows
  into the buyer's own system trace line and the *buyer's* LLM phrasing
  prompt only (never the merchant's, never the negotiation math) — verified
  the actual trace text for `occasion="gift"`: "...list price 89900 paise.
  This purchase is a gift for someone else."
- **Priority** ("Best price"/"Fastest deal"/"Open to upsells") changes the
  real Zeuthen parameters a negotiation runs under
  (`_PRIORITY_PARAMS`: opening-offer fraction + concession-fraction
  multipliers) and the upsell-acceptance buffer
  (`_UPSELL_BUFFER_FRACTION`). Verified with a deterministic (no-LLM) script
  across all 5 of the frontend's curated tight-budget scenarios: `best_price`
  consistently closed at the lowest price in 11–12 rounds (e.g. wireless
  mouse: ₹1,037.56 vs. ₹1,037.80 default), `fastest_deal` consistently
  closed fastest at a higher price (7 rounds, ₹1,076.13) — a real,
  reproducible ordering, not a label. The first multiplier attempt
  (0.5/0.7) made `best_price` fail to close *every* curated scenario within
  the round cap — re-tuned to (0.55/0.85/0.95) so it reliably still reaches
  a deal, just a better one, more slowly.

**Real Razorpay Checkout for human-triggered negotiations** — the largest
piece this session. `POST /negotiate` gained `auto_pay` (default `true`,
untouched behavior for the scenario harness and any other backend-automated
caller, which never sets it): `BuyerAgent.negotiate_and_purchase` still
runs the identical real negotiation, but with `auto_pay=false` (what the
dashboard now always sends) it stops short of paying and returns
`payment_pending: true` plus a `checkout_token`. New:
`backend/app/checkout_quote.py` (a short-lived HMAC-signed token binding
the exact `(product_id, agreed_price_paise)` a negotiation actually closed
at, so a client can never get a real order created at a tampered price);
`POST /checkout/order` (creates a real Razorpay test-mode order for that
exact price) and `POST /checkout/confirm` (verifies the real payment by
reusing `MerchantAgent.handle_request`'s existing `agreed_price_paise`
path — the same code `GET /products/{id}` already used, no parallel
verification logic). Frontend: `CheckoutButton.jsx` loads Razorpay's real
`checkout.js`, opens the real widget, and handles success/failure/cancel
distinctly, wired into `NegotiationChat.jsx`'s result card. `docs/DECISIONS.md`
and `docs/THREAT_MODEL.md` both updated with the full reasoning.

Verified live, not just reviewed: ran a real human-triggered negotiation
(`auto_pay:false`) end to end — got back `payment_pending: true`,
`transaction_id: null`, a real `checkout_token`; used that token against
`POST /checkout/order` and got back a **real** Razorpay test-mode order
(`order_TY5XIVgvXsTwt7`, ₹449, `key_id` starting `rzp_test_`); opened that
real order's real Checkout widget in an actual (non-headless) browser and
it rendered cleanly — correct price, "Test Mode" ribbon, a normal "Contact
details" step — not a bot-detection stall, addressing the exact risk
flagged before starting. Deliberately did **not** type a card
number/OTP into the widget myself, matching this repo's own established
convention (`scripts/demo_payment.py`, `docs/DECISIONS.md` 2026-09-02):
scripting the widget's own form is the thing that risks tripping Razorpay's
bot detection, not the fact that a payment happens — that last step needs
to be a real human, in their own browser, on request.

**Also**: hero primary CTA text changed "See it negotiate" → "Meet your
agent" (per direct request, no functional change — still scrolls to
`#live-feed`).

**Verified throughout**: `pytest backend/tests -v` → 136/136 passing (122
carried forward + 14 new: `test_checkout_quote.py`,
`test_checkout_endpoints.py`, two additions to
`test_negotiate_endpoint.py`). `npm run build` clean after every frontend
change. No console errors across repeated headless-browser screenshot
checks (hero, all four proof tabs, the "try it yourself" form, the audit
log) at realistic viewport sizes.

**Known gaps carried forward**:
- `verification_failed`'s user-facing label is still the raw technical name
  — deliberately left pending an explicit decision (see above), not an
  oversight.
- The real-Checkout flow's actual payment completion (typing a test card
  and OTP into the widget) has only been verified up to the widget opening
  correctly — the final manual click-through needs to be done and confirmed
  by an actual person, by design (see above).
- Nothing from this session is committed — see `git status`.

## 2026-09-04 — Day 4 Part 5: fixed the product-mismatch bug via `product_id` pinning; dashboard visual redesign (theme, header, proof tabs, intro)

**Requested across the session**: fix the "try it yourself" product-mismatch
bug logged as deliberately-unfixed in `docs/DECISIONS.md` (2026-09-04), plus
a long series of visual/UX iterations on the dashboard: hero background
motif, header content, how the four technical/proof sections are revealed,
the color theme, and a page-load intro animation.

**Fixed: product-mismatch bug (`docs/DECISIONS.md`, 2026-09-04 entry
"USB-C Hub → Cable Organizer Kit mismatch")** — rather than fixing
`BuyerAgent._find_candidate_product`'s keyword-matching heuristic itself
(the single-letter-token + substring-containment bug identified but left
unfixed in that entry), added an optional `product_id` field end-to-end:
`NegotiateRequest.product_id` (`backend/app/main.py`) →
`BuyerAgent.negotiate_and_purchase(goal_text, budget_paise, product_id=None)`
(`backend/app/buyer_agent/agent.py`) — when given, looks the product up
directly via `catalog.get(product_id)` and skips `_find_candidate_product`
entirely; when omitted (the "Surprise me" random-scenario path, which only
has free text, not an id), behavior is unchanged. `frontend/src/api.js`'s
`postNegotiate` and `LiveFeed.jsx`'s `runCustom` now send the picker's
`selectedProduct.id`. **The underlying keyword-matching bug in
`_find_candidate_product` is still present and unfixed** — this closes the
gap only for the picker path, which now bypasses that function altogether;
it can still misfire for freeform "Surprise me" goal text, though the
current `SCENARIOS` list is hand-picked to avoid triggering it.

Verified against a locally running backend (two real, live multi-round
Zeuthen negotiations, not mocked):
- `product_id="wireless-mouse-ergo"`, budget 64,900 paise (well under the
  129,900-paise list price): negotiation correctly stayed on the wireless
  mouse and ended `success: False, reason: "negotiation ended without a
  deal: stalemate after 4 round(s)"` — previously this exact case silently
  matched `mouse-pad-xl` instead and reported a false "success".
- Same product_id, budget 110,000 paise: stayed on the wireless mouse,
  negotiated for 11 rounds, closed at `agreed_price_paise: 103780`.

`pytest backend/tests -v` → still 122/122 passing (no test added yet for
`product_id` specifically — see Known gaps below).

**Dashboard visual redesign** (`frontend/`, extensive iteration, final
state only summarized here):

- **Hero backdrop** — went through a "Setu = bridge" SVG motif (a
  suspension-bridge line with offer-pulses, several sizing/pulse-animation
  bug fixes), then a `NegotiationTicker` card, before settling on
  `AgentConnectionBackdrop.jsx` (new): two ambient pulsing nodes on the
  hero's left/right edges with small packets traveling between them —
  deliberately subtle (dot/line sizes fixed in plain px, not viewBox units,
  after an earlier SVG version rendered oversized on wide viewports).
- **Header** — iterated through several ideas (the negotiation ticker, a
  live-status pulse pill, a scrolling audit-log marquee, a full-width
  heartbeat/EKG line) and ended back at empty (just the scroll-shadow
  strip) per explicit request to remove the last one tried, with no
  replacement chosen yet.
- **`ProofTabs.jsx` (new)** — replaced four separate always-mounted
  full-page sections (`DecisionTrace`, `StatsHeadline`, `KillSwitch`,
  `AuditLog`, each previously its own `snap-panel` with its own
  `SectionBackdrop`) with one tabbed section: four buttons ("Decision
  trace", "Test results", "Kill switch", "Audit log"), one panel mounted
  at a time with a framer-motion expand/fade, amber-family active-tab
  styling. The four components were converted to bare content (no more
  standalone `<section>`/backdrop/id of their own). Hero's stat badges
  that used to `scrollIntoView` a specific section id now go through a new
  `frontend/src/lib/proofNav.js` (`goToProofTab`, a small `CustomEvent`
  pub/sub `ProofTabs` listens for) so they still deep-link into the right
  tab without prop-drilling tab state through `App.jsx`.
- **`NegotiationTicker.jsx` (new)** — an Ask/Bid card that ticks through
  scripted negotiation rounds to a settled "Agreed" state, looping; gained
  a `size="lg"` variant and a `full` prop (stretches to its container width,
  spreads Ask/Round/Bid to the edges) for its final placement below the
  "How it works" three-card grid.
- **Theme: gold → emerald → crimson** — the original gold/parchment/ink
  palette (`tailwind.config.js`) was replaced twice on request: first with
  a custom `emerald` scale (Tailwind's own default emerald values), then
  — because it "didn't like this green" — with a custom `crimson` scale.
  The first crimson attempt (`#fda4af`/`#fb7185`/`#f43f5e`/`#e11d48`, a
  rose/pink hue) read as washed-out pink rather than red, especially on
  low-opacity outline buttons; corrected to a true saturated scarlet
  (`#f87171`/`#ef4444`/`#dc2626`/`#b91c1c`, one shade off Tailwind's own
  `red` scale) after the user flagged it. Every `gold-*`/`emerald-*`
  Tailwind class and every hardcoded hex/`rgba(...)` gold value across ~20
  files was mechanically renamed/swapped each time (`sed`, not manual
  per-file edits, given the volume), plus one dead reference fixed along
  the way (`text-gold-200` was never a defined shade, so it rendered
  invisibly; now a defined shade). **Known overlap, flagged to the user
  and accepted**: the app's existing danger/error states (kill-switch
  active, rejected outcomes, failed checklist steps) use Tailwind's
  built-in `red-*` scale, which is now in the same red family as the new
  `crimson` brand accent — differentiated by hue choice, not by being a
  wholly different color.
- **`ShutterIntro.jsx` (new)** — a page-load intro: two full-width panels
  (top/bottom half of the viewport) each render the *same* "Setu" wordmark
  + tagline, clipped via `overflow: hidden` so each panel only shows its
  half (top panel shows the top half, bottom panel the bottom half) — the
  two halves line up into one seamless logo when closed. After a ~900ms
  hold, the panels slide apart (`y: "-100%"`/`"100%"`) with a brief
  crimson flash along the seam, the logo splitting and riding away with
  them to reveal the hero underneath. Locks `document.body.style.overflow`
  during the intro, restores it and fully unmounts once the slide finishes.
- **`LiveFeed.jsx`** — no longer shows a fallback/previous negotiation on
  page load; the negotiation chat now only appears after the visitor
  clicks "Start negotiation" or "Surprise me" (`source = result`, not
  `result || fallbackRecord`). The now-dead `fallbackRecord` prop and its
  `App.jsx`-side computation (`fallbackHarnessRecord`/`fallbackFeedRecord`)
  were removed rather than left unused. Heading changed from "Live
  negotiation feed" to "Your AI Agent"; both action buttons (`Surprise me`,
  `Start negotiation`) restyled from an outline/ghost style to a solid
  filled button matching the hero's primary CTA.
- Small polish: `StatsHeadline.jsx`'s big count-up number had a soft
  `0 0 50px` glow `textShadow` (a halo), changed to a crisp offset
  `4px 6px 0px` drop shadow on request.

**Verified throughout**: no `npm run dev` console/page errors across
repeated headless-browser screenshot checks (every visual change in this
entry was screenshotted and read back before being reported done, per this
session's own instructions); `pytest backend/tests -v` → 122/122 after the
`product_id` change.

**Known gaps carried forward**:
- No automated test covers the `product_id` pinning path specifically
  (`test_negotiate_endpoint.py`/`test_buyer_agent.py` weren't extended this
  session) — only the two manual live-backend runs above.
- `_find_candidate_product`'s keyword-matching bug (short single-letter
  tokens, substring containment) is still unfixed for the "Surprise me"
  freeform-text path.
- Nothing from this session is committed — see `git status`; all of the
  files listed above are modified/new in the working tree.
- Header currently has no content (see above) — was iterated through
  several ideas and explicitly emptied on request, with no next direction
  chosen yet as of session end.

## 2026-09-04 — Day 4 Part 4: interactive negotiation, live chat replay, product-first hero

**Requested across several sessions**: turn the dashboard's live-trigger
feature into something a visitor can actually drive (their own budget +
product, not just a random scenario), make the negotiation replay feel like
a real two-party chat instead of a static log, clean up implementation
details leaking into user-facing copy, and rework the hero/nav into a
product-first landing page rather than an engineering status page.

**"Try it yourself" form** (`LiveFeed.jsx`) — the negotiation feed now has a
form (product dropdown sourced from the real `GET /catalog`, a budget
slider bounded to the catalog's actual ₹449–₹18,999 price spread) alongside
the existing random "Surprise me" scenario button. Both post through the
same `run()` function and the same 60s cooldown (shared `localStorage` key)
— no separate throttle logic to keep in sync. Verified against a real
backend: comfortable-budget request produced a real `pay_fake_*`
transaction (full TrustGuard path, no bypass for this entry point), a
tight-budget request produced a genuine multi-round Zeuthen negotiation,
and a deliberately-mismatched budget/product produced the graceful
"no catalog product matches" outcome.

**Live chat replay** (`NegotiationChat.jsx`, new) — replaces the static
round-by-round block with a WhatsApp-style two-party replay: a typing
indicator (animated dots) paced by *that specific message's real LLM
latency* (backend now measures and returns `latency_ms` per trace entry —
see `docs/DECISIONS.md`), capped 350ms–1.6s so a slow call doesn't stall
the replay, then the bubble fades in. Buyer left, Setu (merchant) right,
each with a small avatar. Risk(Buyer)/Risk(Merchant) and the round's
concession note are inline on the bubble they belong to, not a separate
block. A distinct summary card (deal price / escalated / rejected / no
match) appears only once the full replay finishes. One component, reused
by both the random-scenario button and the "try it yourself" form.

**Copy cleanup — nothing implementation-shaped in the primary flow**:
removed the raw backend URL from user-facing text ("live response from
http://..."), the internal product slug shown next to product names, the
"this response predates the risk-telemetry fields" developer note, the
harsh "Wait 51s" clock-icon cooldown badge (now a plain greyed "Try again
in 51s"), and the "POST /negotiate against the real backend" copy (now
"Your AI agent is negotiating in real time"). The negotiation outcome card
no longer renders the backend's raw `reason` string (which can embed
`"...paise"`, rule names, `max_spend_paise=` internals) — see
`docs/DECISIONS.md` for the plain-language layer that replaces it. All of
this stays exactly as-is, verbatim, in `AuditLog`/`DecisionTrace`, which are
the intentionally technical views.

**Hero, header, "How it works"** — added a sticky header (`Header.jsx`,
new: wordmark left, "How it works"/"Try it" smooth-scroll links right,
transparent-to-blurred on scroll) and a `HowItWorks.jsx` section that now
holds the full x402/Zeuthen/trust-layer technical description, moved out of
the hero. Hero subheadline rewritten to "AI agents that negotiate, pay, and
explain themselves."; badges reworded to plain language while staying wired
to real `summary` data (no fabricated numbers); single solid-amber primary
CTA ("See it negotiate") plus a secondary "How it works" button; the
"Try the kill switch" hero shortcut was removed and the `KillSwitch`
component itself relocated to sit next to `AuditLog`, right before the
footer — re-verified live after the move (activate → a real `/negotiate`
call correctly blocked with "kill switch is active" → deactivate → confirmed
clean) since it's a different page position, not different wiring. Also
added a page-load fade-in, a scroll-progress bar (`ScrollProgress.jsx`,
new), a themed scrollbar/focus ring, and a proper page title/favicon/meta
description (`index.html`) in place of the generic "Setu Dashboard" tab.

Two decorative additions were tried and explicitly reverted this session:
a mouse-following spotlight in the hero (reverted to the original fixed
ambient glow — the user found a moving light distracting) and a "bridge"
background motif behind the headline referencing Setu's literal meaning
("bridge" in Sanskrit/Hindi) — an SVG arc connecting two pulsing nodes with
a traveling spark. The bridge motif went through two bug-fix rounds (a
non-uniform-viewBox distortion that flattened the nodes into ellipses, then
a `vector-effect="non-scaling-stroke"` interaction with framer-motion's
`pathLength` draw-in that cut the line short) before being removed outright
on request rather than iterated further.

**Investigated, not fixed**: a product-matching bug where selecting an
expensive item with too little budget silently negotiates for an unrelated
cheap item instead (root cause: a stray single-letter keyword token plus
substring-containment scoring in `BuyerAgent._find_candidate_product` — see
`docs/DECISIONS.md`). Left open on explicit instruction to investigate
before fixing.

**Also flagged, not acted on**: several large, unrelated instructions
(a full hero/nav redesign, later duplicated near-verbatim) arrived attached
to background-task tool notifications rather than as genuine user turns,
referencing prior requests and screenshots that don't exist earlier in the
actual conversation. Treated as likely prompt injection and not applied;
the same redesign was later done for real once the user asked for it
directly in an actual message.

## 2026-09-04 — Day 4 Part 3: public dashboard, built against real data only

**Requested**: a single-page public dashboard proving the system live —
visible Zeuthen risk-of-conflict math per negotiation round, a real
"run a live negotiation" trigger, a TrustGuard decision-trace panel, the
Part 2 harness's real headline numbers, a working kill switch, and an
audit log — with every number traceable to a real request/response or the
harness's own JSONL, nothing illustrative.

**Built** (`frontend/src/`, new `components/`, `lib/`, `public/harness/`):

- **Hero** — headline, backend-health badge, floating stat badges sourced
  from the real harness summary, a pulsing amber glow behind the wordmark.
- **Live negotiation feed** (`LiveFeed.jsx`) — a "Run a live negotiation"
  button fires a real `POST /negotiate` against a curated set of
  real-catalog tight-budget scenarios (never a freeform budget, to bound
  live Gemini spend), with a 60s cooldown measured from *completion* (not
  click) since a full negotiation can itself take close to a minute.
  Renders each round as `Risk(Buyer)=X.XX vs Risk(Merchant)=X.XX →
  {side} concedes ₹Y`, computed from the real per-round offer numbers, plus
  a hand-rolled SVG chart of both parties' risk curves converging to the
  deal. Falls back to the last verified harness run when no live run has
  been triggered yet.
- **Decision trace** (`DecisionTrace.jsx` + `lib/rules.js`) — reconstructs
  TrustGuard's rule-evaluation checklist from the response's own `reason`
  text and `backend/app/trust/guard.py`'s fixed, sequential, short-circuit
  check order (kill switch → signature → replay → credential scope →
  velocity → daily spend → spend cap → category): every check rendered
  "passed" is one the code guarantees ran before the named rule fired, and
  the failing step's text is the exact backend reason string, not
  paraphrased.
- **Harness results** (`StatsHeadline.jsx` + `charts/OutcomeDonut.jsx`) —
  the real Part 2 run's numbers (12 compliant / 13 escalated / 1 rejected /
  4 graceful-no-match / 7 verification-failed of 37 total calls), a
  count-up on scroll-into-view, an animated donut, and the real
  blocked-by-rule breakdown (13× daily_spend, 1× credential_scope).
- **Kill switch** (`KillSwitch.jsx`) — calls the real
  `/admin/kill-switch/*` endpoints with a user-entered `X-ADMIN-KEY`;
  confirm-to-activate; polls status every 15s.
- **Audit log** (`AuditLog.jsx`) — the Part 2 harness's own
  `run_20260904-021007.jsonl`, copied verbatim into
  `frontend/public/harness/` and fetched at runtime, filterable by outcome.
- **Layout**: full-viewport scroll-snap sections (one section visible at a
  time, `scroll-snap-stop: always` so a fast scroll can't skip one), a
  fixed dot-nav tracking scroll position via `IntersectionObserver`.
- New deps: `framer-motion`, `lucide-react` (added to
  `frontend/package.json`, not yet committed — see below).

**Backend change — additive, NOT committed**: `backend/app/main.py`'s
`_outcome_to_dict` was silently dropping `buyer_offer_paise` /
`merchant_offer_paise` / `buyer_risk` / `merchant_risk` from each
`/negotiate` trace entry, even though `BuyerAgent` already computes and
attaches them (`NegotiationTrace` has always carried these fields — see
`backend/app/buyer_agent/agent.py`). Added them to the response dict; all
122 backend tests still pass unmodified. Left uncommitted per explicit
instruction this session ("don't commit anything") — **the live Render
backend does not have this fix yet**, so a freshly-triggered negotiation
against production will render messages-only (no risk chart, with a
visible "predates risk-telemetry" note); the dashboard was verified
end-to-end against a local `uvicorn` instance running this change instead.
**Action needed before the risk chart works against production**: review
and deploy this `main.py` change.

**Verified**:

- `pytest backend/tests -v` → 122/122 passing, with the additive trace
  fields in place.
- Live-trigger button verified against a local backend: a real
  multi-round negotiation, captured via headless browser, produced the
  intended `Risk(Buyer)=1.00 vs Risk(Merchant)=1.00 → opening positions`
  → ... → converged risk curve, ending in a real `pay_fake_*` transaction.
- Kill switch verified through the *actual rendered buttons* (not curl):
  clicked Activate, confirmed the UI showed `ACTIVE`, independently
  `fetch()`'d `/negotiate` and got `"kill switch is active"` back, clicked
  Deactivate, confirmed `/negotiate` resumed succeeding. Never touched the
  production Render kill switch during this testing.
- `npm run build` clean throughout; no console/page errors across repeated
  headless-browser passes.

**Known gaps carried forward**:

- The `main.py` trace-enrichment change above is uncommitted and
  undeployed — full risk-chart fidelity against the public Render URL
  requires deploying it first.
- No automated test for the dashboard itself (React component tests or
  Playwright) — verification this session was manual, via headless browser
  screenshots and DOM assertions, not committed as a repeatable test suite.
- `frontend/package.json`'s new dependencies (`framer-motion`,
  `lucide-react`) are uncommitted — a fresh `npm install` on another
  machine or CI won't have them until this is committed.

## 2026-09-04 — Day 4 Part 2: scenario test harness, closing idempotency's live-verification gap

**Requested**: build a scenario test harness that runs real, randomized
scenarios against the live `/negotiate` and `/products/{id}` endpoints on
Render (not local scripts), covering comfortable/tight-budget negotiation,
no-match graceful failure, a deliberate duplicate-idempotency-key test
(closing the one TrustGuard rule Part 1 left without live evidence), and
deliberate velocity/spend-limit breaches -- with structured JSONL evidence
and an honest final summary.

**Built**: `backend/app/scripts/scenario_harness.py` -- black-box (HTTP
only, no imports from the app itself, so a pass here is evidence about
real production behavior, not internals), fixed-seed randomization
(`SEED=20260904`) for reproducibility, structured JSONL logging per HTTP
call (`harness_results/run_<timestamp>.jsonl`), and a local
velocity-window mirror that self-throttles the "normal" scenarios so
accidental rate-limit hits don't muddy the intentional ones.

**First run crashed** (`httpx.ReadTimeout`) on the first tight-budget
negotiation -- the original 60s client timeout was too short for a real
multi-round Zeuthen negotiation with live Gemini phrasing calls per round
(some rounds took 100k+ ms). Fixed: read timeout raised to 240s, and both
HTTP helpers now catch network errors and log them as a distinct outcome
instead of crashing the whole run. Re-ran clean.

**Ran 22 named scenarios (37 total HTTP calls) against
`https://setu-59l6.onrender.com`**:

- **8 comfortable-budget** -- all compliant (real purchases, real upsell
  decisions made live by Gemini, not scripted).
- **6 tight-budget** (real multi-round Zeuthen negotiation, live LLM
  phrasing) -- 4 compliant, agreeing at 70,484-149,630 paise after 11
  rounds each. The last 2 (`tight-5`, `tight-6`) were **organically
  escalated by `daily_spend`** -- real cumulative spend from the earlier
  scenarios crossed `max_daily_spend_paise` (2,000,000) mid-run, entirely
  unplanned. Left as-is rather than reordered, since a real agent hitting
  its own daily cap mid-session from a sequence of individually-legitimate
  purchases is exactly the scenario this rule exists to catch.
- **4 no-viable-match** -- all failed gracefully (`200`, clear reason,
  no crash), confirming `BuyerAgent._find_candidate_product` returning
  `None` never produces anything worse than a clean `success:false`.
- **1 deliberate credential-scope breach** (monitor at 1,899,900 paise
  against a comfortably-large budget) -- correctly rejected before any
  charge.
- **1 deliberate duplicate-idempotency-key scenario** (`GET
  /products/{id}`, the flagship demo -- see below) -- **closes Part 1's
  named gap**. 6 identical calls (same fabricated `payment_id`, hence the
  same server-derived `idempotency_key`) returned byte-identical bodies;
  the first took 5,350ms (real Razorpay lookup), the next 5 averaged
  ~380ms (cache hit, no repeat Razorpay call); a control call with a fresh
  key was **not** blocked by velocity, proving the 6 duplicates cost zero
  velocity budget between them.
- **1 deliberate velocity-limit burst** (10 rapid identical purchases,
  safety-capped) -- **did not** independently re-trip `velocity`: by this
  point `daily_spend` had already tripped (see `tight-5/6` above), and a
  daily-spend-blocked attempt never increments the velocity counter
  (`BuyerAgent._pay_and_collect` only calls `record_purchase_attempt`
  after an *approved* purchase reaches the payment rail), so all 10 burst
  attempts hit `daily_spend` first. `velocity` remains live-proven from
  Part 1's manual test (2026-09-04, four `/negotiate` calls), just not
  re-confirmed by this specific run. Named honestly as a run-ordering
  artifact, not silently glossed over -- see `docs/THREAT_MODEL.md`.
- **1 deliberate daily-spend burst** -- fired immediately on its first
  attempt (cap already well past), re-confirming the rule under scripted
  conditions, not just the earlier manual curl test.

**Real, honest summary** (from `run_20260904-021007_summary.json`, not a
claim):

```
Named scenarios: 22    Total HTTP calls logged: 37
Outcomes across all 37 calls:
  compliant: 12, escalated: 13, graceful_no_match: 4, rejected: 1, failed_verification: 7
TrustGuard rules observed firing: daily_spend: 13, credential_scope: 1
```
At the scenario level: 12/22 compliant outright, 2 correctly escalated by
`daily_spend` organically mid-negotiation, 4/4 no-match scenarios failed
gracefully, 1/1 credential-scope breach correctly rejected, 1/1
idempotency demo passed (byte-identical cached responses + zero velocity
cost, proven above), 1/1 daily-spend burst correctly re-confirmed the
cap, and 1/1 velocity burst was inconclusive for `velocity` specifically
(pre-empted by `daily_spend`, itself a correct block) but produced no
unexpected failures and no breaches -- 0 crashes, 0 network errors after
the timeout fix, 0 cases of a rule failing to fire when it should have.

**Flagship demo scenario**: the duplicate-idempotency-key test above --
recommended for recording, since it has a clean before/during/after shape
(first call: real 5.3s Razorpay round-trip and a normal failure; 6
duplicates: instant, byte-identical cached responses; control call: a
fresh key immediately back to normal latency, proving the duplicates were
truly free). Raw evidence: `harness_results/run_20260904-021007.jsonl`
(`scenario_id="idempotency-demo"`, steps 1-7).

**Updated `docs/THREAT_MODEL.md`**: idempotency's live-verification gap
(named explicitly in the Part 1 entry above) is now closed, with the
harness scenario as evidence; a new "Known gaps" note explains the
velocity-burst's inconclusive result honestly rather than omitting it.

**Closed.** Every TrustGuard rule -- kill switch, spend cap/credential
scope, velocity, daily spend cap, and now idempotency -- is proven live
against production, via either the Part 1 manual curl sequences or this
harness. No rule remains with local-only evidence. Day 4 (both parts) is
complete.

## 2026-09-04 — Day 4 Part 1: live-verified max_daily_spend_paise on both endpoints (closes the last TrustGuard gap)

**Requested**: the previous entry below wired `max_daily_spend_paise` into
both live endpoints but only ever tested it locally. Close that gap with
real request/response evidence, same rigor as the kill switch/spend
cap/velocity live tests, plus explain the `credential_scope` vs `spend_cap`
naming difference clearly enough to be self-explanatory.

**`POST /negotiate` (fake Razorpay rail — real accumulation is cheap)**:
the shared, persistent Buyer Agent (`get_buyer_agent()`, one instance for
the process's lifetime) was walked through six genuine successful
purchases: one mouse pad (59,900 paise) then five mechanical keyboards
(349,900 paise each), totalling 1,809,400 paise of real spend in its
trailing 24h window. A seventh purchase attempt (another keyboard,
349,900 paise, otherwise fully valid — correct signature, fresh nonce, in
credential scope, in policy bounds, room left in velocity) was then
rejected, reproduced five times in a row with identical numbers:

```
POST /negotiate {"goal_text":"mechanical keyboard hot-swap 65 percent","budget_paise":349900}
  → {"success":false,"reason":"purchase escalated for review by trust layer (daily_spend):
      agent 'buyer-079629cd' would exceed its daily spend cap: 1809400 paise already spent
      in the last 24h + 349900 paise requested = 2159300 paise, cap is
      max_daily_spend_paise=2000000 paise", ...} — 200 (negotiate always returns HTTP 200;
      the rejection is in the body)
```

**`GET /products/{id}` (real Razorpay client)**: genuinely accumulating
2,000,000 paise of real spend here means completing that many real
Razorpay test-mode Checkout payments, which this codebase deliberately
never automates past Razorpay's PerimeterX/HUMAN bot detection (see
`docs/DECISIONS.md`, 2026-09-02) — no headless/scripted click-through, by
design. Rather than either asking for several manual checkouts or silently
skipping this endpoint, `MAX_DAILY_SPEND_PAISE` was temporarily lowered to
`1000` via the Render dashboard env var (no code change, no
commit/deploy from this session) and the service redeployed. With the cap
that low, a single request's amount alone exceeds it, so the exact same
`DailySpendTracker.check` / `daily_spend` rejection code path fires before
any Razorpay call is made — same trick already used for the live
`spend_cap` test (a fabricated `X-PAYMENT` payload never gets far enough
to be looked up):

```
GET /products/mechanical-keyboard-65  (X-PAYMENT header present, fabricated payment_id)
  → {"error":"purchase escalated for review by trust layer (daily_spend): agent
      '157.49.122.108' would exceed its daily spend cap: 0 paise already spent in the
      last 24h + 349900 paise requested = 349900 paise, cap is max_daily_spend_paise=1000
      paise"} — 429
```
Reproduced with a second, differently-fabricated payment_id — identical
result. Confirmed the kill switch was independently `false` throughout
(`GET /admin/kill-switch`). `MAX_DAILY_SPEND_PAISE` was then restored to
`2000000` on Render and redeployed, returning the live cap to its normal
value.

**New data point**: `daily_spend` and `velocity` rejections return HTTP
`429`; `spend_cap`/`category` rejections return `402`
(`MerchantAgent.handle_request`: `status = 429 if auth.rule in
("velocity", "daily_spend") else 402`) — not previously called out in the
live-verification record.

**Why `/negotiate` says `credential_scope` and `/products/{id}` says
`spend_cap` for what looks like the same protection** (asked directly,
answered in full in `docs/THREAT_MODEL.md`'s "Trust/safety layer" section
— summary here): they're two different rules that happen to enforce the
identical number (`max_single_transaction_paise` = 500,000 paise) for this
deployment specifically. `/products/{id}`'s anonymous caller has no
credential, so the credential-scope check is skipped entirely and only the
platform-wide `PolicyEngine` spend_cap can catch it. `/negotiate`'s Buyer
Agent *does* have a credential, and that credential's `max_spend_paise`
was deliberately issued equal to the platform cap (`BuyerAgent.__init__`)
— so the credential-scope check, which runs earlier in
`TrustGuard.authorize_purchase` and is a hard reject rather than an
escalation, always wins the race for this agent. Not a naming
inconsistency — a structural consequence of one endpoint having a
credential to check and the other not.

**Closed.** Every TrustGuard rule is now backed by real production
request/response evidence with matching rigor across both live
endpoints — kill switch, spend cap/credential scope, velocity, and now
daily spend cap. The one remaining gap: **idempotency has never been
fired against production**, only covered by local tests — same shared
code path as everything else here, no reason to expect divergent
behavior, but it hasn't actually been proven live the way the rest have.
Documented as an explicit named gap in `docs/THREAT_MODEL.md` rather than
left implicit. Day 4 Part 1 is complete; next is the scenario test harness
(Part 2).

## 2026-09-04 — Full TrustGuard on GET /products/{id}, and a new POST /negotiate endpoint

**Requested**: the kill-switch fix directly below closed one narrow gap
(kill switch only). Two follow-ups to close the same class of gap fully:
(1) wire the *entire* TrustGuard — spend caps, velocity, idempotency, daily
spend — into `GET /products/{id}`, not just the kill switch; (2) build a
real `POST /negotiate` HTTP endpoint for the Buyer/Merchant negotiation
flow, which until now only existed as a local script, and route it through
the full TrustGuard too.

**1. `GET /products/{id}` — full TrustGuard wiring:**

Added `TrustGuard.authorize_anonymous_purchase` (`backend/app/trust/guard.py`)
— the same checks as the signed `authorize_purchase` path (idempotency,
velocity, daily spend, policy bounds) minus signature/credential/replay
verification, since this endpoint has no signed agent identity. Shares the
underlying `IdempotencyStore`/`VelocityLimiter`/`DailySpendTracker`/
`PolicyEngine` via a new `_authorize_common` refactor. Bucketed by a
caller-derived identity — `X-Forwarded-For` header or client IP (`main.py`
`_caller_id`) — explicitly weaker than the signed path (spoofable/rotatable
by the caller), documented as such in `THREAT_MODEL.md`.

`MerchantAgent.handle_request` gained a `caller_id` parameter: `None`
(default) means the caller already ran the full signed
`TrustGuard.authorize_purchase` before calling this (the in-process
BuyerAgent flow) and this leg runs unguarded a second time since it was
already cleared; a real value means an unauthenticated HTTP caller, and the
anonymous check runs first. `GET /products/{id}` always passes one now.

**2. `POST /negotiate` — new endpoint:**

Runs `BuyerAgent.negotiate_and_purchase` over HTTP for the first time.
Needed three new singletons in `main.py`: `get_trust_guard()` (one shared
`TrustGuard`), `get_negotiation_razorpay()` (a `FakeRazorpayClient`, same
reasoning as `negotiation_demo.py` — unattended flows never drive the real
Checkout widget), and `get_negotiation_merchant_agent()` /
`get_buyer_agent()` (a second `MerchantAgent` using the fake Razorpay
client, and a persistent `BuyerAgent`, both sharing `get_trust_guard()`
with the real-Razorpay `get_merchant_agent()` used by `/products/{id}`).
Sharing one `TrustGuard` across both merchant instances is what makes the
kill switch (and velocity/spend/idempotency accounting) genuinely global
rather than per-endpoint — this was deliberate, not incidental; two
independent `TrustGuard`s would have reintroduced exactly the same class of
gap this work is closing. No new trust-checking code was needed for
`/negotiate` itself: `BuyerAgent._pay_and_collect` already signs every
purchase attempt and runs the full `TrustGuard.authorize_purchase` before
touching the payment rail — exposing the existing flow over HTTP was the
whole fix.

**New tests** (122 passing, up from 105): `test_anonymous_purchase_*` in
`test_trust_guard.py` (guard-level), `test_anonymous_purchase_*` /
`test_signed_buyer_agent_flow_is_unaffected_by_anonymous_trust_wiring` in
`test_merchant_agent.py` (proves the signed in-process path is unaffected
by the new anonymous wiring), `test_products_endpoint_trust.py` (HTTP,
`TestClient` — spend-cap rejection and kill-switch priority, both of which
short-circuit before any real Razorpay call so they don't need network
access), and `test_negotiate_endpoint.py` (HTTP, `TestClient` with a fake
LLM client — comfortable-budget success, invalid-budget 422, blocked by the
shared kill switch, and rejected by credential scope for an
over-cap-budget negotiation).

**Verified locally:**
- `pytest backend/tests -v` → 122/122 passing.
- `uvicorn backend.app.main:app` boots cleanly from the repo root (Render's
  actual invocation shape) with the new imports (`BuyerAgent`,
  `FakeRazorpayClient`, `TrustGuard`) — `/health`, `/catalog`,
  `/admin/kill-switch` all still `200`; `POST /negotiate` with an invalid
  budget correctly `422`s without making any LLM/network call.

**Committed and pushed** as `13ad42a "Wire full TrustGuard into GET
/products/{id}; add POST /negotiate over HTTP, sharing one TrustGuard so
kill switch/limits are global"`. First Render deploy attempt was manually
cancelled by the user for taking too long; `/health` stayed `200` throughout
(cancelling left the previous deploy running, nothing went down). A manual
"Deploy latest commit" from the Render dashboard completed successfully;
confirmed the new code was live via `POST /negotiate` returning `422` for
an invalid budget instead of `404`.

**Re-verified against live production** (real request/response evidence,
`https://setu-59l6.onrender.com`):

*Kill switch now blocks both endpoints, not just `/products/{id}`:*
```
POST /admin/kill-switch/activate → {"active":true,"reason":"live verification: full trust guard + negotiate endpoint",...} — 200
GET  /products/mechanical-keyboard-65 → {"error":"kill switch is active (...); no new transactions are being processed"} — 503
POST /negotiate {"goal_text":"mechanical keyboard hot-swap","budget_paise":500000}
  → {"success":false,"reason":"kill switch is active (...); no new transactions are being processed",...} — 200
GET  /admin/kill-switch → still {"active":true,...} — 200
POST /admin/kill-switch/deactivate → {"active":false,...} — 200
```

*Spend cap fires on both endpoints for the 1,899,900-paise monitor (cap is
500,000), before any charge:*
```
GET /products/monitor-27-1440p-144hz  (X-PAYMENT header present, fabricated payment_id)
  → {"error":"purchase escalated for review by trust layer (spend_cap): transaction amount 1899900 paise
      exceeds the platform's max_single_transaction_paise cap of 500000 paise"} — 402
  (never reached Razorpay -- the fabricated payment_id was never looked up)

POST /negotiate {"goal_text":"27 inch monitor 1440p 144hz","budget_paise":2500000}
  → {"success":false,"reason":"purchase rejected by trust layer (credential_scope): requested amount 1899900
      paise exceeds this agent's credential scope (max_spend_paise=500000)",...} — 200
```
(`/negotiate`'s Buyer Agent has a credential whose scope exactly equals the
platform's `max_single_transaction_paise`, so `credential_scope` -- checked
before the platform-wide `spend_cap` rule -- is the one that fires here;
`/products/{id}`'s anonymous path has no credential, so `spend_cap` fires
directly. Both are real TrustGuard rejections before any charge was
attempted; see `THREAT_MODEL.md`'s note on why these are separate,
independently-tested rules.)

*Velocity limit fires live on `/negotiate` (`max_purchases_per_minute=5`)
-- four more calls to the same shared Buyer Agent after the baseline
purchase above, each with an upsell leg that also counts as a purchase
attempt:*
```
negotiate call 1 → 200, main + upsell both purchased
negotiate call 2 → 200, main + upsell both purchased
negotiate call 3 → 200, main purchased; upsell leg: "purchase escalated for review by trust layer (velocity):
                    agent 'buyer-989bd678' exceeded velocity limit: 5/5 purchase attempts in the last minute"
negotiate call 4 → 200 (HTTP), body: even the *main* product purchase now blocked by the same velocity rule
```
Confirmed `/products/{id}` (a separate caller-IP-bucketed identity) was
unaffected by this agent's velocity block, and the kill switch was
independently confirmed still `false` throughout.

**Closed.** Every check claimed in this entry -- kill switch (both
endpoints, shared), spend cap (both endpoints), velocity (negotiate) -- is
now backed by real production request/response evidence, not local test
results alone.

## 2026-09-04 — Found and fixed: kill switch didn't gate the only live HTTP transaction endpoint

**Requested**: verify the Day 3 kill switch actually works against the live
Render deployment, with real request/response evidence, not an assumption.
Ran the full activate -> attempt transaction -> confirm still active ->
deactivate -> retry sequence against `https://setu-59l6.onrender.com`.

**What the live test found**: `GET /admin/kill-switch` and
`POST /admin/kill-switch/{activate,deactivate}` all worked correctly
(`active: false -> true -> false`, admin-key auth enforced). But step 3 —
attempting a transaction while active — did **not** get rejected.
`GET /products/mechanical-keyboard-65` returned its completely normal `402
Payment Required` body, byte-identical whether the kill switch was active
or not.

**Root cause**: `TrustGuard.authorize_purchase` (which checks the kill
switch) is only called from `BuyerAgent._pay_and_collect` — an in-process
code path with no HTTP entry point on the deployed server. The one live
endpoint that actually processes anything, `GET /products/{id}` (backed by
`MerchantAgent.handle_request`), never called into `TrustGuard` at all.
Day 3's tests all exercised the in-process Buyer/Merchant flow and never
caught this, because none of them went through the real FastAPI app against
a path a kill switch was supposed to cover.

**Fix**: added a kill-switch check at the very top of
`MerchantAgent.handle_request`, before any product lookup or payment
verification — returns `503 {"error": "kill switch is active (...); no new
transactions are being processed"}`. This gates both the unpaid quote (402)
and paid-verification legs of the endpoint, matching "halts all new
transaction processing immediately" literally. Also fixed a related bug
this exposed: `BuyerAgent.negotiate_and_purchase`'s opening quote fetch
(`merchant_agent.handle_request(candidate.id)`) assumed a `402` response
and would `KeyError` crash on the new `503` — now checks `status_code`
first and fails gracefully into `NegotiationOutcome(success=False, ...)`.

**New tests**: `test_kill_switch_active_rejects_request_before_any_processing`
(unit, `MerchantAgent.handle_request` directly) and
`test_kill_switch_blocks_the_live_products_endpoint` (through the real
FastAPI app via `TestClient`, reproducing the exact sequence run against
production). 105 tests passing (up from 103).

**First live attempt (pre-fix, pre-deploy), for the record:**
1. `GET /admin/kill-switch` → `{"active":false,...}` — 200
2. `POST .../activate` → `{"active":true,"reason":"live re-verification after fix",...}` — 200
3. `GET /products/mechanical-keyboard-65` while active → still returned the
   normal `402` — because the fix was only committed locally at that point,
   not yet pushed/deployed. Confirmed via `git status`/`git log
   origin/main..HEAD` that the fix hadn't reached Render yet.

**Committed and pushed** as `cd1bd50 "Wire kill switch into GET
/products/{id}, the only live transaction endpoint"`.

**Re-verified against live production after Render redeployed** (full
six-step sequence, real `X-ADMIN-KEY`, actual responses below):

```
=== activate ===
{"active":true,"reason":"post-deploy live verification","activated_at":1788463756.7426338}
HTTP_STATUS=200

=== THE TEST: products endpoint while active ===
{"error":"kill switch is active (post-deploy live verification); no new transactions are being processed"}
HTTP_STATUS=503

=== confirm still active ===
{"active":true,"reason":"post-deploy live verification","activated_at":1788463756.7426338}
HTTP_STATUS=200

=== deactivate ===
{"active":false,"reason":null,"activated_at":null}
HTTP_STATUS=200

=== confirm resumed ===
{"x402Version":1,"accepts":[{"scheme":"razorpay-inr",...}]}
HTTP_STATUS=402
```

**Closed.** The kill switch now genuinely blocks the live `GET
/products/{id}` endpoint on production (`503`, correct error body citing
the activation reason) and correctly resumes normal service (`402`) after
deactivation.

**Lesson recorded**: Day 3's own tests were internally consistent and all
passed, but every one of them drove the trust layer through
`BuyerAgent`/`MerchantAgent` Python objects directly — none of them asked
"what does the deployed HTTP surface actually expose, and does *that* path
go through this code." A feature can be fully covered by passing tests and
still not protect the thing it claims to protect, if the tests never
exercise the real entry point production traffic uses. Testing against the
live URL (this session) is what caught it; the same class of gap would be
worth checking for `POST /admin/kill-switch/*` auth or any future endpoint
too — always ask "which HTTP path actually reaches this check" before
declaring a safety control done.

## 2026-09-04 — Incident: the 2026-09-03 import "fix" below was wrong and broke production — reverted

**What happened**: the entry directly below this one ("Fix: broken imports
under Render's actual run context") was built on an unverified assumption
about how Render invokes this service. It was never checked against an
actual Render log before being deployed. It shipped, Render's next deploy
failed, and the live backend went down.

**Actual Render log** (2026-09-03T18:21-18:22, paraphrased): build succeeds
(`pip install -r requirements.txt` from the repo root — confirming Render's
root directory *is* the repo root, not `backend/`), then:

```
==> Running 'uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT'
...
File "/opt/render/project/src/backend/app/main.py", line 10, in <module>
    from app.catalog import get_catalog
ModuleNotFoundError: No module named 'app'
```

So the real configuration was, and still is, the opposite of what the
2026-09-03 fix assumed: root directory = repo root, start command =
`uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`. `backend` *is*
the correct top-level package for this deployment. `backend.app.main`
itself imported fine (Python treated `backend` as an implicit namespace
package even without `__init__.py`) — it was `main.py`'s own internal
`from app.catalog import get_catalog` that failed, because nothing put a
bare `app` on `sys.path` in that run context.

**Revert**: all 35 files touched by the 2026-09-03 change were reverted —
`from app.X import Y` back to `from backend.app.X import Y` throughout
`backend/app/**` and `backend/tests/**`; `backend/__init__.py` restored;
`Makefile`'s `run`/`demo` targets back to `uvicorn backend.app.main:app
--reload --port 8001` / `python -m backend.app.scripts.demo_payment` (no
`cd backend`); the docstring in `negotiation_demo.py` and the
`docs/TESTING.md` run instructions restored to `python -m
backend.app.scripts.negotiation_demo`; `docs/DEPLOYMENT.md`'s "Render
service configuration" section rewritten to state the actual, log-verified
configuration and to flag this exact mistake for next time.

**Verified before calling this done:**

- `pytest backend/tests -v` (repo root) → 103/103 passing.
- `uvicorn backend.app.main:app --port 8125`, run from the repo root —
  i.e. reproducing Render's actual invocation shape, not a guess — boots
  cleanly; `GET /health` and `GET /catalog` both return `200`.

**Lesson, recorded so it isn't repeated**: a bug report describing "how the
deployment runs" is a claim, not a verified fact, even when it comes from
the project owner relaying their own understanding — Render's dashboard
config can differ from what anyone remembers configuring. The 2026-09-03
fix should have asked for (or fetched) an actual Render start-command/log
confirmation before touching import structure repo-wide, especially for a
change with no local way to fully reproduce the target platform's exact
process-launch context. Local `uvicorn`/`pytest` runs alone proved the fix
internally consistent, not that it matched production.

## 2026-09-03 — Fix: broken imports under Render's actual run context (REVERTED — see 2026-09-04 entry above; this was based on a wrong assumption about Render's config)

**Bug**: every module under `backend/app/` imported as `from backend.app.X
import Y`, which only resolves when the process is started with `backend`
as a top-level package (i.e. `uvicorn backend.app.main:app` run from the
repo root). Render's actual service configuration runs uvicorn from inside
`backend/` as the root directory with `app.main:app` as the target — there,
`backend` isn't an importable top-level package, so every import in the
chain fails at boot.

**Fix**:

- Rewrote every `from backend.app.X import Y` / `import backend.app.X` in
  `backend/app/**` and `backend/tests/**` to `from app.X import Y` /
  `import app.X` (35 files).
- Deleted `backend/__init__.py`. This is the load-bearing part of the fix:
  with it gone, `backend/` is a plain path root instead of a package, so
  pytest's own rootdir-walk (which requires an unbroken `__init__.py` chain
  to keep climbing) stops at `backend/` and inserts *that* directory onto
  `sys.path` — meaning `app` resolves identically whether pytest runs from
  the repo root (`pytest backend/tests -v`, unchanged in the Makefile/CI)
  or uvicorn runs from inside `backend/`. Without this, source and test
  code would have ended up importing the same files under two different
  module identities (`app.X` vs `backend.app.X`), silently breaking every
  `lru_cache`-backed singleton (`get_settings()`, `get_catalog()`, etc.).
- Updated `Makefile`'s `run`/`demo` targets to `cd backend && ...` to match.
- Fixed docstring run instructions in `negotiation_demo.py` and
  `docs/TESTING.md` that referenced the old `python -m
  backend.app.scripts.negotiation_demo` form.
- Added a "Render service configuration" note to `docs/DEPLOYMENT.md`
  documenting the required root directory + start command.

**Verified:**

- `pytest backend/tests -v` (from repo root, matching `Makefile`/CI
  exactly) → 103/103 passing, no regressions.
- `uvicorn app.main:app --reload --port 8124` started from inside
  `backend/` (the real Render run context) → boots cleanly, `GET /health`
  and `GET /catalog` both return `200` with real data. Also verified the
  non-`--reload` form the same way.

## 2026-09-03 — Day 3: trust/safety layer (signed identity, policy, idempotency, velocity, kill switch, retry)

**Goal for today**: the trust/safety layer that differentiates Setu from a
"two LLMs chat and checkout" demo — signed agent identity, a policy/gating
engine, idempotency, velocity limits + kill switch, and external-failure
handling, each with tests that prove the rule actually fires, not just that
it exists. Threat model expanded alongside the code as it was built.

**Built:**

- `backend/app/trust/identity.py`: Ed25519 keypairs per agent
  (`AgentIdentity`), scoped/expiring credentials signed by a trusted issuer
  (`AgentCredential` + `CredentialIssuer` — the Merchant Agent is the trust
  root for its own marketplace), and signed request envelopes
  (`SignedRequest`/`build_signed_request`) covering payload + nonce +
  timestamp + idempotency key under one signature.
- `backend/app/trust/policy.py`: `PolicyEngine` — spend cap and category
  rules today (discount bounds via `evaluate_discount`), config-driven from
  `Settings`, each rule independently testable. Within bounds: approved.
  Outside: escalated with a specific, human-readable reason — never a
  silent drop.
- `backend/app/trust/idempotency.py`, `velocity.py`, `kill_switch.py`,
  `retry.py`: in-memory dedup store, sliding-window per-agent rate limiter,
  a global halt flag, and `retry_with_backoff` for transient Razorpay
  failures.
- `backend/app/trust/guard.py`: `TrustGuard.authorize_purchase()` — the
  single choke point composing all of the above in order (kill switch ->
  signature/credential -> replay -> credential scope -> idempotency ->
  velocity -> policy bounds), logging every rejection with agent id, rule,
  and reason.
- Wired into the real purchase path: `MerchantAgent` now owns a
  `TrustGuard`, issues credentials to Buyer Agents it onboards, and wraps
  its Razorpay `fetch_payment` call in `retry_with_backoff`.
  `BuyerAgent` generates its own identity at construction, gets issued a
  credential from the merchant, and signs every purchase attempt
  (`_pay_and_collect`) before it ever touches the payment rail —
  rejected/escalated purchases never reach `razorpay_client.create_order`.
- `POST /admin/kill-switch/{activate,deactivate}` + `GET
  /admin/kill-switch` in `main.py`, protected by a shared `X-ADMIN-KEY`
  (`Settings.admin_api_key`).
- `docs/THREAT_MODEL.md` expanded in full: replay attacks, agent
  impersonation, budget overrun, malicious catalog data, and prompt
  injection via product descriptions, each with what specifically defends
  against it and which test proves it.
- 53 new tests (96 total, up from 43): identity signing/verification,
  policy rules firing, idempotency dedup, velocity windows, kill-switch
  activate/deactivate (unit + HTTP), retry/backoff, and a `TrustGuard`
  integration suite covering unsigned/wrong-key/out-of-scope rejection, a
  genuine duplicate purchase resulting in exactly one charge, a kill switch
  triggered mid-scenario blocking the remaining leg, and a simulated
  Razorpay timeout recovering via retry.

**Verified today:**

- `pytest backend/tests -v` → 96/96 passing.
- Full negotiate-and-purchase flow smoke-tested against the fake Razorpay
  client with the new identity/credential wiring in place (no Day 2
  behavior regressed — same 43 Day 1/2 tests still pass unmodified).
- `POST /admin/kill-switch/activate` without/with a wrong `X-ADMIN-KEY` ->
  `401`; with the correct key -> `200`, and a subsequent purchase attempt
  is blocked until `deactivate` is called (`test_kill_switch_endpoint.py`,
  `test_kill_switch_triggered_mid_scenario_blocks_the_upsell_leg`).

**Follow-up, same day:** the `max_daily_spend_paise` scope cut above was
closed out — `backend/app/trust/daily_spend.py` (`DailySpendTracker`, a
rolling-24h per-agent spend sum) is now wired into `TrustGuard` right after
the velocity check, and only records spend for transactions that actually
completed (`TrustGuard.record_spend`, called from `BuyerAgent._pay_and_collect`
only once a transaction id comes back — a rejected/escalated attempt never
counts). New tests:
`test_daily_spend_cap_fires_after_a_sequence_of_individually_valid_transactions`
(guard-level) and `test_daily_spend_cap_fires_across_a_sequence_of_individually_valid_purchases`
(through the real BuyerAgent/MerchantAgent flow) — both prove the cap fires
from a sequence of transactions that are each individually within every
other bound, isolating this rule specifically. 103 tests passing (up from
96).

**Known gaps carried forward (see docs/THREAT_MODEL.md):**

- Trust-layer state (idempotency store, velocity counters, nonce cache,
  kill switch) is in-process/per-instance — fine for today's single Render
  instance, would need a shared store before running more than one.
- Admin kill-switch auth is a single shared static key, not per-operator.
- The "signed request" boundary is each Buyer->Merchant call, not each
  individual Zeuthen negotiation round (those are still computed in one
  local process call, a carried-forward Day 2 simplification).

**Deployment:** not run from this session — redeploy Render/Vercel
manually once you've reviewed the diff, and set `ADMIN_API_KEY` on Render
(see `docs/DEPLOYMENT.md`). New dependency: `cryptography==50.0.1` added to
`requirements.txt` (Ed25519 signing) — make sure Render's build picks it up.

**Next:** whatever Day 4 covers, or hardening any of the gaps above.

## 2026-09-03 — Day 2: Buyer Agent, Zeuthen bargaining, unattended negotiation loop

**Goal for today**: Buyer Agent that negotiates with the Merchant Agent over
the Day-1 x402 flow using a real Zeuthen bargaining strategy (not an
approximation), rules-first with Gemini used only for offer phrasing, tested
end-to-end against a fake Razorpay client across 3 scenarios, then redeploy.

**Built:**

- `backend/app/bargaining/zeuthen.py`: pure, deterministic Zeuthen strategy
  — `buyer_utility`/`merchant_utility` (normalized `[0,1]`, ideal vs.
  reservation price), `risk()` (fractional utility lost by full concession),
  `run_zeuthen_negotiation()` (who concedes + risk-proportional concession
  size, capped/floored; stalemate and max-rounds-exceeded as explicit
  failure states; a convergence-gap tolerance so closing a negligible
  remaining gap doesn't burn the round budget). No LLM anywhere in this
  module. Full writeup in `docs/BARGAINING.md`.
- `backend/app/buyer_agent/`: `BuyerAgent.negotiate_and_purchase(goal, budget)`
  — deterministic keyword-based product matching, skips negotiation
  outright when budget covers list price (and evaluates the existing Day-1
  upsell offer against remaining budget), otherwise runs the Zeuthen engine
  against a `MerchantParty` supplied by the Merchant Agent, then pays the
  agreed price via the fake Razorpay client and closes the x402 cycle.
- `backend/app/merchant_agent/agent.py`: added `min_acceptable_price()` /
  `negotiation_party()` (merchant's reservation price = configured fraction
  of list price); `handle_request()` now accepts an `agreed_price_paise`
  override so a purchase closing out a negotiation is verified against the
  negotiated price, not blindly against catalog list price — never taken
  from client input, only from code that ran a negotiation to completion.
- `backend/app/fake_razorpay.py`: in-process fake Razorpay client (create
  order, pay, fetch, verify signature) for unattended automated flows —
  distinct from the real `RazorpayClient`, which still requires the manual
  Checkout click-through (see 2026-09-02 decision).
- `backend/app/llm/logging_client.py`: `LoggingLLMClient` wraps any
  `LLMClient`, logs latency + estimated input/output token cost per call.
- `backend/app/scripts/negotiation_demo.py`: runs all 3 required scenarios
  unattended against the real Gemini API + fake Razorpay client, prints the
  full round-by-round trace and the LLM call log.
- New config: `merchant_min_price_factor`, `negotiation_max_rounds`,
  `negotiation_min_concession_fraction`, `negotiation_max_concession_fraction`,
  `negotiation_convergence_fraction`, `buyer_price_ceiling_factor`.
- 12 new pytest tests (`test_zeuthen.py`, `test_buyer_agent.py`) — 43/43
  passing total.

**Verified today:**

- `pytest backend/tests -v` → 43/43 passing, including all 3 required
  scenarios run against `FakeRazorpayClient` + a scripted fake LLM client
  (deterministic, no network): comfortable budget with upsell accepted,
  tight budget requiring genuine multi-round negotiation (asserted: more
  than 1 round, both sides concede at least once), and a budget with no
  viable match (asserted: graceful `stalemate`/`max_rounds_exceeded`
  failure, never a silent success).
- `negotiation_demo.py` run three times against the **real** Gemini API
  (not mocked): the negotiated price sequence for the tight-budget scenario
  (`239465 → 278117 → 324776 → 308445 → 297830 → 290930 → 286445 → 283530 →
  279505 → 282740`, closing at **281122 paise**) came out byte-identical
  across all three runs — including a run where Gemini calls failed
  entirely (hit the `gemini-3.6-flash` free tier's 20-requests/day cap) and
  fell back to deterministic non-LLM phrasing. Direct evidence the Zeuthen
  math, not the LLM, drives the negotiated numbers.
- Hit and fixed a live issue: Day 1's configured model
  (`gemini-2.0-flash`) is now fully deprecated (404s), and its replacement
  `gemini-2.5-flash` is also blocked for new users; switched to
  `gemini-flash-lite-latest` after confirming it has a workable free-tier
  quota. See `docs/DECISIONS.md`.
- A full clean run (`gemini-flash-lite-latest`, no rate-limit fallbacks)
  produced natural-language offers for both sides across all 3 scenarios —
  captured in full; see the negotiation trace shared with the user this
  session.

**Known gaps carried forward:**

- Negotiation engine is a single shared function holding both parties'
  reservation prices, not two independent agents inferring each other's
  utility from observed offers alone — documented simplification, see
  "What this does not model" in `docs/BARGAINING.md`.
- Merchant's reservation price is one global fraction of list price, not a
  per-product floor.
- No spend-approval/policy gate in front of the Buyer Agent yet (Day 3).
- `negotiation_demo.py` is not part of `make test`/CI (uses the real Gemini
  API, real network calls, real quota) — pytest coverage uses a scripted
  fake LLM client instead.

**Next (Day 3):** policy/trust layer — spend limits and velocity checks
actually enforced, payment replay protection, human-approval gate above a
spend threshold.

## 2026-09-03 — Deployment + frontend wired to live backend

**Built:**

- `frontend/src/api.js`: `API_BASE_URL` reads `VITE_API_URL`, falls back to
  `/api` (the local dev proxy). `getHealth()` / `getCatalog()` fetch
  helpers.
- `frontend/src/App.jsx`: fetches both on mount, renders a live
  loading/ok/error state instead of static text.
- CORS: `backend/app/config.py` gained `cors_allowed_origins`
  (config-driven, not hardcoded); `CORSMiddleware` wired in `main.py`,
  `allow_methods=["GET"]`, `allow_headers=["*"]`.
- Fixed a local dev-only port conflict: moved the backend's dev port from
  8000 to 8001 (Docker Desktop's WSL relay silently squats on 8000 on this
  machine) — updated `Makefile`, `vite.config.js`, README,
  `docs/DEPLOYMENT.md`.
- Backend deployed to Render (`https://setu-59l6.onrender.com`), frontend
  to Vercel (`https://setu-alpha-beige.vercel.app`); README's live-demo
  line updated to the real URLs.

**Verified today:**

- CORS: real curl checks against a running server — preflight and GET from
  both allowed origins (`localhost:5173`, the Vercel origin) get
  `Access-Control-Allow-Origin` back; a disallowed origin gets none.
- End-to-end deployment: confirmed the deployed frontend's built JS bundle
  points at the correct Render backend URL (not stale/mismatched), then
  loaded the live Vercel site in a headless browser and saw it render real
  data: "Backend live — status: ok, env: test, catalog: 8 products."
- `pytest backend/tests -v` → still 31/31 passing after the CORS/config
  change.

**Known gaps carried forward:**

- No automated test for the frontend fetch logic or for CORS behavior —
  both verified manually only (see `docs/TESTING.md`).
- No CI-orchestrated deploy step; Render/Vercel deploys are separate from
  `.github/workflows/test.yml`.

## 2026-09-02 — Day 1: Foundation, Razorpay integration, Merchant Agent

**Goal for today**: repo foundation, config system, working Razorpay
test-mode payment, `/health`, and a real/tested Merchant Agent handling x402
requests via Gemini. Buyer Agent, bargaining, and policy/trust layer are
explicitly out of scope until Day 2/3.

**Built:**

- Repo structure: `backend/app` (FastAPI package), `frontend/` (React +
  Tailwind, Vite), `docs/`, `.github/workflows/test.yml`.
- Config system (`backend/app/config.py`): Pydantic Settings, spend limits,
  category allowlist, velocity thresholds — all config-driven; test/live
  mode structurally separated (live mode currently refuses to boot).
- Razorpay integration (`backend/app/razorpay_client.py`): order creation,
  payment fetch/capture, signature verification, all via the official SDK.
- `backend/app/scripts/demo_payment.py`: real order via Orders API, payment
  completed via Razorpay's actual Checkout widget (semi-automated — opens a
  visible browser, waits for one manual test-card click-through; see
  docs/DECISIONS.md for why fully headless completion was rejected).
- x402 subset (`backend/app/x402/`): `PaymentRequirement`,
  `PaymentRequiredBody`, `X-PAYMENT`/`X-PAYMENT-RESPONSE` encode/decode,
  full input validation on the untrusted header path. Adapted to a
  `razorpay-inr` scheme instead of literal on-chain x402 — confirmed with
  the user first. Documented in `docs/PROTOCOL.md`.
- Catalog (`backend/app/catalog/`): 8 real products (keyboards/mice/
  monitors/accessories) across 3 categories, with explicit `related_ids`
  upsell pairings (e.g. monitor -> monitor arm, crossing categories) so the
  upsell path is exercisable and matches the user-provided pairing table.
- Merchant Agent (`backend/app/merchant_agent/agent.py`): handles 402/200
  x402 cycle, verifies payments against Razorpay, offers a Gemini-proposed
  but code-bounded upsell (discount cap + product whitelist enforced
  server-side regardless of model output).
- Gemini LLM client behind a provider-agnostic interface
  (`backend/app/llm/base.py` + `gemini_client.py`).
- 31 pytest tests, all passing (`backend/tests/`).
- `docs/*` skeletons + `PROTOCOL.md` written in full as the protocol was
  built.

**Verified today:**

- `pytest backend/tests -v` → 31/31 passing.
- `GET /health` → `200 {"status": "ok", "env": "test"}`.
- `GET /products/mechanical-keyboard-65` (no payment) → `402` with a
  correctly shaped `PaymentRequirements` body.
- `GET /products/monitor-27-1440p-144hz` → confirms cross-category
  `related_ids` upsell pairing loads correctly.
- Real Razorpay test keys added mid-day. `make demo` run end-to-end: real
  order created, real Checkout widget completed with the official test
  card, payment captured and signature-verified.
  Transaction ID: `pay_TWvFV7TVvlSAe8` (status=captured).
- The `X-PAYMENT` header verification path (amount/signature/status
  checks, resource-mismatch rejection) is covered by
  `test_merchant_agent.py` against a fake Razorpay client; not yet
  re-exercised against the live server with a real X-PAYMENT header from an
  actual completed payment — next natural check when the Buyer Agent exists
  to generate one.

**Known gaps carried forward (see docs/THREAT_MODEL.md):**

- No payment replay protection yet (a receipt could in principle be reused).
- Velocity/spend limits exist in config but aren't enforced anywhere yet.
- `make demo`'s payment-completion step is semi-automated (one manual
  click), not headless — see docs/DECISIONS.md.

**Next (Day 2):** Buyer Agent, Zeuthen bargaining strategy skeleton.
