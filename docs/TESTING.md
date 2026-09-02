# TESTING.md

> Status: updated with what actually exists (Day 2).

## What's covered today

`backend/tests/` (43 tests, all passing):

- `test_health.py` — `/health` and `/catalog` endpoints via FastAPI
  `TestClient`.
- `test_catalog.py` — catalog loading/validation, id/category rules,
  control-character rejection, `related()` lookup.
- `test_x402.py` — `PaymentRequiredBody` shape, `X-PAYMENT` encode/decode
  round-trip, rejection of malformed/oversized/invalid headers.
- `test_merchant_agent.py` — full 402/200 request handling against fake
  Razorpay + fake LLM clients: unpaid, unknown product, malformed id, valid
  payment, amount mismatch, bad signature, resource mismatch, upsell
  discount capping, upsell whitelist enforcement.
- `test_zeuthen.py` — utility function bounds (buyer/merchant), risk
  formula edge cases, a full negotiation that converges within budget, a
  full negotiation that stalemates when budget is below the merchant's
  floor, and instant closing when opening offers already cross.
- `test_buyer_agent.py` — the three required end-to-end scenarios against
  `FakeRazorpayClient` + a scripted (non-LLM) fake `LLMClient`: comfortable
  budget with upsell accepted, tight budget requiring multi-round
  negotiation (asserts `len(rounds) > 1` and that both sides concede at
  least once, not just that it "converged"), and a budget with no viable
  match (asserts graceful, structured failure — a matched product but a
  `stalemate`/`max_rounds_exceeded` outcome, never a silent success). Also
  covers the case where no catalog product matches the goal at all.

For a real, unattended, non-mocked run against the actual Gemini API (not
just the fake LLM client used in tests), see
`backend/app/scripts/negotiation_demo.py` — `python -m
backend.app.scripts.negotiation_demo`. This prints the full round-by-round
trace for all three scenarios plus a per-call LLM log (latency, estimated
token cost). Payment still goes through `FakeRazorpayClient`, not the real
Checkout widget — see `docs/DECISIONS.md`, 2026-09-02, for why automated
flows never drive the real widget.

Run with:

```bash
make test
# or
pytest backend/tests -v
```

## What's NOT covered yet

- No integration test against a *real* Razorpay test account (would need
  real test-mode credentials in CI, which we don't want to commit/store
  there yet). `make demo` is the manual real-integration check.
- No test against a real Gemini API call inside `pytest` (LLM calls are
  mocked/faked in `backend/tests/` by design — deterministic, no network, no
  quota usage). Real-Gemini coverage is `negotiation_demo.py`, run manually,
  not part of `make test` / CI.
- No frontend tests — the frontend does make a real fetch call to
  `/health` + `/catalog` now (see `frontend/src/api.js`), verified manually
  against both local dev and the live deployment, but there's no automated
  test for it (e.g. mocking the fetch and asserting render state).
- No automated CORS test — verified manually with curl against a running
  server (allowed vs. disallowed `Origin` headers); not covered by
  `backend/tests/`.

## Property-based testing (hypothesis)

`hypothesis` is in `requirements.txt` but not yet used — planned candidates:
catalog id/price fuzzing, X-PAYMENT header fuzzing for the decode path.
