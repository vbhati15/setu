"""Zeuthen bargaining strategy: deterministic, code-owned negotiation math.

No LLM involvement anywhere in this module. Agents (Buyer/Merchant) call this
to decide *how much* to concede each round; an LLM is only ever used
downstream to phrase that number as natural language. See BARGAINING.md for
the full writeup of the algorithm and why Zeuthen was chosen.

Core idea (Zeuthen 1930, monotonic concession protocol):
  - Each party has a utility function over price, normalized to [0, 1]:
    1.0 at its ideal price, 0.0 at its reservation (walk-away) price.
  - Each round, each party computes its "risk of conflict": how much utility
    it would sacrifice by conceding fully to the other side's current offer,
    relative to the utility of holding its own offer.
  - Whoever has LOWER risk concedes (they have less to lose by giving
    ground). Concession size is proportional to the *other* party's risk --
    a stubborn opponent (high risk) has to be met with a bigger concession
    to avoid a breakdown.
"""
from __future__ import annotations

from dataclasses import dataclass


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def buyer_utility(price_paise: int, budget_paise: int) -> float:
    """1.0 at price=0, 0.0 at price=budget (buyer's reservation point)."""
    if budget_paise <= 0:
        return 0.0
    return clamp01((budget_paise - price_paise) / budget_paise)


def merchant_utility(price_paise: int, min_price_paise: int, list_price_paise: int) -> float:
    """1.0 at list_price (merchant's ideal), 0.0 at min_price (reservation)."""
    span = list_price_paise - min_price_paise
    if span <= 0:
        return 1.0 if price_paise >= min_price_paise else 0.0
    return clamp01((price_paise - min_price_paise) / span)


def risk(own_utility_at_own_offer: float, own_utility_at_opponent_offer: float) -> float:
    """Fractional utility a party would lose by conceding fully to the
    opponent's current offer, relative to what it has now. risk=1 means
    "conceding costs everything I have" (never concede); risk=0 means
    "conceding costs nothing" (safe to concede)."""
    if own_utility_at_own_offer <= 0:
        return 1.0
    return clamp01((own_utility_at_own_offer - own_utility_at_opponent_offer) / own_utility_at_own_offer)


@dataclass(frozen=True)
class BuyerParty:
    budget_paise: int

    def utility(self, price_paise: int) -> float:
        return buyer_utility(price_paise, self.budget_paise)

    def risk(self, own_offer_paise: int, opponent_offer_paise: int) -> float:
        return risk(self.utility(own_offer_paise), self.utility(opponent_offer_paise))

    @property
    def reservation_paise(self) -> int:
        return self.budget_paise


@dataclass(frozen=True)
class MerchantParty:
    min_price_paise: int
    list_price_paise: int

    def utility(self, price_paise: int) -> float:
        return merchant_utility(price_paise, self.min_price_paise, self.list_price_paise)

    def risk(self, own_offer_paise: int, opponent_offer_paise: int) -> float:
        return risk(self.utility(own_offer_paise), self.utility(opponent_offer_paise))

    @property
    def reservation_paise(self) -> int:
        return self.min_price_paise


@dataclass(frozen=True)
class RoundResult:
    round_number: int
    buyer_offer_paise: int
    merchant_offer_paise: int
    buyer_risk: float
    merchant_risk: float
    conceder: str  # "buyer" | "merchant" | "agreement" | "stalemate" | "round_cap_settlement" | "max_rounds_exceeded"
    deal: bool
    deal_price_paise: int | None
    stalemate: bool


