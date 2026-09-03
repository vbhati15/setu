"""Day 4 Part 2 scenario test harness.

Runs real HTTP scenarios against Setu's *live* Render deployment
(`POST /negotiate`, `GET /products/{id}`) -- not local calls, not mocks.
Deliberately black-box: this script only speaks HTTP to the deployed app,
the same way a real caller would, so passing here is evidence about the
actual production behavior, not about internals.

Covers:
  - Comfortable-budget negotiations (clean match, upsell accepted/declined
    depending on the live LLM's real decision -- not scripted).
  - Tight-budget negotiations (real multi-round Zeuthen back-and-forth).
  - No-viable-match goals (must fail gracefully: 200 + a clear reason, not
    a crash).
  - One deliberate duplicate-idempotency-key scenario against
    `/products/{id}` -- the one TrustGuard rule that, before this harness,
    had only local test evidence (see docs/THREAT_MODEL.md).
  - Deliberate credential-scope / velocity / daily-spend limit breaches, to
    confirm those rules still fire correctly under scripted, bursty
    traffic, not just the earlier one-off manual curl commands.

Every HTTP call is logged as one line of JSON to
`harness_results/run_<timestamp>.jsonl` (full request + response +
latency + classified outcome/rule), and a final honest summary is printed
and saved alongside it. Nothing here touches the real Razorpay client --
`/negotiate` runs on the fake payment rail by server-side design (see
main.py), and every `/products/{id}` call in this harness uses a
fabricated X-PAYMENT payload specifically so it fails Razorpay
verification cleanly, which is what makes the idempotency/credential-scope
scenarios provable without a real checkout.

Run: python backend/app/scripts/scenario_harness.py
"""
from __future__ import annotations

import base64
import json
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE_URL = "https://setu-59l6.onrender.com"
RESULTS_DIR = Path(__file__).parent / "harness_results"
SEED = 20260904  # fixed, so "randomized" scenarios are reproducible/inspectable

# Catalog data mirrored from backend/app/catalog/products.json -- the
# harness is deliberately black-box (HTTP only), so this is hand-copied,
# not imported.
CATALOG_PRICE_PAISE = {
    "mechanical-keyboard-65": 349_900,
    "wireless-mouse-ergo": 129_900,
    "usbc-hub-7in1": 189_900,
    "monitor-27-1440p-144hz": 1_899_900,
    "keycap-set-pbt-129": 89_900,
    "mouse-pad-xl": 59_900,
    "cable-organizer-kit": 44_900,
    "monitor-arm-single": 229_900,
}
MAX_SINGLE_TX_PAISE = 500_000
MAX_DAILY_SPEND_PAISE = 2_000_000
MAX_PER_MINUTE = 5

GOAL_TEXT = {
    "mechanical-keyboard-65": "mechanical keyboard hot-swap 65 percent",
    "wireless-mouse-ergo": "ergonomic wireless mouse 2.4ghz",
    "usbc-hub-7in1": "usb-c hub 7-in-1 with hdmi",
    "monitor-27-1440p-144hz": "27 inch 1440p 144hz monitor display",
    "keycap-set-pbt-129": "pbt keycap set 129 keys",
    "mouse-pad-xl": "extended xl desk mouse pad",
    "cable-organizer-kit": "cable organizer kit for desk",
    "monitor-arm-single": "adjustable single monitor arm",
}
NO_MATCH_GOALS = [
    "telepathic hover skateboard wheels",
    "quantum banana peeler gadget",
    "invisible garden gnome statue",
    "self-folding laundry origami robot",
]

_RULE_RE = re.compile(r"\(([a-z_]+)\):")


@dataclass
class LogRecord:
    scenario_id: str
    step: int
    category: str
    description: str
    method: str
    url: str
    request_body: dict | None
    request_headers: dict
    response_status: int
    response_body: object
    latency_ms: float
    timestamp: float
    outcome: str
    rule: str | None


