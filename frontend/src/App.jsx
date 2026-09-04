import { useEffect, useState } from "react";
import { getHealth } from "./api";
import { loadHarnessSummary, loadHarnessRecords } from "./lib/harness";
import Hero from "./components/Hero";
import StatsHeadline from "./components/StatsHeadline";
import LiveFeed from "./components/LiveFeed";
import DecisionTrace from "./components/DecisionTrace";
import KillSwitch from "./components/KillSwitch";
import AuditLog from "./components/AuditLog";
import SectionNav from "./components/SectionNav";
import { API_BASE_URL } from "./api";

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
  const [backendStatus, setBackendStatus] = useState("loading");
  const [summary, setSummary] = useState(null);
  const [records, setRecords] = useState([]);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    getHealth()
      .then(() => setBackendStatus("ok"))
      .catch(() => setBackendStatus("error"));

    Promise.all([loadHarnessSummary(), loadHarnessRecords()])
      .then(([s, r]) => {
        setSummary(s);
        setRecords(r);
      })
      .catch((e) => setLoadError(e.message));
  }, []);

  const decisionExamples = records.length ? pickDecisionExamples(records) : [];
  const fallbackHarnessRecord = records.find(
    (r) => r.category === "tight_budget" && r.response_body?.rounds >= 5
  );
  const fallbackFeedRecord = fallbackHarnessRecord && {
    body: fallbackHarnessRecord.response_body,
    scenario_id: fallbackHarnessRecord.scenario_id,
  };

  const navSections = [
    { id: "hero", label: "Setu" },
    { id: "live-feed", label: "Live feed" },
    ...(decisionExamples.length > 0 ? [{ id: "decision-trace", label: "Decision trace" }] : []),
    { id: "stats", label: "Harness results" },
    { id: "kill-switch", label: "Kill switch" },
    ...(records.length > 0 ? [{ id: "audit-log", label: "Audit log" }] : []),
  ];

  return (
    <div className="bg-ink-950 text-parchment-100 font-sans selection:bg-gold-500/30">
      <SectionNav sections={navSections} />
      <Hero apiBaseUrl={API_BASE_URL} backendStatus={backendStatus} summary={summary} />
      <LiveFeed fallbackRecord={fallbackFeedRecord} />
      {decisionExamples.length > 0 && <DecisionTrace examples={decisionExamples} />}
      <StatsHeadline summary={summary} />
      <KillSwitch />
      {records.length > 0 && <AuditLog records={records} />}

      <section className="snap-panel flex flex-col items-center justify-center px-6 border-t border-ink-700">
        {loadError && (
          <div className="mb-6 max-w-md text-center text-sm font-mono text-red-400">
            couldn't load harness data: {loadError}
          </div>
        )}
        <footer className="text-center text-xs font-mono text-parchment-500">
          Setu — every number on this page traces back to a real request/response or a real harness run.
        </footer>
      </section>
    </div>
  );
}
