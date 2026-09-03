"""Policy/gating engine: checks a proposed transaction against config-driven
bounds (spend cap, allowed category, discount/upsell bounds).

Within bounds -> auto-approved. Outside bounds -> escalated, with a specific,
human-readable reason -- never silently dropped. This is deliberately
separate from credential-scope enforcement (`TrustGuard`): a credential
violation means "this agent was never allowed to do this at all" (hard
reject); a policy violation means "this is outside the platform's normal
operating bounds" (escalate for review, since it may still be legitimate).
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.config import Settings


@dataclass
class PolicyDecision:
    approved: bool
    escalate: bool
    reason: str | None = None
    rule: str | None = None

    @classmethod
    def ok(cls) -> "PolicyDecision":
        return cls(approved=True, escalate=False)

    @classmethod
    def escalated(cls, rule: str, reason: str) -> "PolicyDecision":
        return cls(approved=False, escalate=True, reason=reason, rule=rule)


class PolicyEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate_purchase(self, *, price_paise: int, category: str) -> PolicyDecision:
        """Runs every bounds rule and returns the first violation, or an
        approval if all rules pass."""
        for rule in (self._check_spend_cap, self._check_category):
            decision = rule(price_paise=price_paise, category=category)
            if not decision.approved:
                return decision
        return PolicyDecision.ok()

    def _check_spend_cap(self, *, price_paise: int, category: str) -> PolicyDecision:
        cap = self.settings.max_single_transaction_paise
        if price_paise > cap:
            return PolicyDecision.escalated(
                rule="spend_cap",
                reason=(
                    f"transaction amount {price_paise} paise exceeds the platform's "
                    f"max_single_transaction_paise cap of {cap} paise"
                ),
            )
        return PolicyDecision.ok()

    def _check_category(self, *, price_paise: int, category: str) -> PolicyDecision:
        if category not in self.settings.allowed_categories:
            return PolicyDecision.escalated(
                rule="category",
                reason=(
                    f"category '{category}' is not in the platform's allowed_categories "
                    f"{self.settings.allowed_categories}"
                ),
            )
        return PolicyDecision.ok()

    def evaluate_discount(self, *, discount_percent: int) -> PolicyDecision:
        cap = self.settings.max_upsell_discount_percent
        if discount_percent > cap:
            return PolicyDecision.escalated(
                rule="discount_bounds",
                reason=(
                    f"discount {discount_percent}% exceeds the platform's "
                    f"max_upsell_discount_percent cap of {cap}%"
                ),
            )
        return PolicyDecision.ok()
