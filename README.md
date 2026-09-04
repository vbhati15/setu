# Setu

**An agent-to-agent commerce trust layer — a hackathon project, built in a
few days, not affiliated with any existing company or product also named
"Setu."**

Two AI agents (a Buyer and a Merchant) negotiate and complete real payments
over Razorpay's test-mode APIs, speaking a Razorpay-adapted subset of the
x402 protocol and bargaining via a Zeuthen strategy.

Live demo: [https://setu-alpha-beige.vercel.app](https://setu-alpha-beige.vercel.app) (frontend) · [https://setu-59l6.onrender.com](https://setu-59l6.onrender.com) (backend API)

## Status

Day 4 of a compressed build: repo foundation, Razorpay test-mode payments,
a Merchant Agent and Buyer Agent that negotiate price via a real Zeuthen
bargaining strategy (see `docs/BARGAINING.md`), a full trust layer
(`TrustGuard` — kill switch, signature/replay defense, credential scope,
idempotency, velocity, daily spend cap, policy bounds) live-verified
against production, a scenario test harness with real HTTP evidence, and a
public single-page dashboard (live negotiation trigger with a Zeuthen
risk-of-conflict chart, a TrustGuard decision-trace panel, real harness
numbers, and a working kill switch). See `BUILD_LOG.md` for the day-by-day
log — the dashboard's one open item is a small additive backend change
awaiting deploy (Day 4 Part 3) — and `docs/DECISIONS.md` for why things
were built the way they were.

## Quickstart

```bash
git clone <this-repo>
cd setu
cp .env.example .env   # fill in Razorpay test keys + Gemini API key
make install
make test               # run the test suite
make run                 # start the FastAPI backend on :8001
make demo               # end-to-end Razorpay test-mode payment (needs real keys in .env)
```

Frontend dev server (separate terminal):

```bash
cd frontend && npm install && npm run dev   # :5173
```

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — the x402 subset, in detail
- [`docs/BARGAINING.md`](docs/BARGAINING.md) — Zeuthen bargaining strategy, implemented
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- [`docs/TESTING.md`](docs/TESTING.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)
- [`BUILD_LOG.md`](BUILD_LOG.md)

## License

MIT — see [`LICENSE`](LICENSE).
