import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check } from "lucide-react";

// Visualizes the core loop: an ask and a bid tick toward each other round
// by round until they land on a number both sides accept -- "negotiate,
// pay, explain" in one glance.
const ROUNDS = [
  { ask: 182, bid: 58 },
  { ask: 156, bid: 74 },
  { ask: 138, bid: 91 },
  { ask: 124, bid: 103 },
  { ask: 116, bid: 111 },
];
const AGREED = 113;
const STEP_MS = 750;
const HOLD_MS = 1600;

const SIZES = {
  md: {
    box: "px-6 py-3 min-h-[64px] min-w-[240px]",
    label: "text-[10px]",
    value: "text-2xl",
    valueBox: "h-9 w-24",
    gap: "gap-5",
    divider: "w-10",
    round: "text-[9px]",
    check: "p-1.5",
    checkIcon: 14,
  },
  lg: {
    box: "px-12 py-8 min-h-[132px] min-w-[400px]",
    label: "text-xs",
    value: "text-4xl",
    valueBox: "h-14 w-36",
    gap: "gap-8",
    divider: "w-16",
    round: "text-[11px]",
    check: "p-2.5",
    checkIcon: 20,
  },
};

function TickCard({ label, value, tone, s }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className={`${s.label} font-mono uppercase tracking-[0.2em] text-parchment-500`}>{label}</span>
      <div className={`relative ${s.valueBox} overflow-hidden`}>
        <AnimatePresence mode="popLayout">
          <motion.span
            key={value}
            initial={{ y: 18, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -18, opacity: 0 }}
            transition={{ duration: 0.32, ease: "easeOut" }}
            className={`absolute inset-0 flex items-center justify-center ${s.value} font-mono font-semibold ${tone}`}
          >
            ${value}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}

export default function NegotiationTicker({ size = "md", full = false }) {
  const [round, setRound] = useState(0);
  const settled = round >= ROUNDS.length;
  const s = SIZES[size] ?? SIZES.md;
  const justify = full ? "justify-between" : "justify-center";

  useEffect(() => {
    const delay = settled ? HOLD_MS : STEP_MS;
    const id = setTimeout(() => {
      setRound((r) => (r >= ROUNDS.length ? 0 : r + 1));
    }, delay);
    return () => clearTimeout(id);
  }, [round, settled]);

  const current = ROUNDS[Math.min(round, ROUNDS.length - 1)];

  return (
    <div
      className={`relative flex items-center justify-center rounded-2xl border border-ink-600 bg-ink-900/60 backdrop-blur ${s.box} ${
        full ? "w-full" : ""
      }`}
    >
      <AnimatePresence>
        {!settled ? (
          <motion.div
            key="negotiating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className={`absolute inset-0 flex items-center ${justify} ${s.gap} ${full ? "px-2" : ""}`}
          >
            <TickCard label="Ask" value={current.ask} tone="text-parchment-300" s={s} />
            <div className="flex flex-col items-center gap-1">
              <motion.div
                className={`h-px ${s.divider} bg-gold-400/50`}
                animate={{ scaleX: [0.4, 1, 0.4] }}
                transition={{ duration: 0.75, repeat: Infinity, ease: "easeInOut" }}
              />
              <span className={`${s.round} font-mono uppercase tracking-widest text-gold-400/70`}>
                round {round + 1}
              </span>
            </div>
            <TickCard label="Bid" value={current.bid} tone="text-gold-400" s={s} />
          </motion.div>
        ) : (
          <motion.div
            key="agreed"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className={`absolute inset-0 flex items-center justify-center ${s.gap}`}
          >
            <motion.div
              animate={{ boxShadow: ["0 0 0px rgba(230,185,90,0.4)", "0 0 18px rgba(230,185,90,0.55)", "0 0 0px rgba(230,185,90,0.4)"] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
              className={`flex items-center justify-center rounded-full bg-gold-500 ${s.check}`}
            >
              <Check size={s.checkIcon} className="text-ink-950" strokeWidth={3} />
            </motion.div>
            <span className={`${s.label} font-mono uppercase tracking-[0.2em] text-parchment-500`}>
              Agreed
            </span>
            <span className={`${s.value} font-mono font-semibold text-parchment-100`}>${AGREED}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
