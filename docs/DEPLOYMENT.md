# DEPLOYMENT.md

> Status: skeleton (Day 1). No deployment has happened yet — this is local
> dev only today. Fill in as the app is actually deployed.

## Local development (today)

```bash
make install   # creates .venv, installs backend + frontend deps
make run        # starts FastAPI on :8001
make demo       # runs the end-to-end Razorpay test-mode payment script
make test       # runs pytest
```

Frontend dev server (separate terminal):

```bash
cd frontend && npm run dev   # :5173, proxies /api -> :8001
```

Backend port is 8001, not the more common 8000, because Docker Desktop's
backend/WSL relay claims port 8000 on Windows — anything hitting
`localhost:8000` while Docker Desktop is running gets silently routed to
Docker's relay instead of the app. If you hit a weird unrelated JSON
response from `/health`, check `netstat -ano | findstr :<port>` for a
process squatting on it before assuming the app is broken.

## Environment variables

See `.env.example`. Copy to `.env` and fill in real Razorpay test keys and a
Gemini API key.

## Known constraint: Razorpay test-mode payment completion is semi-automated

`make demo` creates a real order via the SDK, then opens Razorpay's actual
hosted Checkout widget in a visible (non-headless) browser window and waits
up to 180s for a human to complete it with Razorpay's official test card
(`4100 2800 0000 1007`, any future expiry/CVV, any 4-10 digit OTP). Verified
working end-to-end on 2026-09-02 — real order, real captured payment,
signature-verified.

This is deliberately not fully unattended. Two automated paths were tried
and rejected:

- **S2S UPI Collect** (`POST /v1/payments/create/upi` with the test VPA
  `success@razorpay`) — requires Razorpay Support to manually enable VPA
  validation per-account, and is deprecated for new integrations as of Feb
  2026. Returned `404` against this project's account (feature not
  enabled).
- **Headless Checkout automation** (Playwright driving the real widget) —
  gets stuck indefinitely on the "Sending OTP" step behind Razorpay's
  PerimeterX/HUMAN Security bot detection. Not pursued further: actively
  engineering around a payment provider's fraud detection isn't something
  this project should do, test mode or not.

If a fully unattended demo becomes necessary later, the realistic path is
requesting Razorpay Support enable S2S UPI Collect (or its Intent
successor) for the test account — not defeating Checkout's bot detection.

## Planned (not yet done)

- Container image / Dockerfile.
- Hosting target (TBD — likely Render/Railway/Fly for the FastAPI service,
  static hosting for the frontend).
- Live demo link (placeholder in README.md until deployed).
