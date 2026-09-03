# PROTOCOL.md — x402 subset implemented in Setu

## Status: Day 1 (Merchant Agent side) + Day 2 (Buyer Agent negotiates a
price via Zeuthen bargaining before closing the x402 cycle below — see
`docs/BARGAINING.md`)

## Why a subset

The real [x402 protocol](https://www.x402.org/) is crypto-native: the
`X-PAYMENT` header carries a signed EIP-3009 `transferWithAuthorization`
payload for the `"exact"` scheme, settled on an EVM network by a
*facilitator* service that verifies and broadcasts the transfer.

Setu settles in **INR via Razorpay test-mode**, not on-chain. There is no
wallet, no signed transfer, and no facilitator in the crypto sense. Rather
than force a crypto abstraction onto a fiat rail (or bolt on a fake
"facilitator" that just wraps Razorpay calls for no reason), Setu keeps the
x402 **shape** — the 402 challenge/response cycle, the header names, the
retry pattern — and defines one custom scheme, `razorpay-inr`, whose payload
is a Razorpay order/payment reference instead of a signed transfer. The
Merchant Agent verifies it directly against the Razorpay API in place of a
facilitator's verify/settle split.

This was a deliberate, confirmed simplification (see BUILD_LOG.md, Day 1) —
not an oversight. If a literal on-chain x402 integration becomes valuable
later, the `scheme`/`network` fields and `RazorpayPaymentPayload` model are
the only places that would need to grow a second variant.

## What's implemented today

### 1. Challenge: `GET /products/{product_id}` with no payment

Merchant responds `402 Payment Required` with a JSON body:

```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "razorpay-inr",
      "network": "razorpay-test",
      "resource": "/products/mechanical-keyboard-65",
      "description": "Hot-swappable 65% mechanical keyboard.",
      "mimeType": "application/json",
      "maxAmountRequired": "349900",
      "asset": "INR",
      "payTo": "setu_merchant_test",
      "extra": { "category": "peripherals" }
    }
  ],
  "upsell": {
    "productId": "keycap-set-pbt-129",
    "name": "Keycap Set — PBT, 129 keys",
    "originalPricePaise": 89900,
    "discountedPricePaise": 76415,
    "discountPercent": 15,
    "reason": "Pairs with the keyboard for a full hot-swap setup."
  }
}
```

- `maxAmountRequired` is in paise (INR's atomic unit), as a string — mirrors
  x402's atomic-unit convention for `maxAmountRequired`.
- `upsell` is a Setu-specific extension, not part of core x402. It is
  optional, may be `null`, and is always code-bounded (see below) even
  though an LLM proposes it.

### 2. Retry: `X-PAYMENT` header

Client retries the same request with header:

```
X-PAYMENT: base64(JSON)
```

where the JSON is:

```json
{
  "x402Version": 1,
  "scheme": "razorpay-inr",
  "network": "razorpay-test",
  "resource": "/products/mechanical-keyboard-65",
  "payload": {
    "orderId": "order_...",
    "paymentId": "pay_...",
    "signature": "..."
  }
}
```

`orderId`/`paymentId`/`signature` are exactly what Razorpay's Checkout
returns to the client on successful payment (`razorpay_order_id`,
`razorpay_payment_id`, `razorpay_signature`) — the buyer side is expected to
have already completed a real Razorpay order+payment before constructing
this header.

### 3. Settlement: verification + response

The Merchant Agent (`backend/app/merchant_agent/agent.py`):

1. Decodes and schema-validates the header (untrusted input — rejects
   oversized, non-base64, non-JSON, or schema-invalid headers before doing
   anything else).
2. Checks the `resource` in the header matches the product being requested
   (prevents paying for product A and replaying the receipt against product
   B).
3. Fetches the payment from Razorpay by `payment_id` and checks:
   - `order_id` matches,
   - `amount` matches exactly — either the catalog list price, or (Day 2) a
     prior negotiated price when the request follows a completed Zeuthen
     negotiation (`handle_request(..., agreed_price_paise=...)`; see
     "Where negotiation fits" below and `docs/BARGAINING.md`),
   - `status` is `captured` or `authorized`,
   - the signature verifies via Razorpay's HMAC utility.
4. On success: `200 OK` with the resource body and an `X-PAYMENT-RESPONSE`
   header (`base64(JSON)` of `{success, transaction, payer, network}`).
5. On any failure: `402` again, with an `error` field explaining why —
   never a silent 4xx/5xx, so a Buyer Agent can inspect and react.

### 4. Bounded upsell

The Merchant Agent may attach one upsell offer to a 402 response. Gemini
picks *whether* to offer one and *which* related product, but:

- It only ever sees the requesting product plus the catalog's own
  `related()` list (curated `related_ids` pairings where set, e.g. a
  monitor paired with a monitor arm across categories; same-category
  fallback otherwise — all already validated on load) — it cannot invent a
  product.
- Its chosen `product_id` is checked against that same whitelist before use;
  anything else is discarded server-side.
- `discount_percent` is clamped to `settings.max_upsell_discount_percent`
  regardless of what the model returns.
- Any LLM failure (bad JSON, API error, timeout) results in `upsell: null`
  — it never blocks or breaks the core payment flow.

## Where negotiation fits (Day 2)

Zeuthen bargaining is not a variant of the x402 cycle itself — it runs
*before* it, as an in-process exchange between the Buyer Agent and the
Merchant Agent's `negotiation_party()` (see `docs/BARGAINING.md` for the
algorithm). The x402 challenge/response cycle above is only ever run twice
per purchase:

1. An unpaid `GET /products/{id}` up front, purely to read the catalog list
   price (and any upsell) — this is what tells the Buyer Agent whether it
   can afford list price outright or needs to negotiate.
2. The real payment retry, once a price is settled — either list price
   (comfortable budget) or the Zeuthen-agreed price (tight budget) — with
   the `X-PAYMENT` header carrying a payment made for that exact amount.
   `MerchantAgent.handle_request` is told the agreed price via
   `agreed_price_paise` (never taken from the buyer's claim) and verifies
   the payment against it instead of catalog list price.

Each negotiation round is not its own 402/200 round-trip; there is no
"counter-offer" x402 message type. Only the final agreed price ever touches
the payment-verification path above.

## What's deliberately NOT implemented today

- **Multiple schemes/networks** — only `razorpay-inr` / `razorpay-test`
  exist; the literal crypto `exact` scheme is not implemented.
- **Facilitator service** — verification is inline in the Merchant Agent,
  not a separate verify/settle microservice.
- **Replay/idempotency store** — a given `payment_id` is not yet recorded as
  "already spent" across requests, so (in principle) the same successful
  receipt could be replayed against the same resource more than once. This
  is a known gap for the trust/policy layer (Day 3), not a Day 1 claim of
  completeness.
- **Live mode** — `SETU_ENV=live` is structurally rejected in
  `backend/app/config.py`; only test-mode is wired up.
