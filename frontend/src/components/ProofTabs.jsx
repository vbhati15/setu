import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { GitBranch, ShieldCheck, Power, ScrollText } from "lucide-react";
import DecisionTrace from "./DecisionTrace";
import StatsHeadline from "./StatsHeadline";
import KillSwitch from "./KillSwitch";
import AuditLog from "./AuditLog";
import SectionBackdrop from "./SectionBackdrop";
import SectionReveal from "./SectionReveal";

// Single tabbed section replacing four separate always-visible full-page
// panels -- one tab's content is mounted at a time, so switching tabs is a
// real mount/unmount (not just a visibility toggle), which is what lets
// each panel's own animations (checklist stagger, count-up, etc.) replay
// cleanly every time it's reopened.
const TABS = [
  { key: "decision-trace", label: "Decision trace", icon: GitBranch },
  { key: "test-results", label: "Test results", icon: ShieldCheck },
  { key: "kill-switch", label: "Kill switch", icon: Power },
  { key: "audit-log", label: "Audit log", icon: ScrollText },
];

export default function ProofTabs({ decisionExamples, summary, records }) {
  const availability = {
    "decision-trace": decisionExamples.length > 0,
    "test-results": true,
    "kill-switch": true,
    "audit-log": records.length > 0,
  };
  const available = TABS.filter((t) => availability[t.key]);

  const [active, setActive] = useState(available[0]?.key);

  // Keep the selection valid as data loads in (e.g. decision examples
  // arriving after the harness fetch resolves) without fighting a user who
  // has already picked a tab.
  useEffect(() => {
    if (!availability[active] && available[0]) setActive(available[0].key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decisionExamples.length, records.length]);

  useEffect(() => {
    const onGoTo = (e) => {
      const tab = e.detail?.tab;
      if (tab && availability[tab]) setActive(tab);
    };
    window.addEventListener("setu:goto-proof-tab", onGoTo);
    return () => window.removeEventListener("setu:goto-proof-tab", onGoTo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decisionExamples.length, records.length]);

  return (
    <section
      id="proof"
      className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 border-t border-ink-700 w-full"
    >
      <SectionBackdrop />
      <SectionReveal className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full">
        <div className="flex flex-wrap gap-2 mb-10">
          {available.map((t) => {
            const Icon = t.icon;
            const isActive = active === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setActive(t.key)}
                className={`inline-flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-gold-500/60 bg-gold-500/10 text-gold-300"
                    : "border-ink-700 text-parchment-500 hover:border-ink-600 hover:text-parchment-300"
                }`}
              >
                <Icon size={16} className={isActive ? "text-gold-400" : "text-parchment-500"} />
                {t.label}
              </button>
            );
          })}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 14, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className="overflow-hidden"
          >
            {active === "decision-trace" && <DecisionTrace examples={decisionExamples} />}
            {active === "test-results" && <StatsHeadline summary={summary} />}
            {active === "kill-switch" && <KillSwitch />}
            {active === "audit-log" && <AuditLog records={records} />}
          </motion.div>
        </AnimatePresence>
      </SectionReveal>
    </section>
  );
}
