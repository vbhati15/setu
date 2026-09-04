import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowDown, ArrowRight } from "lucide-react";

const ROTATING_LINES = ["Real payments.", "Real negotiation.", "Real guardrails."];

function FloatingBadge({ children, className, delay, onClick }) {
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: [16, 0, -6, 0] }}
      whileHover={{ scale: 1.08, borderColor: "rgba(230,185,90,0.6)", backgroundColor: "rgba(16,14,12,0.9)" }}
      whileTap={{ scale: 0.96 }}
      transition={{
        opacity: { duration: 0.6, delay },
        y: { duration: 5, delay: delay + 0.6, repeat: Infinity, ease: "easeInOut" },
      }}
      className={`hidden lg:block absolute rounded-full border border-ink-600 bg-ink-900/70 backdrop-blur px-3 py-1.5 text-[11px] font-mono text-parchment-300 cursor-pointer transition-colors ${className}`}
    >
      {children}
    </motion.button>
  );
}

function AnimatedHeadline({ text }) {
  return (
    <h1
      className="text-7xl sm:text-8xl font-semibold tracking-tight bg-clip-text text-transparent"
      style={{ backgroundImage: "linear-gradient(135deg, #f3ede1 30%, #e6b95a 70%, #f0cd7c 100%)" }}
    >
      {text.split("").map((ch, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 + i * 0.06, ease: "easeOut" }}
          className="inline-block"
        >
          {ch}
        </motion.span>
      ))}
    </h1>
  );
}

function RotatingTagline() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % ROTATING_LINES.length), 2200);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="h-5 relative w-full flex items-center justify-center overflow-hidden">
      <AnimatePresence mode="wait">
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="absolute text-xs font-mono uppercase tracking-widest text-gold-400/80"
        >
          {ROTATING_LINES[i]}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

export default function Hero({ summary }) {
  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <section
      id="hero"
      className="snap-panel flex flex-col items-center px-6 pt-24 pb-14 border-b border-ink-700 relative overflow-hidden"
    >
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
          <FloatingBadge className="top-[22%] left-[10%]" delay={0.9} onClick={() => scrollTo("audit-log")}>
            {summary.total_http_calls} real negotiations, verified
          </FloatingBadge>
          <FloatingBadge className="top-[30%] right-[9%]" delay={1.15} onClick={() => scrollTo("decision-trace")}>
            {summary.outcomes?.compliant ?? 0} deals closed, zero unauthorized
          </FloatingBadge>
          <FloatingBadge className="bottom-[26%] left-[14%]" delay={1.4} onClick={() => scrollTo("how-it-works")}>
            Every offer explained
          </FloatingBadge>
          <FloatingBadge className="bottom-[20%] right-[13%]" delay={1.65} onClick={() => scrollTo("kill-switch")}>
            Nothing moves without a reason
          </FloatingBadge>
        </>
      )}

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="max-w-3xl text-center space-y-6 relative flex-1 flex flex-col items-center justify-center"
      >
        <AnimatedHeadline text="Setu" />
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.55 }}
          className="text-lg text-parchment-300 max-w-xl mx-auto leading-relaxed"
        >
          AI agents that negotiate, pay, and explain themselves.
        </motion.p>
        <RotatingTagline />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3, ease: "easeOut" }}
        className="relative flex flex-col items-center gap-4 shrink-0"
      >
        <p className="text-sm text-parchment-400">
          Tell us your budget. Watch your AI agent get you the best deal.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <motion.button
            onClick={() => scrollTo("live-feed")}
            whileHover={{ scale: 1.03, boxShadow: "0 0 30px rgba(230,185,90,0.35)" }}
            whileTap={{ scale: 0.98 }}
            className="inline-flex items-center gap-2 rounded-md bg-gold-500 px-6 py-3 text-sm font-semibold text-ink-950 hover:bg-gold-400 transition-colors shadow-lg shadow-gold-500/20"
          >
            See it negotiate
            <motion.span animate={{ y: [0, 3, 0] }} transition={{ duration: 1.4, repeat: Infinity }}>
              <ArrowDown size={15} />
            </motion.span>
          </motion.button>

          <motion.button
            onClick={() => scrollTo("how-it-works")}
            whileHover={{ scale: 1.03, borderColor: "rgba(230,185,90,0.5)" }}
            whileTap={{ scale: 0.98 }}
            className="inline-flex items-center gap-2 rounded-md border border-ink-600 px-6 py-3 text-sm font-medium text-parchment-300 hover:text-parchment-100 transition-colors"
          >
            How it works
            <ArrowRight size={15} />
          </motion.button>
        </div>
      </motion.div>
    </section>
  );
}
