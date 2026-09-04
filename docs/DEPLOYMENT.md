# DEPLOYMENT.md

> Status: live. Backend on Render, frontend on Vercel, both reachable and
> talking to each other in production as of 2026-09-03.

## Live deployment

- **Frontend**: [https://setu-alpha-beige.vercel.app](https://setu-alpha-beige.vercel.app) (Vercel)
- **Backend**: [https://setu-59l6.onrender.com](https://setu-59l6.onrender.com) (Render)

Verified end-to-end: the deployed frontend's built bundle points at the
Render backend URL above, and loading the live site renders real data
fetched from it (`GET /health` + `GET /catalog`) — not a static page.

### Pending before the next deploy (as of 2026-09-04, Day 4 Part 3)

Neither of these is deployed yet — both were left uncommitted this session
on explicit instruction, so the live URLs above still run the pre-dashboard
build:

- **`backend/app/main.py`**: an additive, backward-compatible change so
  `/negotiate`'s response includes each round's real
  `buyer_offer_paise`/`merchant_offer_paise`/`buyer_risk`/`merchant_risk`
  (see `docs/DECISIONS.md`, 2026-09-04). Without this deployed, the
  dashboard's live-triggered negotiations render messages-only (no risk
  chart) against production.
- **`frontend/`**: the public dashboard itself (`src/App.jsx`,
  `src/components/`, `src/lib/`, `public/harness/`), plus two new
  dependencies in `package.json` (`framer-motion`, `lucide-react`) that a
  fresh `npm install` needs.

### Also pending (Day 4 Part 4, later the same day) — not committed

On top of the above, uncommitted at end of this session:

- **`backend/app/buyer_agent/agent.py` / `main.py`**: `NegotiationTrace`
  now carries a real `latency_ms` per message (measured around the actual
  LLM call), exposed through `/negotiate`'s `trace[]` — used by the
  dashboard's chat-style negotiation replay to pace its typing indicator.
  Without this deployed, a live-triggered negotiation against production
  falls back to a fixed default typing delay per message instead of the
  real one.
- **`frontend/`**: `Header.jsx`, `HowItWorks.jsx`, `NegotiationChat.jsx`,
  `ScrollProgress.jsx`, `SectionReveal.jsx` (new components), plus the
  interactive "try it yourself" form in `LiveFeed.jsx`, the hero/nav
  rework, the `KillSwitch` relocation in `App.jsx`, and the copy cleanup
  described in `BUILD_LOG.md` (Day 4 Part 4). No new dependencies beyond
  the ones already listed above.

### Environment variables set on the hosts (not committed)

- **Render (backend)**: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
  `GEMINI_API_KEY`, `DATABASE_URL`, `MERCHANT_ID`, `CORS_ALLOWED_ORIGINS`
  (must include the Vercel origin — see `.env.example`), and
  `ADMIN_API_KEY` (Day 3 — required to call `POST /admin/kill-switch/*`;
  generate a real random value, the `.env.example` default is dev-only). If `GEMINI_MODEL`
  is explicitly set on Render (rather than left to `Settings`'s default),
  it needs updating to `gemini-flash-lite-latest` — see the 2026-09-03
  entry in `docs/DECISIONS.md` (the old default, `gemini-2.0-flash`, is now
  fully deprecated server-side).
- **Vercel (frontend)**: `VITE_API_URL` set to the Render backend URL above
  (see `frontend/.env.example`). Without this it falls back to `/api`,
  which only resolves via the local dev proxy — production needs it set
  explicitly.

Redeploy either side after changing catalog data, policy config, or the
allowed-origins list.

### Render service configuration (root directory + start command)

Confirmed from a live deploy log (2026-09-04): Render's **root directory
for this service is the repo root**, not `backend/`. The build step runs
`pip install -r requirements.txt` from the repo root (where
`requirements.txt` actually lives), and the start command is:

```
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

`backend` is therefore the top-level Python package in this deployment's
actual run context, matching every internal import in `backend/app/**`
(`from backend.app.X import Y`) and the committed `backend/__init__.py`.
**Do not** change these to `app.X`-style imports or remove
`backend/__init__.py` without also changing Render's start command to
match (root directory `backend/`, start command `uvicorn app.main:app
--host 0.0.0.0 --port $PORT`, and `requirements.txt`/`runtime.txt` moved or
duplicated into `backend/`) — a 2026-09-03 change did exactly that based on
a mistaken assumption about Render's configuration and took the live
backend down (`ModuleNotFoundError: No module named 'app'`); see the
2026-09-04 entry in `BUILD_LOG.md` for the full incident and revert.

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
- CI-orchestrated deploy step — `.github/workflows/test.yml` only runs
  pytest today; it doesn't trigger or gate the Render/Vercel deploys.
