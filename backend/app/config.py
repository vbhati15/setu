"""Central, config-driven settings for Setu.

Nothing in the agent/payment/protocol code should hardcode spend limits,
allowed categories, discount caps, or credentials — it all comes from here,
which in turn comes from the environment (.env in dev, real env vars in
deployment).
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    TEST = "test"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # --- Mode ---
    setu_env: Environment = Environment.TEST

    # --- Razorpay ---
    razorpay_key_id: str = "rzp_test_placeholder"
    razorpay_key_secret: str = "placeholder_secret"

    # --- Gemini ---
    gemini_api_key: str = "placeholder_gemini_key"
    gemini_model: str = "gemini-2.0-flash"

    # --- Database ---
    database_url: str = "postgresql://setu:setu@localhost:5432/setu"

    # --- Merchant identity ---
    merchant_id: str = "setu_merchant_test"

    # --- CORS: origins allowed to call this API from a browser ---
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "https://setu-alpha-beige.vercel.app",
        ]
    )

    # --- Policy: spend limits (in paise, i.e. INR * 100) ---
    max_single_transaction_paise: int = 500_000  # INR 5,000 per transaction
    max_daily_spend_paise: int = 2_000_000  # INR 20,000 per day (aggregate, future use)

    # --- Policy: catalog / category allowlist ---
    allowed_categories: list[str] = Field(
        default_factory=lambda: [
            "peripherals",
            "accessories",
            "displays",
        ]
    )

    # --- Policy: velocity (rate limiting agent purchase attempts; future use) ---
    max_purchases_per_minute: int = 5
    max_purchases_per_hour: int = 30

    # --- Policy: bounded upsell ---
    max_upsell_discount_percent: int = 15  # hard cap enforced in code, not just prompted

    @property
    def is_live(self) -> bool:
        return self.setu_env is Environment.LIVE

    @field_validator("razorpay_key_id")
    @classmethod
    def _warn_live_key_in_test_mode(cls, v: str, info) -> str:
        # Structural guardrail: a live Razorpay key should never be usable while
        # setu_env=test. We don't have setu_env yet at this point in validation
        # order for a single field, so the real enforcement lives in
        # Settings.model_post_init below.
        return v

    def model_post_init(self, __context) -> None:
        if self.setu_env is Environment.TEST and self.razorpay_key_id.startswith("rzp_live_"):
            raise ValueError(
                "Refusing to start: SETU_ENV=test but RAZORPAY_KEY_ID looks like a live key. "
                "Use a rzp_test_ key in test mode."
            )
        if self.setu_env is Environment.LIVE:
            raise ValueError(
                "SETU_ENV=live is not yet supported by this codebase. "
                "Live-mode wiring is structural only (see config.py) and intentionally blocked."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