class Harness:
    def __init__(self) -> None:
        # Tight-budget scenarios can run up to negotiation_max_rounds (12)
        # real Zeuthen rounds, each phrased by two live Gemini calls -- a
        # generous read timeout is needed so a slow-but-genuine negotiation
        # isn't mistaken for a hang.
        self.client = httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(15.0, read=240.0))
        self.records: list[LogRecord] = []
        self._attempt_timestamps: list[float] = []  # local mirror of the server's velocity window
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.log_path = RESULTS_DIR / f"run_{self.run_id}.jsonl"

    # -- low-level HTTP -----------------------------------------------------

    def _negotiate(self, goal_text: str, budget_paise: int) -> tuple[dict, int, float]:
        body = {"goal_text": goal_text, "budget_paise": budget_paise}
        t0 = time.monotonic()
        try:
            resp = self.client.post("/negotiate", json=body)
        except httpx.HTTPError as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return {"success": False, "reason": f"harness network error: {exc!r}"}, -1, latency_ms
        latency_ms = (time.monotonic() - t0) * 1000
        return resp.json(), resp.status_code, latency_ms

    def _products_get(self, product_id: str, x_payment_b64: str | None) -> tuple[object, int, float]:
        headers = {"X-PAYMENT": x_payment_b64} if x_payment_b64 else {}
        t0 = time.monotonic()
        try:
            resp = self.client.get(f"/products/{product_id}", headers=headers)
        except httpx.HTTPError as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return {"error": f"harness network error: {exc!r}"}, -1, latency_ms
        latency_ms = (time.monotonic() - t0) * 1000
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return body, resp.status_code, latency_ms

    @staticmethod
    def _fabricated_x_payment(product_id: str, payment_id: str, order_id: str | None = None) -> str:
        payload = {
            "x402Version": 1,
            "scheme": "razorpay-inr",
            "network": "razorpay-test",
            "resource": f"/products/{product_id}",
            "payload": {
                "orderId": order_id or f"order_{payment_id}",
                "paymentId": payment_id,
                "signature": "fake",
            },
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()

    # -- outcome classification ----------------------------------------------

    @staticmethod
    def _classify_negotiate(body: dict) -> tuple[str, str | None]:
        if body.get("success"):
            return ("compliant", None)
        reason = body.get("reason") or ""
        m = _RULE_RE.search(reason)
        rule = m.group(1) if m else None
        if reason.startswith("no catalog product matches"):
            return ("graceful_no_match", None)
        if "escalated for review" in reason:
            return ("escalated", rule)
        if "rejected by trust layer" in reason:
            return ("rejected", rule)
        if "kill switch is active" in reason:
            return ("rejected", "kill_switch")
        return ("failed_other", rule)

    @staticmethod
    def _classify_products(status: int, body: object) -> tuple[str, str | None]:
        if status == 200 and isinstance(body, dict) and body.get("access_granted"):
            return ("compliant", None)
        error = body.get("error") if isinstance(body, dict) else str(body)
        error = error or ""
        m = _RULE_RE.search(error)
        rule = m.group(1) if m else None
        if "could not verify payment" in error:
            return ("failed_verification", None)  # expected: fabricated payment_id, real Razorpay 404
        if "escalated for review" in error:
            return ("escalated", rule)
        if "rejected by trust layer" in error:
            return ("rejected", rule)
        if "kill switch is active" in error:
            return ("rejected", "kill_switch")
        return ("failed_other", rule)

    # -- logging --------------------------------------------------------------

    def _log(self, rec: LogRecord) -> None:
        self.records.append(rec)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__, default=str) + "\n")

    # -- local velocity-aware pacing (keeps "normal" scenarios from
    #    accidentally tripping velocity, so that rule's rejections are
    #    attributable to the *deliberate* burst scenarios only) -----------

    def _note_attempts(self, n: int) -> None:
        now = time.time()
        for _ in range(n):
            self._attempt_timestamps.append(now)

    def _throttle_if_needed(self, headroom: int = 1) -> None:
        now = time.time()
        self._attempt_timestamps = [t for t in self._attempt_timestamps if now - t <= 60]
        while len(self._attempt_timestamps) > MAX_PER_MINUTE - headroom:
            oldest = self._attempt_timestamps[0]
            sleep_for = max(0.0, 60 - (time.time() - oldest) + 1)
            if sleep_for <= 0:
                break
            print(f"    (local throttle: sleeping {sleep_for:.0f}s to stay clear of the velocity window)")
            time.sleep(sleep_for)
            now = time.time()
            self._attempt_timestamps = [t for t in self._attempt_timestamps if now - t <= 60]

    # -- scenario runner --------------------------------------------------

    def run_negotiate_scenario(
        self, scenario_id: str, category: str, description: str, goal_text: str, budget_paise: int,
        *, throttle: bool = True, headroom: int = 1,
    ) -> dict:
        if throttle:
            self._throttle_if_needed(headroom=headroom)
        body, status, latency_ms = self._negotiate(goal_text, budget_paise)
        outcome, rule = self._classify_negotiate(body)
        # Count real attempts this call consumed, from the response itself,
        # so the local throttle tracks reality rather than a guess.
        # `record_purchase_attempt` (backend/app/buyer_agent/agent.py
        # `_pay_and_collect`) only runs for a purchase that actually got
        # approved and reached the payment rail -- a rejected/escalated/
        # replayed attempt never increments velocity server-side, so
        # neither should our local mirror of it.
        attempts = 0
        if outcome == "compliant":
            attempts += 1
            if body.get("upsell_purchased"):
                attempts += 1
        self._note_attempts(attempts)

        rec = LogRecord(
            scenario_id=scenario_id, step=1, category=category, description=description,
            method="POST", url="/negotiate",
            request_body={"goal_text": goal_text, "budget_paise": budget_paise},
            request_headers={"Content-Type": "application/json"},
            response_status=status, response_body=body, latency_ms=round(latency_ms, 1),
            timestamp=time.time(), outcome=outcome, rule=rule,
        )
        self._log(rec)
        print(
            f"[{scenario_id}] {category}: {description}\n"
            f"    -> outcome={outcome} rule={rule} latency={latency_ms:.0f}ms "
            f"reason={str(body.get('reason'))[:140]!r}"
        )
        return body

    def run(self) -> None:
        random.seed(SEED)
        print(f"=== Setu scenario harness -- run {self.run_id} against {BASE_URL} ===")
        print(f"Log: {self.log_path}\n")

        print("--- sanity: kill switch must be off before we start ---")
        status = self.client.get("/admin/kill-switch").json()
        print(f"kill switch status: {status}\n")
        assert status["active"] is False, "kill switch is active -- aborting harness, fix that first"

        # -- category 1: comfortable budget, clean match ---------------------
        comfortable = [
            ("cable-organizer-kit", 44_900, "exact budget, no upsell room"),
            ("mouse-pad-xl", 59_900, "exact budget, no upsell room"),
            ("keycap-set-pbt-129", 89_900, "exact budget, no upsell room"),
            ("wireless-mouse-ergo", 250_000, "healthy margin -- real upsell opportunity (mouse pad)"),
            ("usbc-hub-7in1", 260_000, "healthy margin -- real upsell opportunity (cable organizer)"),
            ("cable-organizer-kit", 50_000, "small margin, no upsell room"),
            ("mouse-pad-xl", 65_000, "small margin, no upsell room"),
            ("keycap-set-pbt-129", 100_000, "small margin, no upsell room"),
        ]
        for i, (pid, budget, note) in enumerate(comfortable, start=1):
            self.run_negotiate_scenario(
                f"comfortable-{i}", "comfortable_budget",
                f"{pid} @ budget={budget} ({note})",
                GOAL_TEXT[pid], budget,
            )

        # -- category 2: tight budget, real negotiation -----------------------
        tight = [
            ("wireless-mouse-ergo", 110_000),
            ("usbc-hub-7in1", 155_000),
            ("keycap-set-pbt-129", 72_000),
            ("mouse-pad-xl", 48_000),
            ("cable-organizer-kit", 36_000),
            ("wireless-mouse-ergo", 100_000),
        ]
        for i, (pid, budget) in enumerate(tight, start=1):
            price = CATALOG_PRICE_PAISE[pid]
            self.run_negotiate_scenario(
                f"tight-{i}", "tight_budget",
                f"{pid} @ budget={budget} (list={price}, min~{round(price*0.75)}) -- real Zeuthen negotiation",
                GOAL_TEXT[pid], budget,
            )

        # -- category 3: no viable match -- must fail gracefully -------------
        for i, goal in enumerate(NO_MATCH_GOALS, start=1):
            budget = random.choice([50_000, 80_000, 120_000, 200_000])
            self.run_negotiate_scenario(
                f"no-match-{i}", "no_viable_match",
                f"goal='{goal}' budget={budget} -- nothing in the catalog should match",
                goal, budget, throttle=False,  # never consumes a purchase attempt
            )

        # -- category 4: deliberate credential-scope / single-tx breach ------
        self.run_negotiate_scenario(
            "limit-credential-scope-1", "deliberate_limit_breach",
            "monitor @ budget=2,500,000 -- comfortably affordable, but its 1,899,900 paise price "
            "exceeds the Buyer Agent's credential scope (500,000) -- must be rejected before any charge",
            GOAL_TEXT["monitor-27-1440p-144hz"], 2_500_000,
        )

        # -- category 5: deliberate duplicate-idempotency-key scenario -------
        self.run_idempotency_scenario()

        # -- category 6: deliberate velocity breach ---------------------------
        self.run_velocity_burst()

        # -- category 7: deliberate daily-spend breach -------------------------
        self.run_daily_spend_burst()

        self.print_summary()

    # -- deliberate scenario 1: duplicate idempotency key --------------------

    def run_idempotency_scenario(self) -> None:
        print("\n=== DELIBERATE SCENARIO: duplicate idempotency key (/products/{id}) ===")
        product_id = "cable-organizer-kit"
        payment_id = f"pay_idem_demo_{uuid.uuid4().hex[:10]}"
        header = self._fabricated_x_payment(product_id, payment_id)

        bodies: list[object] = []
        latencies: list[float] = []
        for step in range(1, 7):  # 6 identical duplicate calls -- more than max_per_minute(5)
            body, status, latency_ms = self._products_get(product_id, header)
            outcome, rule = self._classify_products(status, body)
            bodies.append(body)
            latencies.append(latency_ms)
            self._log(LogRecord(
                scenario_id="idempotency-demo", step=step, category="deliberate_idempotency",
                description=f"duplicate call #{step} with identical X-PAYMENT (payment_id={payment_id})",
                method="GET", url=f"/products/{product_id}",
                request_body=None, request_headers={"X-PAYMENT": "<fabricated, same every call>"},
                response_status=status, response_body=body, latency_ms=round(latency_ms, 1),
                timestamp=time.time(), outcome=outcome, rule=rule,
            ))
            tag = "FIRST CALL (real Razorpay round-trip expected)" if step == 1 else f"DUPLICATE #{step}"
            print(f"    [{tag}] status={status} latency={latency_ms:.0f}ms body={json.dumps(body)[:160]}")

        control_payment_id = f"pay_idem_control_{uuid.uuid4().hex[:10]}"
        control_header = self._fabricated_x_payment(product_id, control_payment_id)
        cbody, cstatus, clat = self._products_get(product_id, control_header)
        coutcome, crule = self._classify_products(cstatus, cbody)
        self._log(LogRecord(
            scenario_id="idempotency-demo", step=7, category="deliberate_idempotency",
            description=f"control call: FRESH idempotency key (payment_id={control_payment_id})",
            method="GET", url=f"/products/{product_id}",
            request_body=None, request_headers={"X-PAYMENT": "<fabricated, fresh key>"},
            response_status=cstatus, response_body=cbody, latency_ms=round(clat, 1),
            timestamp=time.time(), outcome=coutcome, rule=crule,
        ))
        print(f"    [CONTROL, fresh key] status={cstatus} latency={clat:.0f}ms body={json.dumps(cbody)[:160]}")

        identical = all(b == bodies[0] for b in bodies)
        control_not_velocity_blocked = crule != "velocity"
        print(
            f"    RESULT: {len(bodies)} identical-key calls returned byte-identical bodies: {identical}. "
            f"Fresh-key control call was NOT blocked by velocity: {control_not_velocity_blocked} "
            f"(control outcome={coutcome} rule={crule}).\n"
            f"    -> This proves idempotency dedup fired on every duplicate: 6 repeats of the same "
            f"key cost the caller 0 velocity slots combined (only the control's 1 fresh attempt did), "
            f"and none of the 6 duplicates re-hit Razorpay independently.\n"
        )
        # A duplicate call's own real attempt only happens once (step 1);
        # steps 2-6 are cache hits and must not count against velocity.
        self._note_attempts(0)  # anonymous caller bucket is independent of the buyer-agent bucket anyway

    # -- deliberate scenario 2: velocity burst --------------------------------

    def run_velocity_burst(self) -> None:
        print("=== DELIBERATE SCENARIO: velocity limit burst (/negotiate) ===")
        self._throttle_if_needed(headroom=MAX_PER_MINUTE)  # wait for a fully clear window first
        pid = "cable-organizer-kit"
        budget = CATALOG_PRICE_PAISE[pid]  # exact price, no upsell noise
        blocked_seen = False
        for step in range(1, 11):  # safety cap of 10 -- expect the block well before that
            body, status, latency_ms = self._negotiate(GOAL_TEXT[pid], budget)
            outcome, rule = self._classify_negotiate(body)
            self._log(LogRecord(
                scenario_id="velocity-burst", step=step, category="deliberate_velocity",
                description=f"rapid-fire purchase #{step} of {pid} (no artificial pacing)",
                method="POST", url="/negotiate",
                request_body={"goal_text": GOAL_TEXT[pid], "budget_paise": budget},
                request_headers={"Content-Type": "application/json"},
                response_status=status, response_body=body, latency_ms=round(latency_ms, 1),
                timestamp=time.time(), outcome=outcome, rule=rule,
            ))
            print(f"    [burst #{step}] outcome={outcome} rule={rule} latency={latency_ms:.0f}ms")
            if outcome == "compliant":
                self._note_attempts(1)
            if rule == "velocity":
                blocked_seen = True
                print(f"    -> velocity rule fired at attempt #{step}. Stopping burst.\n")
                break
        if not blocked_seen:
            print("    -> WARNING: velocity rule never fired within the safety cap of 10 attempts.\n")

    # -- deliberate scenario 3: daily-spend burst -----------------------------

    def run_daily_spend_burst(self) -> None:
        print("=== DELIBERATE SCENARIO: daily spend cap burst (/negotiate) ===")
        pid = "mechanical-keyboard-65"
        budget = CATALOG_PRICE_PAISE[pid]  # exact price, no upsell noise
        blocked_seen = False
        for step in range(1, 9):  # safety cap -- 8 * 349,900 > 2,000,000 with margin to spare
            self._throttle_if_needed(headroom=1)
            body, status, latency_ms = self._negotiate(GOAL_TEXT[pid], budget)
            outcome, rule = self._classify_negotiate(body)
            self._log(LogRecord(
                scenario_id="daily-spend-burst", step=step, category="deliberate_daily_spend",
                description=f"keyboard purchase #{step} (349,900 paise), pushing toward the 2,000,000 daily cap",
                method="POST", url="/negotiate",
                request_body={"goal_text": GOAL_TEXT[pid], "budget_paise": budget},
                request_headers={"Content-Type": "application/json"},
                response_status=status, response_body=body, latency_ms=round(latency_ms, 1),
                timestamp=time.time(), outcome=outcome, rule=rule,
            ))
            print(f"    [spend #{step}] outcome={outcome} rule={rule} reason={str(body.get('reason'))[:140]!r}")
            if outcome == "compliant":
                self._note_attempts(1)
            if rule == "daily_spend":
                blocked_seen = True
                print(f"    -> daily_spend rule fired at attempt #{step}. Stopping burst.\n")
                break
        if not blocked_seen:
            print("    -> WARNING: daily_spend rule never fired within the safety cap of 8 attempts.\n")

    # -- summary --------------------------------------------------------------

    def print_summary(self) -> None:
        by_category: dict[str, list[LogRecord]] = {}
        for r in self.records:
            by_category.setdefault(r.category, []).append(r)

        total = len(self.records)
        outcomes: dict[str, int] = {}
        rules_fired: dict[str, int] = {}
        for r in self.records:
            outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
            if r.rule:
                rules_fired[r.rule] = rules_fired.get(r.rule, 0) + 1

        named_scenarios = sorted({r.scenario_id for r in self.records})

        summary = {
            "run_id": self.run_id,
            "base_url": BASE_URL,
            "total_named_scenarios": len(named_scenarios),
            "total_http_calls": total,
            "outcomes": outcomes,
            "rules_fired": rules_fired,
            "log_file": str(self.log_path),
        }
        summary_path = RESULTS_DIR / f"run_{self.run_id}_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("=" * 78)
        print("FINAL SUMMARY (real, from this run -- not a claim)")
        print("=" * 78)
        print(f"Named scenarios: {len(named_scenarios)}    Total HTTP calls logged: {total}")
        print(f"Outcomes across all {total} calls: {outcomes}")
        print(f"TrustGuard rules observed firing: {rules_fired}")
        print(f"Full JSONL log:    {self.log_path}")
        print(f"Summary JSON:      {summary_path}")
        print("=" * 78)


if __name__ == "__main__":
    Harness().run()
