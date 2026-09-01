# BARGAINING.md

> Status: skeleton. Zeuthen bargaining strategy is Day 2/3 scope — not
> implemented yet. This file documents the intended design so it can be
> built against.

## Planned approach: Zeuthen strategy

The Zeuthen strategy is a concession protocol for bilateral negotiation:
at each round, whichever agent has *less to lose* by risking conflict
(i.e. lower "risk" = utility loss from conceding vs. utility loss from a
breakdown) is the one who must concede next.

### Planned components (not yet built)

- **Buyer Agent utility function**: budget ceiling, category preferences,
  urgency.
- **Merchant Agent utility function**: price floor (derived from catalog
  price + config-driven minimum margin), bounded upsell value.
- **Risk calculation**: `risk_i = (utility_i(own_offer) - utility_i(opponent_offer)) / utility_i(own_offer)`
  per round, per agent.
- **Concession step**: the higher-risk agent moves toward the other's last
  offer by a bounded step.
- **Termination**: agreement, max-rounds timeout, or explicit walk-away.

## Open questions to resolve before implementation

- Where does the Merchant Agent's price floor come from — fixed % margin in
  config, or per-product?
- How many negotiation rounds is "real-time" for a hackathon demo (target:
  a handful of seconds end-to-end)?
- How does a Zeuthen round map onto the x402 402/200 cycle — is each
  counter-offer a distinct x402 exchange, or a separate negotiation
  sub-protocol before the final x402 payment?

## Non-goals for this hackathon

- General-purpose multi-issue bargaining (price is the only negotiated
  variable for now).
- Learning/adaptive strategies — the Zeuthen rule is deterministic given the
  two utility functions.
