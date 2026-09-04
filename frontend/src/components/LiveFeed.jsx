import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, ScaleIcon, Zap, SlidersHorizontal } from "lucide-react";
import { postNegotiate, getCatalog } from "../api";
import { groupRoundsFromTrace, hasRiskTelemetry } from "../lib/harness";
import { paise } from "../lib/rules";
import RiskChart from "./charts/RiskChart";
import NegotiationChat from "./NegotiationChat";
import SectionBackdrop from "./SectionBackdrop";
import SectionReveal from "./SectionReveal";

const COOLDOWN_SECONDS = 60;
const STORAGE_KEY = "setu_last_negotiate_trigger_ts";

// Fallback bounds before the catalog loads -- match products.json's actual
// price spread (₹449 cable organizer to ₹18,999 monitor) so the slider never
// shows a range wider than what the catalog can actually satisfy.
const FALLBACK_MIN_RUPEES = 449;
const FALLBACK_MAX_RUPEES = 18_999;

// Curated scenarios only -- real catalog products/budgets mirroring the
// scenario harness (backend/app/scripts/scenario_harness.py), chosen to
// produce genuine multi-round Zeuthen negotiations rather than instant
// list-price accepts. Used by the "surprise me" quick option; the "Try it
// yourself" form below sends the visitor's own budget/product instead.
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

