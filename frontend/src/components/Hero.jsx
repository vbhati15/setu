import { motion } from "framer-motion";
import { ArrowDown, Radio } from "lucide-react";

function FloatingBadge({ children, className, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: [16, 0, -6, 0] }}
      transition={{
        opacity: { duration: 0.6, delay },
        y: { duration: 5, delay: delay + 0.6, repeat: Infinity, ease: "easeInOut" },
      }}
      className={`hidden lg:block absolute rounded-full border border-ink-600 bg-ink-900/70 backdrop-blur px-3 py-1.5 text-[11px] font-mono text-parchment-300 ${className}`}
    >
      {children}
    </motion.div>
  );
}

export default function Hero({ apiBaseUrl, backendStatus, summary }) {
  const scrollToFeed = () => {
    document.getElementById("live-feed")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <section id="hero" className="snap-panel flex flex-col items-center justify-center px-6 border-b border-ink-700 relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #e6b95a 1px, transparent 0)",
          backgroundSize: "28px 28px",
        }}
      />
      <motion.div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(420px circle at 50% 40%, rgba(230,185,90,0.34) 0%, rgba(230,185,90,0.16) 35%, rgba(230,185,90,0.05) 65%, transparent 100%)",
          filter: "blur(25px)",
        }}
        animate={{ opacity: [0.6, 0.95, 0.75, 1, 0.6] }}
        transition={{ duration: 3, times: [0, 0.2, 0.4, 0.55, 1], repeat: Infinity, ease: "easeInOut" }}
      />

      {summary && (
        <>
          <FloatingBadge className="top-[22%] left-[10%]" delay={0.9}>
            {summary.total_http_calls} real HTTP calls verified
          </FloatingBadge>
          <FloatingBadge className="top-[30%] right-[9%]" delay={1.15}>
            {summary.rules_fired?.daily_spend ?? 0}× daily-spend cap enforced
          </FloatingBadge>
          <FloatingBadge className="bottom-[26%] left-[14%]" delay={1.4}>
            up to 12 Zeuthen rounds per deal
          </FloatingBadge>
          <FloatingBadge className="bottom-[20%] right-[13%]" delay={1.65}>
            {summary.outcomes?.compliant ?? 0} negotiated deals closed
          </FloatingBadge>
        </>
      )}

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="max-w-3xl text-center space-y-6 relative"
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-ink-600 bg-ink-900/60 px-3 py-1 text-xs font-mono text-parchment-300">
          <motion.span
            animate={backendStatus === "ok" ? { opacity: [1, 0.3, 1] } : {}}
            transition={{ duration: 1.8, repeat: Infinity }}
          >
            <Radio size={12} className={backendStatus === "ok" ? "text-gold-400" : "text-parchment-500"} />
          </motion.span>
          {backendStatus === "ok" ? "backend live" : backendStatus === "error" ? "backend unreachable" : "checking backend…"}
        </div>

        <h1
          className="text-7xl sm:text-8xl font-semibold tracking-tight bg-clip-text text-transparent"
          style={{
            backgroundImage: "linear-gradient(135deg, #f3ede1 30%, #e6b95a 70%, #f0cd7c 100%)",
          }}
        >
          Setu
        </h1>
        <p className="text-lg text-parchment-300 max-w-xl mx-auto leading-relaxed">
          An agent-to-agent commerce gateway: a real x402 payment protocol, a
          deterministic Zeuthen bargaining algorithm negotiating price, and a
          trust layer that gates every transaction before money moves —
          watchable, not just claimed.
        </p>

        <motion.button
          onClick={scrollToFeed}
          whileHover={{ scale: 1.03, boxShadow: "0 0 30px rgba(230,185,90,0.25)" }}
          whileTap={{ scale: 0.98 }}
          className="mt-4 inline-flex items-center gap-2 rounded-md border border-gold-500/40 bg-gold-500/10 px-5 py-2.5 text-sm font-medium text-gold-300 hover:bg-gold-500/20 hover:border-gold-500/70 transition-colors"
        >
          See it negotiate
          <motion.span animate={{ y: [0, 3, 0] }} transition={{ duration: 1.4, repeat: Infinity }}>
            <ArrowDown size={15} />
          </motion.span>
        </motion.button>
      </motion.div>

      <div className="absolute bottom-6 text-[11px] font-mono text-parchment-500">{apiBaseUrl}</div>
    </section>
  );
}
