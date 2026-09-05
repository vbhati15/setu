# TESTING.md

> Status: Day 6. 141 backend tests passing, plus a black-box scenario
> harness run for real against the live production API. See `BUILD_LOG.md`
> for the full day-by-day history and every live-verification transcript.

## Run it

```bash
make test
# or
pytest backend/tests -v
```

Expect `141 passed`.

## What's covered

`backend/tests/` (141 tests):

| File | Tests | Covers |
|---|---|---|
| `test_trust_guard.py` | 20 | `TrustGuard`'s full pipeline — kill switch, signature/credential/replay, credential scope, idempotency, velocity, daily spend, policy bounds; both the signed (`authorize_purchase`) and anonymous-caller (`authorize_anonymous_purchase`) paths |
| `test_merchant_agent.py` | 14 | Full 402/200 request handling against fake Razorpay + fake LLM clients — unpaid, unknown product, malformed id, valid payment, amount mismatch, bad signature, resource mismatch, upsell discount capping/whitelisting, anonymous-purchase wiring |
| `test_catalog.py` | 13 | Catalog loading/validation, id/category rules, control-character rejection, `related()` lookup |
| `test_trust_integration.py` | 9 | End-to-end trust-layer behavior through the real Buyer/Merchant flow — duplicate-charge prevention, spend-cap rejection, daily-spend-cap sequences, kill-switch mid-scenario, velocity escalation, Razorpay retry/timeout handling |
| `test_trust_identity.py` | 8 | Ed25519 signing/verification, credential issuance/expiry/tampering, signed-request round-trips |
| `test_zeuthen.py` | 8 | Utility function bounds, risk formula edge cases, full negotiations that converge, stalemate, close instantly, and the round-cap tie-break (settles a near-miss gap or reports an explicit no-deal) |
| `test_x402.py` | 7 | `PaymentRequiredBody` shape, `X-PAYMENT` encode/decode round-trip, rejection of malformed/oversized/invalid headers |
| `test_negotiate_endpoint.py` | 6 | `POST /negotiate` over HTTP — comfortable budget, invalid budget, kill-switch block, credential-scope rejection, occasion/priority behavioral wiring |
| `test_checkout_quote.py` | 6 | The signed `checkout_token` — round-trip, tampering, expiry |
| `test_checkout_endpoints.py` | 6 | `POST /checkout/order` + `POST /checkout/confirm` over HTTP — invalid/expired/tampered tokens, kill-switch block, unknown product |
| `test_velocity.py` | 5 | Per-minute/per-hour limits, window reset, per-agent isolation |
| `test_policy.py` | 5 | Spend cap, category allowlist, discount-percent bounding |
| `test_kill_switch_endpoint.py` | 5 | `/admin/kill-switch/*` over HTTP — activate/deactivate, admin-key enforcement |
| `test_daily_spend.py` | 5 | 24h rolling spend tracking and cap enforcement |
| `test_buyer_agent.py` | 5 | The three required end-to-end scenarios against `FakeRazorpayClient` + a scripted (non-LLM) fake `LLMClient`: comfortable budget with upsell accepted, tight budget requiring multi-round negotiation, and a budget with no viable match — plus the no-matching-product-at-all case |
| `test_retry.py` | 4 | `retry_with_backoff` — transient failure recovery, persistent failure surfaced as a clear rejection |
| `test_certificate.py` | 4 | Signed transaction certificates — expected fields, real verification round-trip through the actual standalone `verify_certificate.py` script, tamper detection, wrong-key forgery detection |
| `test_products_endpoint_trust.py` | 3 | `GET /products/{id}` over HTTP — spend-cap rejection and kill-switch priority, both short-circuiting before any real Razorpay call |
| `test_kill_switch.py` | 3 | `KillSwitch` unit behavior |
| `test_idempotency.py` | 3 | `IdempotencyStore` unit behavior |
| `test_health.py` | 2 | `/health` and `/catalog` endpoints |

For a real, unattended, non-mocked run against the actual Gemini API (not
the fake LLM client used in tests), see
`backend/app/scripts/negotiation_demo.py` — `python -m
backend.app.scripts.negotiation_demo`. Prints the full round-by-round trace
plus a per-call LLM log (latency, estimated token cost). Payment still goes
through `FakeRazorpayClient`, not the real Checkout widget — see
`docs/DECISIONS.md`, 2026-09-02, for why automated flows never drive the
real widget.

## Live verification against production

Unit tests prove the code is correct in isolation. Two things go further
and prove it live, against the actual deployed system:

- **`backend/app/scripts/scenario_harness.py`** — black-box (HTTP only, no
  imports from the app itself), ran 22 named scenarios (37 real HTTP calls)
  against `https://setu-59l6.onrender.com`: comfortable-budget purchases,
  tight-budget multi-round negotiations, graceful no-match failures, and
  deliberate rule-breach attempts (credential scope, velocity, daily spend,
  duplicate idempotency keys). Results are structured JSONL, checked into
  `backend/app/scripts/harness_results/*.jsonl`, and surfaced live in the
  dashboard's Test Results/Audit Log tabs. Run it yourself:
  ```bash
  python -m backend.app.scripts.scenario_harness
  ```
- **Every `TrustGuard` rule** — kill switch, signature/replay, credential
  scope, idempotency, velocity, daily spend cap, spend cap, category — has
  additionally been fired by hand against production with real
  request/response transcripts, not just through the harness. Full
  transcripts in `BUILD_LOG.md`; summarized with what each one proves in
  `docs/THREAT_MODEL.md`.
- **The real Razorpay Checkout and certificate-download flow** have been
  run end to end by an actual human (not just a code path) — a real test-mode
  payment, a real transaction id, a real downloaded certificate verified by
  the real standalone script. See `BUILD_LOG.md`, 2026-09-05 (Day 6).

## Standalone certificate verification

`verify_certificate.py` (repo root) is deliberately outside the test suite
and outside the `backend` package — it's meant to run standalone, with only
`cryptography` as a dependency, no network call:

```bash
python verify_certificate.py path/to/certificate.json
```

`backend/tests/test_certificate.py` imports and exercises this exact script
(not a reimplementation of its logic) to keep the two from drifting apart.

## What's NOT covered yet

- No integration test against a *real* Razorpay test account inside
  `pytest` (would need real test-mode credentials in CI). `make demo` and
  the live scenario harness are the real-integration checks instead.
- No test against a real Gemini API call inside `pytest` (LLM calls are
  mocked/faked in `backend/tests/` by design — deterministic, no network, no
  quota usage). Real-Gemini coverage is `negotiation_demo.py` and the live
  scenario harness, both run manually, not part of `make test` / CI.
- No frontend tests — the frontend does make real fetch calls (`/health`,
  `/catalog`, `/negotiate`, `/checkout/*`, `/admin/kill-switch/*`, see
  `frontend/src/api.js`), verified manually against both local dev and the
  live deployment, but there's no automated test for it.
- No automated CORS test — verified manually with curl against a running
  server; not covered by `backend/tests/`.

## Property-based testing (hypothesis)

`hypothesis` is in `requirements.txt` but not yet used — planned candidates:
catalog id/price fuzzing, X-PAYMENT header fuzzing for the decode path.
