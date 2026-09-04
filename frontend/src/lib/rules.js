// Reconstructs TrustGuard's rule-evaluation checklist for a given outcome.
//
// This is NOT a guess: backend/app/trust/guard.py runs these checks as a
// strict, sequential short-circuit pipeline (see its module docstring) --
// kill_switch -> signature -> replay -> credential_scope -> idempotency ->
// velocity -> daily_spend -> policy(spend_cap, category). If the API tells
// us which rule failed (or that the purchase succeeded), every step before
// it in this fixed order is mechanically guaranteed to have passed. We only
// ever render a check as failed when the backend's own `reason` text names
// that rule, and we display that exact reason text -- nothing here is
// fabricated or illustrative.
export const SIGNED_PIPELINE = [
  { rule: "kill_switch", label: "Kill switch inactive" },
  { rule: "signature", label: "Signature & credential valid" },
  { rule: "replay", label: "Not a replay (fresh nonce, in-window)" },
  { rule: "credential_scope", label: "Within agent's credential scope" },
  { rule: "velocity", label: "Within velocity limit" },
  { rule: "daily_spend", label: "Within daily spend cap" },
  { rule: "spend_cap", label: "Within per-transaction spend cap" },
  { rule: "category", label: "Category allowed" },
];

const RULE_RE = /\(([a-z_]+)\):/;

export function extractRule(reasonText) {
  if (!reasonText) return null;
  const m = RULE_RE.exec(reasonText);
  return m ? m[1] : null;
}

export function detailAfterRule(reasonText) {
  const idx = reasonText.indexOf("): ");
  return idx >= 0 ? reasonText.slice(idx + 3) : reasonText;
}

// Classifies one /negotiate (or /products) response body into a verdict the
// decision-trace panel can render.
export function classifyOutcome(body) {
  const reason = body?.reason || body?.error || "";
  if (body?.success === true) {
    return { verdict: "approved", rule: null, detail: reason };
  }
  if (reason.includes("kill switch is active")) {
    return { verdict: "rejected", rule: "kill_switch", detail: reason };
  }
  if (reason.includes("escalated for review")) {
    return { verdict: "escalated", rule: extractRule(reason), detail: detailAfterRule(reason) };
  }
  if (reason.includes("rejected by trust layer")) {
    return { verdict: "rejected", rule: extractRule(reason), detail: detailAfterRule(reason) };
  }
  return { verdict: "other", rule: null, detail: reason };
}

// Builds the ordered checklist to render for one classified outcome.
// Returns null when the outcome isn't a TrustGuard verdict at all (e.g. "no
// catalog product matches" -- negotiation never reached the trust layer).
export function buildChecklist({ verdict, rule }) {
  if (verdict === "other") return null;
  if (verdict === "approved") {
    return SIGNED_PIPELINE.map((step) => ({ ...step, status: "pass" }));
  }
  const idx = SIGNED_PIPELINE.findIndex((s) => s.rule === rule);
  if (idx === -1) return null;
  return SIGNED_PIPELINE.map((step, i) => ({
    ...step,
    status: i < idx ? "pass" : i === idx ? "fail" : "unreached",
  }));
}

export function paise(n) {
  if (n === null || n === undefined) return "--";
  return `₹${(n / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
