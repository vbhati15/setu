import { motion } from "framer-motion";

// Hand-rolled SVG line chart of the two parties' real Zeuthen risk-of-conflict
// values across rounds -- not decorative: every point is r.buyer_risk /
// r.merchant_risk exactly as returned by the negotiate response. The two
// lines visibly converging toward 0 *is* the algorithm reaching agreement.
export default function RiskChart({ rounds, replayKey }) {
  const withRisk = rounds.filter((r) => r.buyer_risk != null && r.merchant_risk != null);
  if (withRisk.length < 2) return null;

  const W = 640;
  const H = 180;
  const padX = 28;
  const padY = 18;
  const n = withRisk.length;
  const x = (i) => padX + (i / (n - 1)) * (W - padX * 2);
  const y = (v) => padY + (1 - v) * (H - padY * 2);

  const buyerPath = withRisk.map((r, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(r.buyer_risk)}`).join(" ");
  const merchantPath = withRisk.map((r, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(r.merchant_risk)}`).join(" ");

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-950/60 px-4 pt-4 pb-2">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] font-mono uppercase tracking-wide text-parchment-500">
          Risk of conflict, by round
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="flex items-center gap-1.5 text-parchment-300">
            <span className="w-2.5 h-2.5 rounded-full bg-parchment-300 inline-block" /> buyer
          </span>
          <span className="flex items-center gap-1.5 text-gold-400">
            <span className="w-2.5 h-2.5 rounded-full bg-gold-400 inline-block" /> merchant
          </span>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" key={replayKey}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={padX}
            x2={W - padX}
            y1={y(t)}
            y2={y(t)}
            stroke="#28221d"
            strokeWidth="1"
          />
        ))}
        <motion.path
          d={merchantPath}
          fill="none"
          stroke="#e6b95a"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.1, ease: "easeInOut" }}
        />
        <motion.path
          d={buyerPath}
          fill="none"
          stroke="#cdc3b3"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.1, ease: "easeInOut", delay: 0.15 }}
        />
        {withRisk.map((r, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(r.buyer_risk)} r="2.5" fill="#cdc3b3" />
            <circle cx={x(i)} cy={y(r.merchant_risk)} r="2.5" fill="#e6b95a" />
          </g>
        ))}
        {withRisk[n - 1].buyer_risk < 0.05 && withRisk[n - 1].merchant_risk < 0.05 && (
          <motion.circle
            cx={x(n - 1)}
            cy={y(0)}
            r="7"
            fill="none"
            stroke="#e6b95a"
            strokeWidth="1.5"
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: [0, 1, 0.4], scale: [0.5, 1.4, 1] }}
            transition={{ duration: 1.4, delay: 1.1 }}
          />
        )}
      </svg>
      <div className="flex justify-between text-[10px] font-mono text-parchment-500 px-1 -mt-1">
        <span>round 1</span>
        <span>round {withRisk[n - 1].round}</span>
      </div>
    </div>
  );
}
