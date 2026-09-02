# Setu

**An agent-to-agent commerce trust layer — a hackathon project, built in a
few days, not affiliated with any existing company or product also named
"Setu."**

Two AI agents (a Buyer and a Merchant) negotiate and complete real payments
over Razorpay's test-mode APIs, speaking a Razorpay-adapted subset of the
x402 protocol and (soon) bargaining via a Zeuthen strategy.

Live demo: [https://setu-alpha-beige.vercel.app](https://setu-alpha-beige.vercel.app) (frontend) · [https://setu-59l6.onrender.com](https://setu-59l6.onrender.com) (backend API)

## Status

Day 1 of a compressed build: repo foundation, config system, Razorpay
test-mode payments, and a working Merchant Agent that speaks x402. No Buyer
Agent or bargaining logic yet — see `BUILD_LOG.md` for the day-by-day log
and `docs/DECISIONS.md` for why things were built the way they were.

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
- [`docs/BARGAINING.md`](docs/BARGAINING.md) — Zeuthen strategy design (not yet built)
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- [`docs/TESTING.md`](docs/TESTING.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)
- [`BUILD_LOG.md`](BUILD_LOG.md)

## License

MIT — see [`LICENSE`](LICENSE).
