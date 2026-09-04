import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Clock, ScaleIcon, Zap } from "lucide-react";
import { postNegotiate, API_BASE_URL } from "../api";
import { groupRoundsFromTrace, hasRiskTelemetry } from "../lib/harness";
import { paise } from "../lib/rules";
import RiskChart from "./charts/RiskChart";
import SectionBackdrop from "./SectionBackdrop";

const COOLDOWN_SECONDS = 60;
const STORAGE_KEY = "setu_last_negotiate_trigger_ts";

// Curated scenarios only -- real catalog products/budgets mirroring the
// scenario harness (backend/app/scripts/scenario_harness.py), chosen to
// produce genuine multi-round Zeuthen negotiations rather than instant
// list-price accepts. Never a freeform user-supplied budget: this button
// fires real Gemini calls per round (up to 12 rounds x 2 phrasing calls),
// so the surface stays bounded and can't be turned into an open prompt.
const SCENARIOS = [
  { label: "Wireless mouse, tight budget", goal_text: "ergonomic wireless mouse 2.4ghz", budget_paise: 110_000 },
  { label: "USB-C hub, tight budget", goal_text: "usb-c hub 7-in-1 with hdmi", budget_paise: 155_000 },
  { label: "Keycap set, tight budget", goal_text: "pbt keycap set 129 keys", budget_paise: 72_000 },
  { label: "Mouse pad, tight budget", goal_text: "extended xl desk mouse pad", budget_paise: 48_000 },
  { label: "Cable organizer, tight budget", goal_text: "cable organizer kit for desk", budget_paise: 36_000 },
];

function pickScenario() {
  return SCENARIOS[Math.floor(Math.random() * SCENARIOS.length)];
}

