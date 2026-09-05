# BARGAINING.md

How the Buyer Agent and Merchant Agent negotiate price, and why Zeuthen was
chosen over letting the LLM freestyle the negotiation.

## Why Zeuthen, not "ask the LLM to negotiate"

An LLM asked to "negotiate a fair price" has no notion of either party's
actual reservation price, produces different numbers on every run, and gives
no way to prove after the fact that the outcome was principled rather than
a plausible-sounding hallucination. For a payments-adjacent agent that's
unacceptable: the price a Buyer Agent agrees to pay has to be justifiable by
code, not by "the model said so."

Zeuthen's strategy (1930; the standard "monotonic concession protocol" in
automated-negotiation literature) gives a fully deterministic answer to the
two questions a bargaining round has to answer:

1. **Who concedes this round?** The party with less to lose by conceding.
2. **By how much?** Enough to meaningfully address the other party's
   stubbornness, not an arbitrary fixed increment.

Both are computed from each party's own utility function and the two
current offers -- no LLM involved. The LLM's only job in this codebase is
turning a round's numbers into one natural-language sentence for the trace;
see "Division of labor" below.

## Utility functions

Both are normalized to `[0, 1]`: 1.0 at the party's ideal price, 0.0 at its
reservation (walk-away) price.

**Buyer** (`backend/app/bargaining/zeuthen.py::buyer_utility`):

```
U_buyer(price) = clamp01((budget - price) / budget)
```

Ideal price is 0, reservation is the buyer's stated budget. A price at or
above budget is unaffordable -> utility 0, not negative.

**Merchant** (`merchant_utility`):

```
U_merchant(price) = clamp01((price - min_price) / (list_price - min_price))
```

Ideal price is the catalog list price, reservation is `min_price` --
computed as `merchant_min_price_factor * list_price` (default 0.75, see
`Settings.merchant_min_price_factor`). This is a deliberate Day-2
simplification: one global floor fraction rather than a per-product
negotiated-margin table. A real merchant would want per-product floors
(different margins on different SKUs); adding that is a config change, not
an architecture change (`MerchantAgent.min_acceptable_price`).

## Risk of conflict

```
risk(U_own_at_own_offer, U_own_at_opponent_offer) =
    clamp01((U_own_at_own_offer - U_own_at_opponent_offer) / U_own_at_own_offer)
```

if `U_own_at_own_offer <= 0`, risk = 1 (you have nothing left to protect by
holding firm, so backing down costs you nothing you haven't already lost --
by convention this is treated as maximal risk, i.e. don't concede further;
see the reservation-pinning behavior below).

This is: *what fraction of my current utility would I sacrifice if I
capitulated entirely to your last offer, right now?* A party with high risk
has a lot resting on holding its position (holding firm is "safe" relative
to what conceding would cost); a party with low risk loses little by giving
ground, so it should be the one to move.

## The concession rule

Each round:

```
conceder = "buyer" if risk_buyer <= risk_merchant else "merchant"
```

(ties go to the buyer -- an arbitrary but deterministic tiebreak.) If the
risk-preferred conceder is already pinned at its own reservation price
(buyer at budget, merchant at floor), the other party concedes instead, so
one exhausted party doesn't stall the whole negotiation.

Concession size is proportional to the *other* party's risk -- a more
stubborn opponent has to be met with a bigger step, or the negotiation never
moves:

```
step = clamp(risk_of_other_party, min_concession_fraction, max_concession_fraction)
new_offer = own_offer + step * (opponent_offer - own_offer)   # moving toward opponent
```

`min_concession_fraction` (default 0.15) exists because risk can be
arbitrarily close to 0 near convergence, which would otherwise stall
progress indefinitely within a bounded round count.
`max_concession_fraction` (default 0.35) exists for the opposite reason:
early in a negotiation both parties' offers typically give each other 0
utility, so risk is exactly 1.0 on both sides -- an uncapped concession
would jump straight from the opening lowball to the opponent's full asking
price in round one, which isn't a negotiation, it's a coin flip. Capping
keeps the "concede proportional to opponent's risk" rule intact while
guaranteeing several real rounds of back-and-forth. Both are configured in
`Settings` (`negotiation_min_concession_fraction`,
`negotiation_max_concession_fraction`), not hardcoded in the algorithm.

## Convergence, not just crossing