export default function LiveFeed({ fallbackRecord, onResult }) {
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  const [catalog, setCatalog] = useState([]);
  const [catalogError, setCatalogError] = useState(null);
  const [productId, setProductId] = useState("");
  const [budgetRupees, setBudgetRupees] = useState(FALLBACK_MIN_RUPEES);

  useEffect(() => {
    getCatalog()
      .then((products) => {
        setCatalog(products);
        if (products.length > 0) {
          setProductId(products[0].id);
          setBudgetRupees(Math.round(products[0].price_paise / 100));
        }
      })
      .catch((e) => setCatalogError(e.message));
  }, []);

  const minRupees = catalog.length ? Math.floor(Math.min(...catalog.map((p) => p.price_paise)) / 100) : FALLBACK_MIN_RUPEES;
  const maxRupees = catalog.length ? Math.ceil(Math.max(...catalog.map((p) => p.price_paise)) / 100) : FALLBACK_MAX_RUPEES;
  const selectedProduct = catalog.find((p) => p.id === productId) || null;

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
  const replayKey = result?.ts || fallbackRecord?.scenario_id;

  async function run(customScenario) {
    if (cooldown > 0 || state === "loading") return;
    const chosen = customScenario || pickScenario();
    setScenario(chosen);
    setState("loading");
    setError(null);
    const startedAt = Date.now();
    try {
      const body = await postNegotiate(chosen.goal_text, chosen.budget_paise);
      const ts = Date.now();
      setResult({ body, source: "live", scenario: chosen, ts });
      setState("done");
      onResult?.({ body, scenario: chosen, ts, latencyMs: ts - startedAt });
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

  function runCustom(e) {
    e.preventDefault();
    if (!selectedProduct) return;
    const budgetPaise = Math.round(budgetRupees * 100);
    run({
      label: `${selectedProduct.name} — your budget ₹${budgetRupees.toLocaleString("en-IN")}`,
      goal_text: selectedProduct.name,
      budget_paise: budgetPaise,
      custom: true,
    });
  }

  return (
    <section id="live-feed" className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 w-full">
      <SectionBackdrop />
      <SectionReveal className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full">
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
        {cooldown > 0 ? (
          <span className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm text-parchment-500">
            Try again in {cooldown}s
          </span>
        ) : (
          <motion.button
            onClick={() => run()}
            disabled={state === "loading"}
            whileHover={state !== "loading" ? { scale: 1.03, boxShadow: "0 0 24px rgba(230,185,90,0.2)" } : {}}
            whileTap={{ scale: 0.97 }}
            className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition-colors
              border-gold-500/40 bg-gold-500/10 text-gold-300 hover:bg-gold-500/20 hover:border-gold-500/70
              disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-gold-500/10"
          >
            {state === "loading" ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Negotiating live…
              </>
            ) : (
              <>
                <Zap size={15} /> Surprise me
              </>
            )}
          </motion.button>
        )}
      </div>
      <p className="text-base text-parchment-400 leading-relaxed mb-8 max-w-3xl">
        Your AI agent is negotiating in real time — pick your own budget and product below, or hit
        "Surprise me" for a random scenario. Limited to one negotiation per minute.
      </p>

      <form
        onSubmit={runCustom}
        className="mb-8 rounded-lg border border-ink-700 bg-ink-900/50 p-5 sm:p-6"
      >
        <div className="text-xs font-mono uppercase tracking-wide text-parchment-500 mb-4 flex items-center gap-2">
          <SlidersHorizontal size={13} className="text-gold-400" />
          Try it yourself
        </div>

        {catalogError && (
          <div className="text-sm font-mono text-red-400 mb-4">couldn't load catalog: {catalogError}</div>
        )}

        <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-4 items-end">
          <label className="block">
            <span className="block text-xs text-parchment-500 mb-1.5">Product</span>
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              disabled={catalog.length === 0}
              className="w-full rounded-md border border-ink-700 bg-ink-950 px-3 py-2.5 text-sm text-parchment-100 focus:outline-none focus:border-gold-500/50 disabled:opacity-50"
            >
              {catalog.length === 0 && <option>loading catalog…</option>}
              {catalog.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({paise(p.price_paise)})
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="block text-xs text-parchment-500 mb-1.5">
              Your budget — {paise(Math.round(budgetRupees * 100))}
            </span>
            <input
              type="range"
              min={minRupees}
              max={maxRupees}
              step={10}
              value={budgetRupees}
              onChange={(e) => setBudgetRupees(Number(e.target.value))}
              className="w-full accent-[#e6b95a]"
            />
            <div className="flex justify-between text-[10px] font-mono text-parchment-500 mt-1">
              <span>₹{minRupees.toLocaleString("en-IN")}</span>
              <span>₹{maxRupees.toLocaleString("en-IN")}</span>
            </div>
          </label>

          {cooldown > 0 ? (
            <span className="inline-flex items-center justify-center gap-2 rounded-md px-5 py-2.5 text-sm text-parchment-500">
              Try again in {cooldown}s
            </span>
          ) : (
            <motion.button
              type="submit"
              disabled={state === "loading" || !selectedProduct}
              whileHover={state !== "loading" ? { scale: 1.03, boxShadow: "0 0 30px rgba(230,185,90,0.25)" } : {}}
              whileTap={{ scale: 0.98 }}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-gold-500/40 bg-gold-500/10 px-5 py-2.5 text-sm font-medium text-gold-300 hover:bg-gold-500/20 hover:border-gold-500/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-gold-500/10"
            >
              {state === "loading" ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Negotiating…
                </>
              ) : (
                "Start negotiation"
              )}
            </motion.button>
          )}
        </div>
      </form>

      {error && (
        <div className="rounded-md border border-red-900/60 bg-red-950/30 px-4 py-3 text-sm text-red-300 mb-6">
          Something went wrong — please try again.
        </div>
      )}

      {!source && state !== "loading" && (
        <div className="rounded-md border border-ink-700 bg-ink-900/50 px-4 py-6 text-center text-sm text-parchment-500">
          No negotiation loaded yet — pick a product and budget above, or hit "Surprise me".
        </div>
      )}

      {result && (
        <div className="mb-4 text-xs text-parchment-500">
          {scenario.label} · {new Date(result.ts).toLocaleTimeString()}
        </div>
      )}
      {!result && fallbackRecord && (
        <div className="mb-4 text-xs text-parchment-500">Showing a previous negotiation.</div>
      )}

      {liveTelemetry && rounds.length >= 2 && (
        <div className="mb-6">
          <RiskChart rounds={rounds} replayKey={replayKey} />
        </div>
      )}

      {source && <NegotiationChat key={replayKey} trace={trace} outcome={source.body} />}
      </SectionReveal>
    </section>
  );
}
