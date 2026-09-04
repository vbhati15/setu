import { motion } from "framer-motion";
import { Zap, Scale, ShieldCheck } from "lucide-react";
import SectionBackdrop from "./SectionBackdrop";
import SectionReveal from "./SectionReveal";

const STEPS = [
  {
    icon: Zap,
    title: "Real payments",
    body: "A real, Razorpay-adapted x402 payment protocol — every offer is a genuine HTTP 402 exchange, not a mock.",
  },
  {
    icon: Scale,
    title: "Real negotiation",
    body: "A deterministic Zeuthen bargaining algorithm negotiates price, round by round. The numbers are math, not an LLM guessing.",
  },
  {
    icon: ShieldCheck,
    title: "Real guardrails",
    body: "A trust layer — kill switch, spend caps, credential scope, replay protection — checks every transaction before money moves.",
  },
];

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="snap-panel relative overflow-hidden flex flex-col justify-center py-20 border-t border-ink-700 w-full"
    >
      <SectionBackdrop />
      <SectionReveal className="relative px-6 lg:px-16 max-w-6xl mx-auto w-full">
        <h2 className="text-3xl sm:text-4xl font-semibold text-parchment-100 mb-4">How it works</h2>
        <p className="text-base text-parchment-400 leading-relaxed mb-10 max-w-2xl">
          Two AI agents — yours and Setu's — negotiate and complete a real payment, live. Every step below is
          watchable, not just claimed.
        </p>
        <div className="grid sm:grid-cols-3 gap-6">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              whileHover={{ y: -4, borderColor: "rgba(230,185,90,0.4)" }}
              className="rounded-lg border border-ink-700 bg-ink-900/50 p-6 transition-colors"
            >
              <motion.div whileHover={{ scale: 1.15, rotate: 4 }} transition={{ type: "spring", stiffness: 300 }} className="inline-block">
                <Icon size={22} className="text-gold-400 mb-3" />
              </motion.div>
              <div className="text-lg font-medium text-parchment-100 mb-2">{title}</div>
              <p className="text-sm text-parchment-400 leading-relaxed">{body}</p>
            </motion.div>
          ))}
        </div>
      </SectionReveal>
    </section>
  );
}
