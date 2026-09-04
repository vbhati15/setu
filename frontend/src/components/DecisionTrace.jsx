import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, MinusCircle, GitBranch } from "lucide-react";
import { classifyOutcome, buildChecklist, paise, formatDuration } from "../lib/rules";

// A plain-language stand-in for the harness's own scenario description
// (which is internal shorthand like "cable-organizer-kit @ budget=44900
// (exact budget, no upsell room)") -- built from the same response data,
// just described the way a shopper would read it.
function friendlySummary(ex, classified) {
  const product = ex.response_body?.product?.name;
  const budget = paise(ex.request_body?.budget_paise);
  const upsold = ex.response_body?.upsell_purchased;
  const exactMatch = ex.response_body?.agreed_price_paise === ex.request_body?.budget_paise;

  let note = "comfortable budget";
  if (classified.verdict === "approved") {
    note = upsold ? "comfortable budget, with an extra item added" : exactMatch ? "exact match, no room for extras" : "comfortable budget";
  } else if (classified.verdict === "escalated") {
    note = classified.rule === "daily_spend" ? "the agent's daily spending limit was reached" : "flagged for a manual review";
  } else if (classified.verdict === "rejected") {
    note =
      classified.rule === "credential_scope"
        ? "price is within budget, but above what this agent can approve on its own"
        : "blocked before any charge was made";
  }

  if (!product) return null;
  return `Buying: ${product} · Budget: ${budget} (${note})`;
}

function StepIcon({ status }) {
  if (status === "pass") return <Check size={14} className="text-gold-400 shrink-0" />;
  if (status === "fail") return <X size={14} className="text-red-400 shrink-0" />;
  return <MinusCircle size={14} className="text-parchment-500/50 shrink-0" />;
}

export default function DecisionTrace({ examples }) {
  const [active, setActive] = useState(0);
  const ex = examples[active];
  const body = ex?.response_body || {};
  const classified = classifyOutcome(body);
  const checklist = buildChecklist(classified);

  return (
    <div className="relative w-full">
      <h2 className="text-2xl sm:text-3xl font-semibold text-parchment-100 flex items-center gap-3 mb-2">
        <GitBranch size={24} className="text-gold-400" />
        Decision trace
      </h2>
      <p className="text-sm text-parchment-400 leading-relaxed mb-5 max-w-3xl">
        Before any purchase goes through, we run 8 independent safety checks, in order. If any single one
        fails, everything stops right there — no partial approvals, no guessing.
      </p>

      <div className="grid sm:grid-cols-[220px_1fr] gap-6">
        <div className="flex sm:flex-col gap-2 overflow-x-auto sm:overflow-visible pb-2 sm:pb-0">
          {examples.map((e, i) => {
            const c = classifyOutcome(e.response_body || {});
            return (
              <button
                key={e.scenario_id + e.step}
                onClick={() => setActive(i)}
                className={`text-left whitespace-nowrap sm:whitespace-normal shrink-0 rounded-lg px-3 py-2 text-xs font-mono border transition-colors ${
                  i === active
                    ? "border-gold-500/60 bg-gold-500/10 text-gold-300"
                    : "border-ink-700 text-parchment-500 hover:border-ink-600 hover:text-parchment-300"
                }`}
              >
                <div
                  className={`text-[9px] uppercase tracking-wide mb-1 ${
                    c.verdict === "approved"
                      ? "text-gold-500"
                      : c.verdict === "escalated"
                      ? "text-amber-500"
                      : c.verdict === "rejected"
                      ? "text-red-400"
                      : "text-parchment-500"
                  }`}
                >
                  {c.verdict}
                </div>
                {e.label}
              </button>
            );
          })}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.25 }}
            className="rounded-lg border border-ink-700 bg-ink-900/50 p-5"
          >
            <div className="text-sm text-parchment-300 mb-3">{friendlySummary(ex, classified) || ex.description}</div>

            {checklist ? (
              <ol className="space-y-1 relative -mx-4">
                <div className="absolute left-[25px] top-2 bottom-2 w-px bg-ink-700" />
                {checklist.map((step, i) => (
                  <motion.li
                    key={step.rule}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.06, duration: 0.25 }}
                    className={`relative flex items-start gap-2.5 rounded-md px-4 py-1.5 text-sm font-mono ${
                      step.status === "fail"
                        ? "bg-red-950/30 border border-red-900/50 text-red-300"
                        : step.status === "pass"
                        ? "text-parchment-300"
                        : "text-parchment-500/50"
                    }`}
                  >
                    <span className="bg-ink-900 rounded-full z-10">
                      <StepIcon status={step.status} />
                    </span>
                    <div>
                      <div>{step.label}</div>
                      {step.status === "fail" && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          transition={{ delay: i * 0.06 + 0.15 }}
                          className="text-xs text-red-400/80 mt-1 normal-case font-mono"
                        >
                          {classified.detail}
                        </motion.div>
                      )}
                    </div>
                  </motion.li>
                ))}
              </ol>
            ) : (
              <div className="text-sm text-parchment-500 font-mono">
                {classified.detail || "no matching product / not a trust-layer verdict"}
              </div>
            )}

            <div className="mt-3 pt-3 border-t border-ink-700 text-xs font-mono text-parchment-500">
              Result:{" "}
              <span
                className={
                  classified.verdict === "approved"
                    ? "text-gold-400"
                    : classified.verdict === "escalated"
                    ? "text-amber-500"
                    : classified.verdict === "rejected"
                    ? "text-red-400"
                    : "text-parchment-400"
                }
              >
                {classified.verdict === "approved"
                  ? "Approved"
                  : classified.verdict === "escalated"
                  ? "Escalated for review"
                  : classified.verdict === "rejected"
                  ? "Rejected"
                  : classified.verdict}
              </span>{" "}
              · Completed in {formatDuration(ex.latency_ms)}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