def run_zeuthen_negotiation(
    buyer: BuyerParty,
    merchant: MerchantParty,
    opening_buyer_offer_paise: int,
    opening_merchant_offer_paise: int,
    max_rounds: int,
    min_concession_fraction: float,
    max_concession_fraction: float = 1.0,
    convergence_threshold_paise: int = 0,
    close_threshold_paise: int = 0,
) -> list[RoundResult]:
    """Runs the Zeuthen concession protocol to convergence, stalemate, or
    round exhaustion. Returns the full round-by-round trace -- never raises
    for a failed negotiation, that's a normal outcome (last round's
    `deal=False`).

    `convergence_threshold_paise` treats a sufficiently small remaining gap
    (not just an exact crossing) as agreement -- concession decay is
    asymptotic, so without this a negotiation between two rational,
    risk-averse parties could burn many rounds closing the last few paise of
    a gap neither side actually cares about.

    `close_threshold_paise` is the same idea applied once more, only at the
    round cap itself: concession decay can still leave a small, immaterial
    gap open when `max_rounds` runs out, which without this would report a
    false "no deal" on a negotiation that was genuinely reachable. If the
    final gap is within this threshold, round `max_rounds` settles at the
    midpoint (`conceder="round_cap_settlement"`) instead of failing
    (`conceder="max_rounds_exceeded"`). This is deterministic arithmetic,
    identical in kind to the mid-negotiation convergence check above -- no
    LLM involvement, no bypass of anything downstream. See BARGAINING.md."""
    rounds: list[RoundResult] = []
    buyer_offer = opening_buyer_offer_paise
    merchant_offer = opening_merchant_offer_paise

    for round_number in range(1, max_rounds + 1):
        if merchant_offer - buyer_offer <= convergence_threshold_paise:
            midpoint = round((buyer_offer + merchant_offer) / 2)
            # Clamp into both parties' feasible range -- the midpoint of two
            # offers within `convergence_threshold_paise` of each other can
            # still fall a few paise outside one side's reservation price.
            deal_price = min(buyer.reservation_paise, max(merchant.reservation_paise, midpoint))
            rounds.append(
                RoundResult(
                    round_number=round_number,
                    buyer_offer_paise=buyer_offer,
                    merchant_offer_paise=merchant_offer,
                    buyer_risk=0.0,
                    merchant_risk=0.0,
                    conceder="agreement",
                    deal=True,
                    deal_price_paise=deal_price,
                    stalemate=False,
                )
            )
            return rounds

        risk_b = buyer.risk(buyer_offer, merchant_offer)
        risk_m = merchant.risk(merchant_offer, buyer_offer)

        buyer_maxed = buyer_offer >= buyer.reservation_paise
        merchant_floored = merchant_offer <= merchant.reservation_paise

        if buyer_maxed and merchant_floored:
            rounds.append(
                RoundResult(
                    round_number=round_number,
                    buyer_offer_paise=buyer_offer,
                    merchant_offer_paise=merchant_offer,
                    buyer_risk=risk_b,
                    merchant_risk=risk_m,
                    conceder="stalemate",
                    deal=False,
                    deal_price_paise=None,
                    stalemate=True,
                )
            )
            return rounds

        # Lower risk concedes; fall back to the other party if the
        # risk-preferred conceder is already pinned at its reservation price.
        conceder = "buyer" if risk_b <= risk_m else "merchant"
        if conceder == "buyer" and buyer_maxed:
            conceder = "merchant"
        elif conceder == "merchant" and merchant_floored:
            conceder = "buyer"

        if conceder == "buyer":
            step = min(max(risk_m, min_concession_fraction), max_concession_fraction)
            buyer_offer = min(buyer.reservation_paise, round(buyer_offer + step * (merchant_offer - buyer_offer)))
        else:
            step = min(max(risk_b, min_concession_fraction), max_concession_fraction)
            merchant_offer = max(
                merchant.reservation_paise, round(merchant_offer - step * (merchant_offer - buyer_offer))
            )

        rounds.append(
            RoundResult(
                round_number=round_number,
                buyer_offer_paise=buyer_offer,
                merchant_offer_paise=merchant_offer,
                buyer_risk=risk_b,
                merchant_risk=risk_m,
                conceder=conceder,
                deal=False,
                deal_price_paise=None,
                stalemate=False,
            )
        )

    if merchant_offer - buyer_offer <= close_threshold_paise:
        midpoint = round((buyer_offer + merchant_offer) / 2)
        # Same clamp as the mid-negotiation convergence branch -- the
        # midpoint of two offers within `close_threshold_paise` of each
        # other can still fall a few paise outside one side's reservation.
        deal_price = min(buyer.reservation_paise, max(merchant.reservation_paise, midpoint))
        rounds.append(
            RoundResult(
                round_number=max_rounds,
                buyer_offer_paise=buyer_offer,
                merchant_offer_paise=merchant_offer,
                buyer_risk=0.0,
                merchant_risk=0.0,
                conceder="round_cap_settlement",
                deal=True,
                deal_price_paise=deal_price,
                stalemate=False,
            )
        )
    else:
        rounds.append(
            RoundResult(
                round_number=max_rounds,
                buyer_offer_paise=buyer_offer,
                merchant_offer_paise=merchant_offer,
                buyer_risk=buyer.risk(buyer_offer, merchant_offer),
                merchant_risk=merchant.risk(merchant_offer, buyer_offer),
                conceder="max_rounds_exceeded",
                deal=False,
                deal_price_paise=None,
                stalemate=False,
            )
        )
    return rounds
