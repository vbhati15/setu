"""TrustGuard: the single choke point every purchase request passes through
before a charge is attempted. Runs, in order:

  1. Kill switch -- if active, everything is halted, no other check runs.
  2. Signature/credential verification -- unsigned, wrong-key, expired, or
     malformed requests are rejected outright (never processed further).
  3. Replay defense -- stale `issued_at` or a reused `nonce` for the same
     agent is rejected.
  4. Credential-scope check -- does this *specific agent's* credential
     permit this spend/category at all? A hard reject, not an escalation:
     the agent was never authorized to do this.
  5. Idempotency -- a previously-seen `idempotency_key` short-circuits
     straight to the stored result; no new charge is ever attempted.
  6. Velocity -- too many attempts in the window blocks/escalates until the
     window has room again.
  7. Daily spend -- cumulative spend across many individually-valid
     transactions in the trailing 24h, escalated if this transaction would
     push the agent's running total over `max_daily_spend_paise`.
  8. Policy engine -- platform-wide bounds (spend cap, category). Within
     bounds: approved. Outside: escalated with a specific reason, not
     silently dropped.

Every rejection is logged with agent id, rule, and reason.

`authorize_anonymous_purchase` runs the same steps minus signature/
credential/replay checks (2-4 above), for HTTP callers with no signed
identity -- see its docstring.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from backend.app.config import Settings
from backend.app.trust.identity import CredentialIssuer, SignedRequest, verify_signature
from backend.app.trust.daily_spend import DailySpendTracker
from backend.app.trust.idempotency import IdempotencyStore
from backend.app.trust.kill_switch import KillSwitch
from backend.app.trust.policy import PolicyDecision, PolicyEngine
from backend.app.trust.velocity import VelocityLimiter

logger = logging.getLogger("setu.trust")

# How long a signed request stays "fresh" -- outside this window from
# `issued_at` a request is rejected even with a perfectly valid signature,
# so a captured-and-replayed-later request eventually stops working.
DEFAULT_FRESHNESS_WINDOW_SECONDS = 300
# Bound how many nonces we remember per agent so this can't grow unbounded.
_MAX_NONCES_PER_AGENT = 10_000


@dataclass
class AuthorizationResult:
    approved: bool
    escalate: bool = False
    is_replay: bool = False
    cached_result: Any = None
    reason: str | None = None
    rule: str | None = None


class TrustGuard:
    def __init__(
        self,
        *,
        settings: Settings,
        issuer: CredentialIssuer | None = None,
        freshness_window_seconds: float = DEFAULT_FRESHNESS_WINDOW_SECONDS,
    ) -> None:
        self.settings = settings
        self.issuer = issuer or CredentialIssuer()
        self.kill_switch = KillSwitch()
        self.policy_engine = PolicyEngine(settings)
        self.idempotency_store = IdempotencyStore()
        self.velocity_limiter = VelocityLimiter(
            max_per_minute=settings.max_purchases_per_minute,
            max_per_hour=settings.max_purchases_per_hour,
        )
        self.daily_spend_tracker = DailySpendTracker()
        self.freshness_window_seconds = freshness_window_seconds
        self._seen_nonces: dict[str, set[str]] = {}

    # -- public API ---------------------------------------------------------

    def authorize_purchase(self, request: SignedRequest, *, category: str) -> AuthorizationResult:
        """Runs every trust check for a purchase of `payload["price_paise"]`
        paise in `category`. Does NOT itself charge anything or record
        velocity/idempotency on success -- callers that go on to actually
        run the purchase must call `record_attempt` / `store_result`."""
        if self.kill_switch.is_active:
            return self._reject(
                request.agent_id, "kill_switch",
                f"kill switch is active ({self.kill_switch.reason or 'no reason given'}); "
                "no new transactions are being processed",
            )

        ok, reason = self._verify_signature_and_credential(request)
        if not ok:
            return self._reject(request.agent_id, "signature", reason)

        ok, reason = self._check_freshness_and_replay(request)
        if not ok:
            return self._reject(request.agent_id, "replay", reason)

        price_paise = int(request.payload.get("price_paise", 0))
        ok, reason = self._check_credential_scope(request, price_paise=price_paise, category=category)
        if not ok:
            return self._reject(request.agent_id, "credential_scope", reason)

        return self._authorize_common(request.agent_id, request.idempotency_key, price_paise, category)

    def authorize_anonymous_purchase(
        self, *, agent_id: str, idempotency_key: str, price_paise: int, category: str
    ) -> AuthorizationResult:
        """For HTTP callers with no signed agent identity or credential --
        today, that's `GET /products/{id}`'s X-PAYMENT-verification leg,
        which any client (not just an onboarded Buyer Agent) can call.

        Runs every check that doesn't require a credential: kill switch,
        idempotency, velocity, daily spend, and policy bounds. Skips
        signature verification, replay-nonce tracking, and credential-scope
        checking, since there is no signed envelope or credential to check
        those against. `agent_id` here is a caller-derived bucket (e.g.
        client IP) for rate/spend accounting, not an onboarded agent's
        identity -- so this intentionally provides weaker guarantees than
        `authorize_purchase` (an unauthenticated caller can rotate IPs to
        dodge velocity/daily-spend accounting; `authorize_purchase`'s
        credential-scope check has no equivalent bypass). See
        `docs/THREAT_MODEL.md` for what this does and does not cover."""
        if self.kill_switch.is_active:
            return self._reject(
                agent_id, "kill_switch",
                f"kill switch is active ({self.kill_switch.reason or 'no reason given'}); "
                "no new transactions are being processed",
            )
        return self._authorize_common(agent_id, idempotency_key, price_paise, category)

    def record_attempt(self, agent_id: str) -> None:
        self.velocity_limiter.record(agent_id)

    def record_spend(self, agent_id: str, amount_paise: int) -> None:
        """Call only after a purchase actually completed -- a failed or
        rejected attempt never spent anything."""
        self.daily_spend_tracker.record(agent_id, amount_paise)

    def store_result(self, idempotency_key: str, result: Any) -> None:
        self.idempotency_store.store(idempotency_key, result)

    # -- internals ------------------------------------------------------------

    def _authorize_common(
        self, agent_id: str, idempotency_key: str, price_paise: int, category: str
    ) -> AuthorizationResult:
        """Checks shared by both authorization paths, once identity/scope
        (or the deliberate absence of it) has already been settled:
        idempotency, velocity, daily spend, policy bounds."""
        cached = self.idempotency_store.get(idempotency_key)
        if cached is not None:
            return AuthorizationResult(approved=True, is_replay=True, cached_result=cached.result)

        ok, reason = self.velocity_limiter.check(agent_id)
        if not ok:
            return self._reject(agent_id, "velocity", reason, escalate=True)

        ok, reason = self.daily_spend_tracker.check(agent_id, price_paise, self.settings.max_daily_spend_paise)
        if not ok:
            return self._reject(agent_id, "daily_spend", reason, escalate=True)

        decision = self.policy_engine.evaluate_purchase(price_paise=price_paise, category=category)
        if not decision.approved:
            logger.warning("purchase escalated: agent=%s rule=%s reason=%s", agent_id, decision.rule, decision.reason)
            return AuthorizationResult(
                approved=False, escalate=decision.escalate, reason=decision.reason, rule=decision.rule
            )

        return AuthorizationResult(approved=True)

    def _verify_signature_and_credential(self, request: SignedRequest) -> tuple[bool, str | None]:
        if not request.signature:
            return False, "request is unsigned"

        credential = request.credential
        issuer_ok, issuer_reason = self.issuer.verify(credential)
        if not issuer_ok:
            return False, f"invalid credential: {issuer_reason}"

        if credential.agent_id != request.agent_id:
            return False, "credential agent_id does not match request agent_id"

        request_ok = verify_signature(credential.public_key_b64, request.signing_payload(), request.signature)
        if not request_ok:
            return False, "request signature does not verify against the credential's public key"

        return True, None

    def _check_freshness_and_replay(self, request: SignedRequest) -> tuple[bool, str | None]:
        age = time.time() - request.issued_at
        if age > self.freshness_window_seconds or age < -30:
            return False, (
                f"request is stale or has a bad timestamp (issued_at={request.issued_at}, "
                f"{age:.0f}s from now; freshness window is {self.freshness_window_seconds}s)"
            )
        seen = self._seen_nonces.setdefault(request.agent_id, set())
        if request.nonce in seen:
            return False, f"nonce '{request.nonce}' has already been used by agent '{request.agent_id}' (replay)"
        if len(seen) >= _MAX_NONCES_PER_AGENT:
            seen.clear()
        seen.add(request.nonce)
        return True, None

    def _check_credential_scope(
        self, request: SignedRequest, *, price_paise: int, category: str
    ) -> tuple[bool, str | None]:
        credential = request.credential
        if price_paise > credential.max_spend_paise:
            return False, (
                f"requested amount {price_paise} paise exceeds this agent's credential "
                f"scope (max_spend_paise={credential.max_spend_paise})"
            )
        if category not in credential.allowed_categories:
            return False, (
                f"category '{category}' is outside this agent's credential scope "
                f"(allowed_categories={credential.allowed_categories})"
            )
        return True, None

    def _reject(self, agent_id: str, rule: str, reason: str, *, escalate: bool = False) -> AuthorizationResult:
        logger.warning("purchase rejected: agent=%s rule=%s reason=%s", agent_id, rule, reason)
        return AuthorizationResult(approved=False, escalate=escalate, reason=reason, rule=rule)
