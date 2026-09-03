# BUILD_LOG.md

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
