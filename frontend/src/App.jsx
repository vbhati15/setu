import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { loadHarnessSummary, loadHarnessRecords } from "./lib/harness";
import { paise } from "./lib/rules";
import Header from "./components/Header";
import ScrollProgress from "./components/ScrollProgress";
import Hero from "./components/Hero";
import HowItWorks from "./components/HowItWorks";
import StatsHeadline from "./components/StatsHeadline";
import LiveFeed from "./components/LiveFeed";
import DecisionTrace from "./components/DecisionTrace";
import KillSwitch from "./components/KillSwitch";
import AuditLog from "./components/AuditLog";
import SectionNav from "./components/SectionNav";
import SectionReveal from "./components/SectionReveal";

function pickDecisionExamples(records) {
  const byId = (id, step = 1) => records.find((r) => r.scenario_id === id && r.step === step);
  const firstWithRule = (rule) => records.find((r) => r.rule === rule);

  const picks = [
    { rec: byId("comfortable-1"), label: "approved · comfortable budget" },
    { rec: firstWithRule("daily_spend"), label: "escalated · daily spend cap" },
    { rec: byId("limit-credential-scope-1"), label: "rejected · credential scope" },
    { rec: byId("comfortable-4"), label: "approved · with upsell" },
  ].filter((p) => p.rec);

  return picks.map((p) => ({ ...p.rec, label: p.label }));
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [records, setRecords] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [liveResult, setLiveResult] = useState(null);

  useEffect(() => {
    Promise.all([loadHarnessSummary(), loadHarnessRecords()])
      .then(([s, r]) => {
        setSummary(s);
        setRecords(r);
      })
      .catch((e) => setLoadError(e.message));
  }, []);

  const liveDecisionExample = liveResult && {
    scenario_id: `live-${liveResult.ts}`,
    step: 1,
    label: liveResult.scenario.custom ? "your live negotiation" : "live · random scenario",
    description: `Live ${liveResult.scenario.custom ? "visitor-triggered" : "randomized"} negotiation for "${liveResult.scenario.goal_text}", budget ${paise(liveResult.scenario.budget_paise)} — this is the real /negotiate response that just came back, not a harness replay.`,
    response_body: liveResult.body,
    method: "POST",
    url: "/negotiate",
    response_status: 200,
    latency_ms: liveResult.latencyMs,
  };
  const decisionExamples = [
    ...(liveDecisionExample ? [liveDecisionExample] : []),
    ...(records.length ? pickDecisionExamples(records) : []),
  ];
  const fallbackHarnessRecord = records.find(
    (r) => r.category === "tight_budget" && r.response_body?.rounds >= 5
  );
  const fallbackFeedRecord = fallbackHarnessRecord && {
    body: fallbackHarnessRecord.response_body,
    scenario_id: fallbackHarnessRecord.scenario_id,
  };

  const navSections = [
    { id: "hero", label: "Setu" },
    { id: "how-it-works", label: "How it works" },
    { id: "live-feed", label: "Live feed" },
    ...(decisionExamples.length > 0 ? [{ id: "decision-trace", label: "Decision trace" }] : []),
    { id: "stats", label: "Harness results" },
    ...(records.length > 0 ? [{ id: "audit-log", label: "Audit log" }] : []),
    { id: "kill-switch", label: "System status" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="bg-ink-950 text-parchment-100 font-sans selection:bg-gold-500/30"
    >
      <Header />
      <ScrollProgress />
      <SectionNav sections={navSections} />
      <Hero summary={summary} />
      <HowItWorks />
      <LiveFeed fallbackRecord={fallbackFeedRecord} onResult={setLiveResult} />
      {decisionExamples.length > 0 && <DecisionTrace examples={decisionExamples} />}
      <StatsHeadline summary={summary} />
      {records.length > 0 && <AuditLog records={records} />}
      <KillSwitch />

      <section className="snap-panel flex flex-col items-center justify-center px-6 border-t border-ink-700">
        <SectionReveal className="flex flex-col items-center">
          {loadError && (
            <div className="mb-6 max-w-md text-center text-sm font-mono text-red-400">
              couldn't load harness data: {loadError}
            </div>
          )}
          <footer className="text-center text-xs font-mono text-parchment-500">
            Setu — every number on this page traces back to a real request/response or a real harness run.
          </footer>
        </SectionReveal>
      </section>
    </motion.div>
  );
}
