import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ScrollText } from "lucide-react";
import { OUTCOME_LABELS, RULE_LABELS, formatDuration, describeEndpoint, orderNumber } from "../lib/rules";

export default function AuditLog({ records }) {
  const [filter, setFilter] = useState("all");
  const filtered = filter === "all" ? records : records.filter((r) => r.outcome === filter);
  const outcomes = [...new Set(records.map((r) => r.outcome))];

  return (
    <div className="relative w-full">
      <h2 className="text-2xl sm:text-3xl font-semibold text-parchment-100 flex items-center gap-3 mb-2">
        <ScrollText size={24} className="text-gold-400" />
        Audit log
      </h2>
      <p className="text-sm text-parchment-400 leading-relaxed mb-4 max-w-3xl">
        Every single test, in the order it happened — with real order numbers, real timestamps, and how
        long each one took.
      </p>

      <div className="flex flex-wrap gap-2 mb-5">
        <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
          All ({records.length})
        </FilterChip>
        {outcomes.map((o) => (
          <FilterChip key={o} active={filter === o} onClick={() => setFilter(o)}>
            {OUTCOME_LABELS[o] || o} ({records.filter((r) => r.outcome === o).length})
          </FilterChip>
        ))}
      </div>

      <div className="rounded-lg border border-ink-700 bg-ink-950 max-h-[380px] overflow-y-auto font-mono text-sm">
        <AnimatePresence initial={false}>
          {filtered.map((r, i) => {
            const order = orderNumber(r.response_body?.transaction_id);
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2, delay: Math.min(i * 0.02, 0.3) }}
                className="px-4 py-2 border-b border-ink-800 last:border-0 hover:bg-ink-900/50 flex flex-wrap gap-x-3 gap-y-1"
              >
                <span className="text-parchment-500">{new Date(r.timestamp * 1000).toLocaleTimeString()}</span>
                <span className="text-parchment-300">{describeEndpoint(r.method, r.url)}</span>
                <span
                  className={
                    r.outcome === "compliant"
                      ? "text-gold-400"
                      : r.outcome === "escalated"
                      ? "text-amber-500"
                      : r.outcome === "rejected"
                      ? "text-red-400"
                      : "text-parchment-500"
                  }
                >
                  {OUTCOME_LABELS[r.outcome] || r.outcome}
                </span>
                {r.rule && <span className="text-parchment-500">{RULE_LABELS[r.rule] || r.rule}</span>}
                <span className="text-parchment-500">{formatDuration(r.latency_ms)}</span>
                {order && <span className="text-parchment-300">Order #{order}</span>}
              </motion.div>
            );
          })}
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