The literal Zeuthen protocol ends when the offers cross
(`buyer_offer >= merchant_offer`). Because each concession is a
*multiplicative* fraction of the remaining gap, closing the last few paise
of an already-tiny gap is an asymptotic process that can burn many rounds on
a difference neither party would care about in practice. `run_zeuthen_negotiation`
therefore also treats a gap at or below `convergence_threshold_paise` as
agreement (deal price = midpoint of the two offers, clamped into both
parties' feasible range). The Buyer Agent sets this threshold to 1% of list
price (`Settings.negotiation_convergence_fraction`). This bounds a real
negotiation to a handful of rounds without changing who-concedes-how-much.

## Stalemate: the no-deal case

If the buyer is pinned at its budget *and* the merchant is pinned at its
floor, and a gap still remains, further rounds cannot change anything --
`conceder = "stalemate"`, `deal = False`, negotiation ends immediately
rather than burning the remaining round budget. If the round cap
(`Settings.negotiation_max_rounds`) is hit without either crossing or a
formal stalemate, the round-cap tie-break below decides the outcome. Every
path is an explicit, structured result in `NegotiationOutcome` -- the Buyer
Agent never silently treats a failed negotiation as a purchase, and never
leaves the caller guessing which of these happened.

## Round-cap tie-break: a reachable deal shouldn't die on the clock

Neither of the two rules above is a "your offer wasn't good enough" check --
one is genuine convergence, the other is a genuine dead end. But there's a
third case those two don't cover: the negotiation was heading toward a real
deal the whole time (the buyer's budget was always above the merchant's
floor -- reservations overlap), concession size just decayed faster than
`convergence_threshold_paise` could catch, and `negotiation_max_rounds` ran
out one or two steps short. That's a round-budget miss, not a real
stalemate, and reporting it as "no deal" would be misleading -- the two
sides were, say, ₹10 apart on an ₹899 item, well within what either side
would accept in practice.

`run_zeuthen_negotiation`'s `close_threshold_paise` parameter
(`Settings.negotiation_close_threshold_paise`, default ₹150) exists for
exactly this. If `max_rounds` is reached and the final gap between the two
offers is at or below this threshold, round `max_rounds` settles at the
midpoint of the two final offers (clamped into both parties' feasible
range) -- `conceder = "round_cap_settlement"`, `deal = True`. If the gap is
still wider than that, the negotiation ends as an explicit
`conceder = "max_rounds_exceeded"`, `deal = False` -- a distinct, clearly
labeled "reached the round limit without agreement" result, never confused
with a stalemate or a lower-round rejection, and never a silent failure or
hang.

This is deterministic arithmetic, identical in kind to the mid-negotiation
convergence check -- no LLM call, no special-casing downstream. A price
settled this way is still just `deal_price_paise` on a normal
`RoundResult`, so it flows through the exact same path as any other agreed
price: the Buyer Agent hands it to the Merchant Agent, which runs it through
the full TrustGuard pipeline (spend cap, category, velocity, etc.) before
any payment happens. There is no bypass for a round-cap settlement -- it can
still be rejected or escalated like any other price if it fails a check.

## Division of labor: rules-first, LLM-as-fallback

Deterministic, no LLM call:
- Whether any catalog product matches the buyer's goal at all
  (`BuyerAgent._find_candidate_product` -- keyword match against
  name/description/category, filtered by a price ceiling).
- Whether the buyer can afford list price outright (skips negotiation
  entirely -- see "comfortable budget" scenario).
- Every number produced during negotiation: opening offers, each round's
  risk values, who concedes, concession size, whether offers have converged
  or deadlocked.
- Payment verification: the Merchant Agent checks the paid amount against
  the price the Zeuthen engine actually agreed to
  (`MerchantAgent.handle_request(..., agreed_price_paise=...)`), not
  whatever the buyer claims.

LLM call (Gemini, via the same `LLMClient` interface as Day 1's upsell
logic):
- Phrasing one round's buyer offer and merchant counter-offer as a natural
  sentence for the trace (`BuyerAgent._phrase`). The prompt hands the model
  the exact price in paise and instructs it not to invent a different one;
  if the call fails or returns something unusable, the trace falls back to
  a plain `"{speaker} offer: {price} paise (risk={risk})"` line -- a broken
  LLM call degrades the trace's readability, never the negotiation's
  correctness.
- Deciding *whether* to offer an upsell and which related product to
  propose (unchanged from Day 1, `MerchantAgent._maybe_build_upsell`) --
  discount percentage and product whitelist are still clamped in code
  regardless of what the model returns.

Every LLM call is wrapped in `LoggingLLMClient`
(`backend/app/llm/logging_client.py`), which records latency and an
estimated input/output token count (chars / 4 heuristic) and estimated cost
per call, logged against Gemini 2.0 Flash's paid-tier rate for illustrative
purposes -- actual calls in this project run on the free tier.

## What this does not model

- **Private information leakage**: the negotiation engine
  (`run_zeuthen_negotiation`) is handed both parties' reservation prices
  directly rather than each side inferring the other's from observed
  concessions alone. In a real distributed protocol each agent would only
  know its own utility function and the other's *offers*, exchanging risk
  values as part of the message protocol. Simulating that honestly (agents
  reasoning about an opponent's utility from behavior alone) is future
  work; today the engine is the shared "negotiation session," and the
  round-by-round trace renders it as an offer/counter-offer/risk exchange
  to match what that distributed protocol would look like on the wire.
- **Per-product merchant floors** -- see the utility functions section
  above.
- **Multi-item negotiation** -- an upsell is only ever offered/accepted at
  its fixed (code-bounded) discount, never itself negotiated.
