"""checkout_quote.py: the signed token binding a human-triggered
negotiation's exact (product_id, agreed_price_paise) to the real Razorpay
order/confirm endpoints -- see docs/DECISIONS.md, 2026-09-05."""
import time

import pytest

from backend.app.checkout_quote import InvalidQuoteToken, build_quote_token, verify_quote_token


def test_round_trips_product_id_and_price():
    token = build_quote_token("wireless-mouse-ergo", 103_780)
    product_id, price_paise = verify_quote_token(token)
    assert product_id == "wireless-mouse-ergo"
    assert price_paise == 103_780


def test_tampered_price_is_rejected():
    token = build_quote_token("wireless-mouse-ergo", 103_780)
    body, _, signature = token.partition(".")
    # Flip the last character of the signed body -- simulates a client
    # trying to smuggle a different price through unmodified.
    tampered_body = body[:-1] + ("a" if body[-1] != "a" else "b")
    with pytest.raises(InvalidQuoteToken):
        verify_quote_token(f"{tampered_body}.{signature}")


def test_tampered_signature_is_rejected():
    token = build_quote_token("wireless-mouse-ergo", 103_780)
    body, _, signature = token.partition(".")
    with pytest.raises(InvalidQuoteToken):
        verify_quote_token(f"{body}.{'0' * len(signature)}")


def test_expired_token_is_rejected():
    token = build_quote_token("wireless-mouse-ergo", 103_780, ttl_seconds=-1)
    with pytest.raises(InvalidQuoteToken):
        verify_quote_token(token)


def test_malformed_token_is_rejected():
    with pytest.raises(InvalidQuoteToken):
        verify_quote_token("not-a-real-token")
    with pytest.raises(InvalidQuoteToken):
        verify_quote_token("")


def test_still_valid_just_inside_ttl():
    token = build_quote_token("cable-organizer-kit", 35_212, ttl_seconds=0.5)
    time.sleep(0.1)
    product_id, price_paise = verify_quote_token(token)
    assert product_id == "cable-organizer-kit"
    assert price_paise == 35_212