export default function LiveFeed({ fallbackRecord }) {
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);
  const [revealCount, setRevealCount] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    const tick = () => {
      const last = Number(localStorage.getItem(STORAGE_KEY) || 0);
      const remaining = Math.max(0, COOLDOWN_SECONDS - Math.floor((Date.now() - last) / 1000));
      setCooldown(remaining);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const source = result || fallbackRecord;
  const trace = source?.body?.trace || [];
  const rounds = groupRoundsFromTrace(trace);
  const liveTelemetry = hasRiskTelemetry(trace);

  useEffect(() => {
    if (state !== "done") return;
    setRevealCount(0);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setRevealCount((c) => {
        if (c >= rounds.length) {
          clearInterval(timerRef.current);
          return c;
        }
        return c + 1;
      });
    }, 550);
    return () => clearInterval(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, result]);

  const visibleRounds = state === "done" ? rounds.slice(0, revealCount) : rounds;

  async function run() {
    if (cooldown > 0 || state === "loading") return;
    const chosen = pickScenario();
    setScenario(chosen);
    setState("loading");
    setError(null);
    try {
      const body = await postNegotiate(chosen.goal_text, chosen.budget_paise);
      setResult({ body, source: "live", scenario: chosen, ts: Date.now() });
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("error");
    } finally {
      // Cooldown is measured from when the run *finishes*, not when it
      // started -- a multi-round Zeuthen negotiation can itself take close
      // to a minute (up to 12 rounds x 2 live Gemini calls), so starting the
      // clock at click-time could let the cooldown fully elapse during the
      // run itself and defeat the point of throttling repeat clicks.
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    }
  }

  return (
    <section id="live-feed" className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 w-full">
      <SectionBackdrop />
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ amount: "some", once: true }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full"
      >
      <div className="flex items-baseline justify-between flex-wrap gap-4 mb-3">
        <h2 className="text-3xl sm:text-4xl font-semibold text-parchment-100 flex items-center gap-3">
          <ScaleIcon size={28} className="text-gold-400" />
          Live negotiation feed
          {result && (
            <motion.span
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="inline-flex items-center gap-1 rounded-full border border-gold-500/40 bg-gold-500/10 px-2 py-0.5 text-[10px] font-mono text-gold-300 tracking-wide"
            >
              <motion.span
                className="w-1.5 h-1.5 rounded-full bg-gold-400 inline-block"
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
              LIVE RUN
            </motion.span>
          )}
        </h2>
        <motion.button
          onClick={run}
          disabled={cooldown > 0 || state === "loading"}
          whileHover={cooldown === 0 && state !== "loading" ? { scale: 1.03, boxShadow: "0 0 24px rgba(230,185,90,0.2)" } : {}}
          whileTap={{ scale: 0.97 }}
          className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition-colors
            border-gold-500/40 bg-gold-500/10 text-gold-300 hover:bg-gold-500/20 hover:border-gold-500/70
            disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-gold-500/10"
        >
          {state === "loading" ? (
            <>
              <Loader2 size={15} className="animate-spin" /> Negotiating live…
            </>
          ) : cooldown > 0 ? (
            <>
              <Clock size={15} /> Wait {cooldown}s
            </>
          ) : (
            <>
              <Zap size={15} /> Run a live negotiation
            </>
          )}
        </motion.button>
      </div>
      <p className="text-base text-parchment-400 leading-relaxed mb-8 max-w-3xl">
        Fires a fresh <code className="font-mono text-parchment-300">POST /negotiate</code> against the
        real backend with a randomized tight-budget scenario. Every round below is the actual Zeuthen
        risk-of-conflict math the server computed for that request — cooled down to one request/min so a
        curious visitor can't run up the live LLM bill.
      </p>

      {error && (
        <div className="rounded-md border border-red-900/60 bg-red-950/30 px-4 py-3 text-sm text-red-300 mb-6 font-mono">
          request failed: {error}
        </div>
      )}

      {!source && state !== "loading" && (
        <div className="rounded-md border border-ink-700 bg-ink-900/50 px-4 py-6 text-center text-sm text-parchment-500">
          No negotiation loaded yet — click "Run a live negotiation" above.
        </div>
      )}

      {result && (
        <div className="mb-4 text-xs font-mono text-parchment-500">
          scenario: {scenario.label} · budget {paise(scenario.budget_paise)} ·{" "}
          {new Date(result.ts).toLocaleTimeString()} · live response from {API_BASE_URL}
        </div>
      )}
      {!result && fallbackRecord && (
        <div className="mb-4 text-xs font-mono text-parchment-500">
          showing last verified scenario-harness run ({fallbackRecord.scenario_id}) — real HTTP evidence, not a fresh call
        </div>
      )}

      {source && !liveTelemetry && (
        <div className="rounded-md border border-ink-700 bg-ink-900/40 px-4 py-2 text-xs font-mono text-parchment-500 mb-4">
          this response predates the risk-telemetry fields on /negotiate — showing messages only, no risk readout
        </div>
      )}

      {liveTelemetry && rounds.length >= 2 && (
        <div className="mb-6">
          <RiskChart rounds={rounds} replayKey={result?.ts || fallbackRecord?.scenario_id} />
        </div>
      )}

      <div className="space-y-3">
        <AnimatePresence initial={false}>
          {visibleRounds.map((r) => (
            <motion.div
              key={r.round}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={{ y: -2, borderColor: "rgba(230,185,90,0.35)" }}
              className="rounded-lg border border-ink-700 bg-ink-900/50 p-4 transition-colors"
            >
              <div className="flex items-center justify-between text-xs font-mono text-parchment-500 mb-3">
                <span>ROUND {r.round}</span>
                {r.buyer_offer_paise != null && (
                  <span>
                    buyer {paise(r.buyer_offer_paise)} · merchant {paise(r.merchant_offer_paise)}
                  </span>
                )}
              </div>
              <div className="grid sm:grid-cols-2 gap-3 mb-3">
                {r.messages.map((m, i) => {
                  const isConceder = r.conceder === m.speaker;
                  return (
                    <div
                      key={i}
                      className={`rounded-md px-3 py-2 text-sm transition-shadow ${
                        m.speaker === "buyer"
                          ? "bg-ink-800/70 text-parchment-100 border border-ink-600"
                          : "bg-gold-500/[0.07] text-parchment-100 border border-gold-500/20"
                      } ${isConceder ? "ring-1 ring-gold-400/50" : ""}`}
                    >
                      <div className="text-[10px] font-mono uppercase tracking-wide mb-1 text-parchment-500 flex items-center gap-1.5">
                        {m.speaker}
                        {isConceder && <span className="text-gold-400 normal-case">· conceded this round</span>}
                      </div>
                      {m.message}
                    </div>
                  );
                })}
              </div>
              {r.buyer_risk != null && (
                <div className="rounded bg-ink-950 border border-ink-700 px-3 py-2 font-mono text-xs text-gold-300">
                  Risk(Buyer)={r.buyer_risk.toFixed(2)} vs Risk(Merchant)={r.merchant_risk.toFixed(2)}
                  {r.conceder ? (
                    <>
                      {" "}
                      → {r.conceder === "buyer" ? "Buyer" : "Merchant"} concedes {paise(r.concessionPaise)}
                    </>
                  ) : r.round === 1 ? (
                    <> — opening positions</>
                  ) : null}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {source?.body && (
        <div className="mt-6 rounded-lg border border-ink-700 bg-ink-900/40 px-4 py-3 text-sm">
          <span className={source.body.success ? "text-gold-300" : "text-parchment-300"}>
            {source.body.success ? "✓ " : "— "}
            {source.body.reason}
          </span>
          {source.body.transaction_id && (
            <span className="block mt-1 font-mono text-xs text-parchment-500">
              transaction {source.body.transaction_id}
            </span>
          )}
        </div>
      )}
      </motion.div>
    </section>
  );
}
