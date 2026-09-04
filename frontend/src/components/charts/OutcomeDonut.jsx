import { motion } from "framer-motion";

const COLORS = {
  compliant: "#e6b95a",
  escalated: "#b8842e",
  rejected: "#c8524a",
  graceful_no_match: "#5c5449",
  failed_verification: "#3a322a",
};

const LABELS = {
  compliant: "Completed successfully",
  escalated: "Flagged for review",
  rejected: "Blocked automatically",
  graceful_no_match: "No good deal found",
  failed_verification: "verification failed",
};

// Real donut of the harness's own outcome counts -- radius per segment is
// literally count / total, nothing normalized for effect.
export default function OutcomeDonut({ outcomes }) {
  const entries = Object.entries(outcomes).filter(([, v]) => v > 0);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const R = 60;
  const CX = 70;
  const CY = 70;
  const STROKE = 22;
  const circumference = 2 * Math.PI * R;

  let acc = 0;
  const segments = entries.map(([key, value]) => {
    const frac = value / total;
    const dash = frac * circumference;
    const offset = acc * circumference;
    acc += frac;
    return { key, value, dash, offset, frac };
  });

  return (
    <div className="flex items-center gap-6 flex-wrap sm:flex-nowrap">
      <svg viewBox="0 0 140 140" className="w-36 h-36 shrink-0 -rotate-90">
        <circle cx={CX} cy={CY} r={R} fill="none" stroke="#1d1916" strokeWidth={STROKE} />
        {segments.map((s, i) => (
          <motion.circle
            key={s.key}
            cx={CX}
            cy={CY}
            r={R}
            fill="none"
            stroke={COLORS[s.key] || "#5c5449"}
            strokeWidth={STROKE}
            strokeDasharray={`${circumference} ${circumference}`}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - s.dash }}
            transition={{ duration: 0.9, delay: 0.1 * i, ease: "easeOut" }}
            style={{ transform: `rotate(${s.offset * (360 / circumference)}deg)`, transformOrigin: "70px 70px" }}
            strokeLinecap="butt"
          />
        ))}
      </svg>
      <div className="space-y-2">
        {segments.map((s) => (
          <div key={s.key}>
            <div className="flex items-center gap-3 text-sm font-mono">
              <span className="w-3 h-3 rounded-full inline-block" style={{ background: COLORS[s.key] }} />
              <span className="text-parchment-300">{LABELS[s.key] || s.key}</span>
              <span className="text-parchment-500">
                {s.value} ({Math.round(s.frac * 100)}%)
              </span>
            </div>
            {s.key === "graceful_no_match" && (
              <div className="text-xs text-parchment-500/70 italic ml-6 mt-0.5">
                a good outcome — no deal made sense here
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
