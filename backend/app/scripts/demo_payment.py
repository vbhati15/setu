"""End-to-end Razorpay test-mode payment demo.

Creates a real order via the Orders API, then opens Razorpay's actual
hosted Checkout widget in a visible browser window and waits for you to
complete it with Razorpay's official test card. This is a semi-automated
demo, not a headless one, by deliberate choice:

  - The S2S UPI Collect API (server-only completion) requires Razorpay
    Support to enable VPA validation per-account, and is deprecated for new
    integrations as of Feb 2026.
  - Driving the real Checkout widget with a *headless* browser gets stuck
    behind Razorpay's PerimeterX/HUMAN Security bot detection (the "Sending
    OTP" step never completes) — and deliberately engineering around a
    payment provider's fraud detection isn't something this script should
    do, test mode or not.

So: real order, real Checkout widget, one manual click-through. Still a
fully real Razorpay test-mode payment end to end. See docs/DECISIONS.md.

Test card: 4100 2800 0000 1007, any future expiry, any CVV, any 4-10 digit
OTP when prompted (Razorpay test-mode convention: OTP length 4-10 succeeds,
below 4 digits deliberately fails).

Run with: make demo
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.config import get_settings
from app.razorpay_client import RazorpayClient

DEMO_PRODUCT_NAME = "Mechanical Keyboard - Hot-swap, 65%"
DEMO_AMOUNT_PAISE = 349_900  # INR 3,499.00

TEST_CARD_NUMBER = "4100 2800 0000 1007"

TEMPLATE_PATH = Path(__file__).parent / "checkout_template.html"
MANUAL_STEP_TIMEOUT_SECONDS = 180


def _render_checkout_html(*, key_id: str, order_id: str, amount_paise: int, description: str) -> Path:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        html.replace("__KEY_ID__", key_id)
        .replace("__ORDER_ID__", order_id)
        .replace("__AMOUNT_PAISE__", str(amount_paise))
        .replace("__DESCRIPTION__", description)
    )
    tmp = Path(tempfile.gettempdir()) / f"setu-checkout-{order_id}.html"
    tmp.write_text(html, encoding="utf-8")
    return tmp


def _complete_checkout_manually(html_path: Path) -> dict:
    """Opens the real Razorpay Checkout in a visible browser window and
    waits for the buyer to complete it by hand. Returns the
    {razorpay_payment_id, razorpay_order_id, razorpay_signature} the
    widget's own success handler receives."""
    print()
    print(f"      A browser window is opening. Complete the payment with:")
    print(f"        Card number : {TEST_CARD_NUMBER}")
    print(f"        Expiry      : any future date (e.g. 12/35)")
    print(f"        CVV         : any 3 digits")
    print(f"        OTP         : any 4-10 digit number, when prompted")
    print(f"      Waiting up to {MANUAL_STEP_TIMEOUT_SECONDS}s for you to finish...")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(html_path.as_uri())

        result_el = page.locator("#result")
        deadline = time.monotonic() + MANUAL_STEP_TIMEOUT_SECONDS
        status = None
        while time.monotonic() < deadline:
            status = result_el.get_attribute("data-status")
            if status is not None:
                break
            time.sleep(1)

        if status is None:
            browser.close()
            raise RuntimeError(f"no payment result within {MANUAL_STEP_TIMEOUT_SECONDS}s (window closed or timed out)")

        text = result_el.inner_text()
        browser.close()

        if status != "success":
            raise RuntimeError(f"checkout did not succeed (status={status}): {text}")

        return json.loads(text)


def run_demo() -> int:
    settings = get_settings()
    client = RazorpayClient(settings)

    print(f"[1/3] Creating Razorpay test-mode order for '{DEMO_PRODUCT_NAME}'...")
    order = client.create_order(
        amount_paise=DEMO_AMOUNT_PAISE,
        receipt="setu-demo-order",
        notes={"product": DEMO_PRODUCT_NAME},
    )
    order_id = order["id"]
    print(f"      order_id = {order_id}")

    print("[2/3] Completing payment via real Razorpay Checkout...")
    html_path = _render_checkout_html(
        key_id=settings.razorpay_key_id,
        order_id=order_id,
        amount_paise=DEMO_AMOUNT_PAISE,
        description=DEMO_PRODUCT_NAME,
    )
    try:
        checkout_result = _complete_checkout_manually(html_path)
    except Exception as exc:
        print(f"      FAILED: {exc}", file=sys.stderr)
        return 1

    payment_id = checkout_result["razorpay_payment_id"]
    print(f"      payment_id = {payment_id}")

    signature_ok = client.verify_payment_signature(
        {
            "razorpay_order_id": checkout_result["razorpay_order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": checkout_result["razorpay_signature"],
        }
    )
    if not signature_ok:
        print("      FAILED: payment signature verification failed", file=sys.stderr)
        return 1

    print("[3/3] Confirming payment status via Razorpay API...")
    payment = client.fetch_payment(payment_id)
    status = payment.get("status")
    print(f"      status = {status}")

    print()
    if status in ("captured", "authorized"):
        print(f"SUCCESS. Transaction ID: {payment_id} (status={status})")
        return 0
    print(f"Payment did not settle as expected (status={status}).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(run_demo())
