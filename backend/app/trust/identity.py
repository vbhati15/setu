"""Signed agent identity: Ed25519 keypairs, scoped/expiring credentials, and
signed request envelopes.

Trust model:
  - Each agent (Buyer, Merchant) holds its own Ed25519 keypair
    (`AgentIdentity`). The private key never leaves the agent.
  - A `CredentialIssuer` (the Setu platform -- in this codebase, the
    Merchant Agent's own issuer keypair, since it is the trust root for its
    own marketplace) issues each agent a `AgentCredential`: a signed
    statement of who the agent is, what it's allowed to spend, what
    categories it may buy in, and when that permission expires. This is
    authorization scope, not just identity -- a valid signature alone does
    not mean "allowed to do anything."
  - Every purchase request an agent sends is wrapped in a `SignedRequest`:
    the payload plus a signature made with the agent's own private key.
    The receiving side verifies both the credential (issued by a trusted
    issuer, not expired) and the request signature (matches the public key
    named in that credential) before doing anything else.

Replay defense: a `SignedRequest` carries `issued_at` (checked against a
freshness window by the caller) and a random `nonce` -- `TrustGuard` tracks
recently-seen nonces per agent so a captured, still-fresh request cannot be
replayed verbatim.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class AgentIdentity:
    """An agent's own Ed25519 keypair. `agent_id` is a human-readable label,
    not itself a security boundary -- the public key is."""

    agent_id: str
    _private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls, agent_id: str) -> "AgentIdentity":
        return cls(agent_id=agent_id, _private_key=Ed25519PrivateKey.generate())

    @property
    def public_key_b64(self) -> str:
        raw = self._private_key.public_key().public_bytes_raw()
        return _b64(raw)

    def sign(self, payload: dict) -> str:
        signature = self._private_key.sign(_canonical(payload))
        return _b64(signature)


def verify_signature(public_key_b64: str, payload: dict, signature_b64: str) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(_unb64(public_key_b64))
        public_key.verify(_unb64(signature_b64), _canonical(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


class AgentCredential(BaseModel):
    """Scoped, expiring authorization for one agent, signed by a trusted
    issuer. Presenting a valid signature over a request proves the sender
    holds the private key matching `public_key_b64`; this credential is
    what says that key is *allowed* to spend up to `max_spend_paise` in
    `allowed_categories` until `expires_at`."""

    agent_id: str
    public_key_b64: str
    max_spend_paise: int
    allowed_categories: list[str]
    issued_at: float
    expires_at: float
    issuer_signature: str = ""

    def signing_payload(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "public_key_b64": self.public_key_b64,
            "max_spend_paise": self.max_spend_paise,
            "allowed_categories": sorted(self.allowed_categories),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class CredentialIssuer:
    """The trust root that issues and verifies agent credentials. In this
    codebase the Merchant Agent owns one issuer keypair and issues
    credentials to Buyer Agents it onboards -- a hackathon-scale stand-in
    for a real platform-level certificate authority."""

    def __init__(self, issuer_id: str = "setu-platform") -> None:
        self.issuer_id = issuer_id
        self._private_key = Ed25519PrivateKey.generate()

    @property
    def public_key_b64(self) -> str:
        return _b64(self._private_key.public_key().public_bytes_raw())

    def issue(
        self,
        *,
        agent_id: str,
        public_key_b64: str,
        max_spend_paise: int,
        allowed_categories: list[str],
        ttl_seconds: float,
    ) -> AgentCredential:
        now = time.time()
        credential = AgentCredential(
            agent_id=agent_id,
            public_key_b64=public_key_b64,
            max_spend_paise=max_spend_paise,
            allowed_categories=allowed_categories,
            issued_at=now,
            expires_at=now + ttl_seconds,
        )
        signature = self._private_key.sign(_canonical(credential.signing_payload()))
        credential.issuer_signature = _b64(signature)
        return credential

    def verify(self, credential: AgentCredential) -> tuple[bool, str | None]:
        if credential.is_expired:
            return False, "credential has expired"
        ok = verify_signature(self.public_key_b64, credential.signing_payload(), credential.issuer_signature)
        if not ok:
            return False, "credential issuer signature is invalid"
        return True, None


class SignedRequest(BaseModel):
    """A purchase/negotiation request from one agent to another, signed by
    the sending agent's private key. `payload` carries the actual request
    (product id, price, action); `idempotency_key` and `nonce` are outside
    the payload but still covered by the signature, so neither can be
    stripped or swapped by a man-in-the-middle without invalidating it."""

    agent_id: str
    credential: AgentCredential
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex)
    issued_at: float = Field(default_factory=time.time)
    idempotency_key: str
    payload: dict
    signature: str = ""

    def signing_payload(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
        }


def build_signed_request(
    identity: AgentIdentity,
    credential: AgentCredential,
    payload: dict,
    idempotency_key: str,
) -> SignedRequest:
    request = SignedRequest(
        agent_id=identity.agent_id,
        credential=credential,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    request.signature = identity.sign(request.signing_payload())
    return request
