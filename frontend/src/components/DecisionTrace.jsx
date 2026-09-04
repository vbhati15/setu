import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, MinusCircle, GitBranch } from "lucide-react";
import { classifyOutcome, buildChecklist } from "../lib/rules";
import SectionBackdrop from "./SectionBackdrop";

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
    <section id="decision-trace" className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 border-t border-ink-700 w-full">
      <SectionBackdrop />
      <div className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full">
      <h2 className="text-3xl sm:text-4xl font-semibold text-parchment-100 flex items-center gap-3 mb-4">
        <GitBranch size={30} className="text-gold-400" />
        Decision trace
      </h2>
      <p className="text-base text-parchment-400 leading-relaxed mb-10 max-w-3xl">
        TrustGuard runs a fixed, sequential pipeline (kill switch → signature → replay → credential scope →
        velocity → daily spend → spend cap → category) and short-circuits at the first failure — see{" "}
        <code className="font-mono text-parchment-300">backend/app/trust/guard.py</code>. Every check shown
        below "passed" is one the code guarantees ran and cleared before the named rule fired; the failing
        step's text is the exact reason the backend returned.
      </p>

      <div className="grid sm:grid-cols-[260px_1fr] gap-8">
        <div className="flex sm:flex-col gap-2 overflow-x-auto sm:overflow-visible pb-2 sm:pb-0">
          {examples.map((e, i) => {
            const c = classifyOutcome(e.response_body || {});
            return (
              <button
                key={e.scenario_id + e.step}
                onClick={() => setActive(i)}
                className={`text-left whitespace-nowrap sm:whitespace-normal shrink-0 rounded-lg px-3 py-2.5 text-xs font-mono border transition-colors ${
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
            className="rounded-lg border border-ink-700 bg-ink-900/50 p-8"
          >
            <div className="text-base text-parchment-300 mb-6">{ex.description}</div>

            {checklist ? (
              <ol className="space-y-2 relative">
                <div className="absolute left-[9px] top-2 bottom-2 w-px bg-ink-700" />
                {checklist.map((step, i) => (
                  <motion.li
                    key={step.rule}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.06, duration: 0.25 }}
                    className={`relative flex items-start gap-2.5 rounded-md px-4 py-2.5 text-sm font-mono ${
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

            <div className="mt-4 pt-4 border-t border-ink-700 text-xs font-mono text-parchment-500">
              verdict:{" "}
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
                {classified.verdict.toUpperCase()}
              </span>{" "}
              · {ex.method} {ex.url} · {ex.response_status} · {ex.latency_ms}ms
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
      </div>
    </section>
  );
}
