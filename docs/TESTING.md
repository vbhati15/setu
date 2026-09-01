# TESTING.md

> Status: skeleton, updated with what actually exists as of Day 1.

## What's covered today

`backend/tests/` (28 tests, all passing as of Day 1):

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
- No test against a real Gemini API call (LLM calls are mocked/faked in
  tests by design — deterministic, no network, no quota usage).
- No Buyer Agent / negotiation tests (doesn't exist yet).
- No frontend tests (placeholder page only).

## Property-based testing (hypothesis)

`hypothesis` is in `requirements.txt` but not yet used — planned candidates:
catalog id/price fuzzing, X-PAYMENT header fuzzing for the decode path.
