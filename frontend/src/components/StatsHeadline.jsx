import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import { useCountUp } from "../lib/useCountUp";
import OutcomeDonut from "./charts/OutcomeDonut";

const RULE_LABELS = {
  daily_spend: "Tried to spend more than the daily limit allows",
  credential_scope: "Tried to act outside what it's authorized to do",
  velocity: "velocity limit breach",
  spend_cap: "per-transaction spend cap breach",
  category: "category-policy violation",
  kill_switch: "kill-switch block",
  idempotency: "duplicate-charge attempt caught",
};

export default function StatsHeadline({ summary }) {
  const ref = useRef(null);
  // margin must stay non-negative here: a negative rootMargin shrinks the
  // trigger zone inward, which on a short viewport can mean the section
  // never satisfies "in view" at all -- so the count-up would never fire.
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });

  if (!summary) return <div ref={ref} />;
  const { outcomes, rules_fired, total_named_scenarios, total_http_calls } = summary;
  const compliant = outcomes.compliant || 0;
  const blocked = Object.entries(rules_fired || {});

  return (
    <div ref={ref} className="relative w-full">
      <h2 className="text-2xl sm:text-3xl font-semibold text-parchment-100 flex items-center gap-3 mb-2">
        <ShieldCheck size={24} className="text-gold-400" />
        Scenario harness results
      </h2>
      <p className="text-sm text-parchment-400 leading-relaxed mb-5 max-w-3xl">
        We tested Setu against {total_named_scenarios} real-world situations — including ones designed to
        try to break it. Here's exactly what happened, every time.
      </p>

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-8 items-center mb-6">
        <div className="flex items-baseline gap-5">
          <BigStat value={compliant} inView={inView} />
          <div className="text-parchment-400 text-sm leading-tight max-w-[14rem]">
            transactions completed clean, of {total_http_calls} total calls this run
          </div>
        </div>
        <OutcomeDonut outcomes={outcomes} />
      </div>

      <div className="grid sm:grid-cols-4 gap-4 mb-6">
        <Stat label="flagged for review" value={outcomes.escalated || 0} inView={inView} delay={0.1} />
        <Stat label="blocked automatically" value={outcomes.rejected || 0} inView={inView} delay={0.2} />
        <Stat label="no good deal found" value={outcomes.graceful_no_match || 0} inView={inView} delay={0.3} />
        <Stat label="named scenarios" value={total_named_scenarios} inView={inView} delay={0.4} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ delay: 0.5, duration: 0.5 }}
        className="rounded-lg border border-ink-700 bg-ink-900/50 p-4"
      >
        <div className="text-xs font-mono uppercase tracking-wide text-parchment-500 mb-3">
          During testing, we deliberately tried to break these rules — here's what got caught:
        </div>
        {blocked.length === 0 ? (
          <div className="text-sm text-parchment-500">no rules fired in this run</div>
        ) : (
          <ul className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5">
            {blocked.map(([rule, count]) => (
              <li key={rule} className="flex items-center justify-between text-sm font-mono">
                <span className="text-parchment-300">{RULE_LABELS[rule] || rule}</span>
                <span className="text-gold-400">{count}×</span>
              </li>
            ))}
          </ul>
        )}
      </motion.div>
    </div>
  );
}

function BigStat({ value, inView }) {
  const n = useCountUp(value, { start: inView, duration: 1100 });
  return (
    <div
      className="text-6xl sm:text-7xl font-semibold font-mono text-gold-400 leading-none"
      style={{ textShadow: "3px 4px 0px rgba(0,0,0,0.55)" }}
    >
      {n}
    </div>
  );
}

function Stat({ label, value, inView, delay = 0 }) {
  const n = useCountUp(value, { start: inView, duration: 800 });
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ delay, duration: 0.5 }}
      whileHover={{ y: -3, borderColor: "rgba(230,185,90,0.4)" }}
      className="rounded-lg border border-ink-700 bg-ink-900/50 p-4 transition-colors"
    >
      <div className="text-3xl font-semibold font-mono text-parchment-100">{n}</div>
      <div className="text-sm text-parchment-500 mt-1">{label}</div>
    </motion.div>
  );
}
