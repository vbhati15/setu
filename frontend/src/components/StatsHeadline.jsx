import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import { useCountUp } from "../lib/useCountUp";
import OutcomeDonut from "./charts/OutcomeDonut";
import SectionBackdrop from "./SectionBackdrop";
import SectionReveal from "./SectionReveal";

const RULE_LABELS = {
  daily_spend: "daily spend cap breach",
  credential_scope: "credential-scope violation",
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

  if (!summary) return <section id="stats" ref={ref} className="snap-panel" />;
  const { outcomes, rules_fired, total_named_scenarios, total_http_calls, base_url } = summary;
  const compliant = outcomes.compliant || 0;
  const blocked = Object.entries(rules_fired || {});

  return (
    <section
      id="stats"
      ref={ref}
      className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 border-t border-ink-700 w-full"
    >
      <SectionBackdrop />
      <SectionReveal className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full">
      <h2 className="text-3xl sm:text-4xl font-semibold text-parchment-100 flex items-center gap-3 mb-4">
        <ShieldCheck size={30} className="text-gold-400" />
        Scenario harness results
      </h2>
      <p className="text-base text-parchment-400 leading-relaxed mb-10 max-w-3xl">
        A real black-box HTTP test run against the live deployment at{" "}
        <span className="font-mono text-parchment-300">{base_url}</span> — {total_named_scenarios} named
        scenarios, {total_http_calls} total calls, logged in full.
      </p>

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-12 items-center mb-12">
        <div className="flex items-baseline gap-6">
          <BigStat value={compliant} inView={inView} />
          <div className="text-parchment-400 text-base leading-tight max-w-[14rem]">
            transactions completed clean, of {total_http_calls} total calls this run
          </div>
        </div>
        <OutcomeDonut outcomes={outcomes} />
      </div>

      <div className="grid sm:grid-cols-4 gap-5 mb-10">
        <Stat label="escalated" value={outcomes.escalated || 0} inView={inView} delay={0.1} />
        <Stat label="rejected" value={outcomes.rejected || 0} inView={inView} delay={0.2} />
        <Stat label="graceful no-match" value={outcomes.graceful_no_match || 0} inView={inView} delay={0.3} />
        <Stat label="named scenarios" value={total_named_scenarios} inView={inView} delay={0.4} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ delay: 0.5, duration: 0.5 }}
        className="rounded-lg border border-ink-700 bg-ink-900/50 p-6"
      >
        <div className="text-xs font-mono uppercase tracking-wide text-parchment-500 mb-4">
          Blocked, by rule (real breaches this run deliberately triggered)
        </div>
        {blocked.length === 0 ? (
          <div className="text-sm text-parchment-500">no rules fired in this run</div>
        ) : (
          <ul className="grid sm:grid-cols-2 gap-x-8 gap-y-2">
            {blocked.map(([rule, count]) => (
              <li key={rule} className="flex items-center justify-between text-sm font-mono">
                <span className="text-parchment-300">{RULE_LABELS[rule] || rule}</span>
                <span className="text-gold-400">{count}×</span>
              </li>
            ))}
          </ul>
        )}
      </motion.div>
      </SectionReveal>
    </section>
  );
}

function BigStat({ value, inView }) {
  const n = useCountUp(value, { start: inView, duration: 1100 });
  return (
    <div
      className="text-8xl sm:text-9xl font-semibold font-mono text-gold-400 leading-none"
      style={{ textShadow: "0 0 50px rgba(230,185,90,0.4)" }}
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
      className="rounded-lg border border-ink-700 bg-ink-900/50 p-6 transition-colors"
    >
      <div className="text-4xl font-semibold font-mono text-parchment-100">{n}</div>
      <div className="text-sm text-parchment-500 mt-2">{label}</div>
    </motion.div>
  );
}
