import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ScrollText } from "lucide-react";

export default function AuditLog({ records }) {
  const [filter, setFilter] = useState("all");
  const filtered = filter === "all" ? records : records.filter((r) => r.outcome === filter);
  const outcomes = [...new Set(records.map((r) => r.outcome))];

  return (
    <div className="relative w-full">
      <h2 className="text-3xl sm:text-4xl font-semibold text-parchment-100 flex items-center gap-3 mb-4">
        <ScrollText size={30} className="text-gold-400" />
        Audit log
      </h2>
      <p className="text-base text-parchment-400 leading-relaxed mb-8 max-w-3xl">
        Every HTTP call from the scenario harness run, in order — real transaction IDs, real timestamps,
        real latencies.
      </p>

      <div className="flex flex-wrap gap-2 mb-5">
        <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
          all ({records.length})
        </FilterChip>
        {outcomes.map((o) => (
          <FilterChip key={o} active={filter === o} onClick={() => setFilter(o)}>
            {o} ({records.filter((r) => r.outcome === o).length})
          </FilterChip>
        ))}
      </div>

      <div className="rounded-lg border border-ink-700 bg-ink-950 max-h-[480px] overflow-y-auto font-mono text-sm">
        <AnimatePresence initial={false}>
          {filtered.map((r, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: Math.min(i * 0.02, 0.3) }}
              className="px-4 py-2 border-b border-ink-800 last:border-0 hover:bg-ink-900/50 flex flex-wrap gap-x-3 gap-y-1"
            >
              <span className="text-parchment-500">{new Date(r.timestamp * 1000).toLocaleTimeString()}</span>
              <span className="text-parchment-300">{r.method}</span>
              <span className="text-parchment-100">{r.url}</span>
              <span
                className={
                  r.outcome === "compliant"
                    ? "text-gold-400"
                    : r.outcome?.startsWith("escalated")
                    ? "text-amber-500"
                    : r.outcome?.startsWith("rejected")
                    ? "text-red-400"
                    : "text-parchment-500"
                }
              >
                {r.outcome}
              </span>
              {r.rule && <span className="text-parchment-500">rule={r.rule}</span>}
              <span className="text-parchment-500">{r.response_status}</span>
              <span className="text-parchment-500">{r.latency_ms}ms</span>
              {r.response_body?.transaction_id && (
                <span className="text-parchment-300">tx={r.response_body.transaction_id}</span>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function FilterChip({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-mono border transition-colors ${
        active
          ? "border-gold-500/60 bg-gold-500/10 text-gold-300"
          : "border-ink-700 text-parchment-500 hover:border-ink-600"
      }`}
    >
      {children}
    </button>
  );
}
