import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, XCircle, AlertTriangle, HelpCircle, ShieldCheck } from "lucide-react";
import { groupRoundsFromTrace } from "../lib/harness";
import { classifyOutcome, paise } from "../lib/rules";
import CheckoutButton from "./CheckoutButton";

// Triggers a browser download of the signed certificate JSON exactly as the
// backend produced it -- nothing reformatted or re-serialized here, so the
// downloaded file is byte-for-byte what verify_certificate.py will check.
function downloadCertificate(certificate) {
  const blob = new Blob([JSON.stringify(certificate, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `setu-certificate-${certificate.transaction_id}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Paces the typing indicator against the real LLM latency for that specific
// message (backend/app/buyer_agent/agent.py measures it around the actual
// generate_text call) -- capped so a slow call doesn't make the replay feel
// sluggish, floored so a fallback/instant message still reads as a "turn".
const TYPING_MIN_MS = 350;
const TYPING_MAX_MS = 1600;
const TYPING_DEFAULT_MS = 650;
const GAP_MS = 220;

function typingDelay(latencyMs) {
  if (latencyMs == null) return TYPING_DEFAULT_MS;
  return Math.min(TYPING_MAX_MS, Math.max(TYPING_MIN_MS, latencyMs));
}

function wait(ms, timers) {
  return new Promise((resolve) => {
    timers.push(setTimeout(resolve, ms));
  });
}

function speakerLabel(speaker) {
  return speaker === "buyer" ? "Your Agent" : "Setu";
}

function bubbleClass(speaker) {
  return speaker === "merchant"
    ? "bg-gold-500/[0.09] border border-gold-500/25 text-parchment-100"
    : "bg-ink-800/70 border border-ink-600 text-parchment-100";
}

function Avatar({ speaker }) {
  return (
    <div
      className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-medium ${
        speaker === "merchant" ? "bg-gold-500/25 text-parchment-100" : "bg-ink-600 text-parchment-200"
      }`}
    >
      {speaker === "merchant" ? "S" : "Y"}
    </div>
  );
}

function TypingIndicator({ speaker }) {
  const isMerchant = speaker === "merchant";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className={`flex items-end gap-2 ${isMerchant ? "flex-row-reverse" : ""}`}
    >
      <Avatar speaker={speaker} />
      <div className={`inline-flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm ${bubbleClass(speaker)}`}>
        <span className="text-parchment-400">{speakerLabel(speaker)} is typing</span>
        <span className="flex gap-0.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-current inline-block opacity-70"
              animate={{ y: [0, -4, 0] }}
              transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
            />
          ))}
        </span>
      </div>
    </motion.div>
  );
}

function MessageBubble({ turn, roundMeta }) {
  const isMerchant = turn.speaker === "merchant";
  const showConcessionNote = isMerchant && roundMeta;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.32, ease: "easeOut" }}
      className={`flex items-end gap-2 ${isMerchant ? "flex-row-reverse" : ""}`}
    >
      <Avatar speaker={turn.speaker} />
      <div className={`max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-3 text-sm ${bubbleClass(turn.speaker)}`}>
        <div className="text-xs font-medium mb-1 text-parchment-400">{speakerLabel(turn.speaker)}</div>
        <div className="leading-relaxed">{turn.message}</div>
        {turn.buyer_risk != null && (
          <div className="mt-2 pt-2 border-t border-white/10 text-[11px] text-gold-300/80">
            risk of no-deal: you {turn.buyer_risk.toFixed(2)} · Setu {turn.merchant_risk.toFixed(2)}
            {showConcessionNote && roundMeta.conceder && (
              <>
                {" "}
                — {roundMeta.conceder === "buyer" ? "your agent" : "Setu"} moved closer by {paise(roundMeta.concessionPaise)}
              </>
            )}
            {showConcessionNote && !roundMeta.conceder && turn.round === 1 && <> — opening offers</>}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// The raw `reason` string from the backend can carry trust-layer internals
// (rule names, "paise", credential/spend-cap jargon) meant for the
// technical decision-trace/audit views, never for this primary card -- so
// the primary flow always shows a plain-language line derived from the
// verdict, not the reason text itself.
function plainOutcomeMessage(outcome, classified) {
  if (classified.verdict === "approved") {
    return "Your agent and Setu agreed on a price.";
  }
  if (classified.verdict === "escalated") {
    return "This one needs a quick human review before it goes through.";
  }
  if (classified.verdict === "rejected") {
    return "This purchase couldn't be completed right now.";
  }
  if (outcome.reason?.includes("no catalog product matches")) {
    return "We couldn't find a match for that budget and item — try raising the budget or picking something else.";
  }
  if (outcome.reason?.includes("negotiation ended without a deal")) {
    return "Your agent and Setu couldn't agree on a price this time.";
  }
  return "No deal this time.";
}

function SummaryCard({ outcome }) {
  const [certificate, setCertificate] = useState(null);
  const classified = classifyOutcome(outcome);
  const success = outcome?.success === true;
  const Icon = success ? CheckCircle2 : classified.verdict === "escalated" ? AlertTriangle : classified.verdict === "rejected" ? XCircle : HelpCircle;
  const headline = success
    ? `Deal closed at ${paise(outcome.agreed_price_paise)}`
    : classified.verdict === "escalated"
    ? "Sent for review"
    : classified.verdict === "rejected"
    ? "Couldn't be completed"
    : "No deal";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className={`rounded-xl border-2 px-5 py-4 ${
        success ? "border-gold-500/50 bg-gold-500/[0.08]" : "border-ink-600 bg-ink-900/60"
      }`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={18} className={success ? "text-gold-400" : "text-parchment-400"} />
        <span className="font-semibold text-parchment-100">{headline}</span>
      </div>
      <div className="text-sm text-parchment-300">{plainOutcomeMessage(outcome, classified)}</div>
      {success && outcome.payment_pending && outcome.checkout_token && (
        <CheckoutButton
          checkoutToken={outcome.checkout_token}
          productName={outcome.product?.name}
          pricePaise={outcome.agreed_price_paise}
          onSuccess={(result) => setCertificate(result.certificate || null)}
        />
      )}
      {certificate && (
        <div className="mt-3 pt-3 border-t border-white/10">
          <button
            onClick={() => downloadCertificate(certificate)}
            className="inline-flex items-center gap-2 rounded-md border border-gold-500/40 bg-gold-500/10 px-3 py-1.5 text-xs font-semibold text-gold-300 hover:bg-gold-500/20 transition-colors"
          >
            <ShieldCheck size={14} />
            Download verification certificate
          </button>
          <p className="mt-2 text-xs text-parchment-500 leading-relaxed">
            This isn't just a receipt — it's mathematically provable. Download it, and verify it
            yourself, without ever trusting our server.
          </p>
        </div>
      )}
    </motion.div>
  );
}

// Replays one /negotiate response as a live two-party chat: a typing
// indicator paced by that message's real LLM latency, then the bubble.
// Driven purely by `trace` -- same component for the random-scenario button
// and the "try it yourself" form, since both just hand it a fresh response.
export default function NegotiationChat({ trace, outcome }) {
  const turns = useMemo(() => trace.filter((t) => t.speaker !== "system"), [trace]);
  // Composed from the clean `outcome.product` field rather than shown from
  // the raw backend trace text, which embeds the internal product slug and
  // a price in paise -- neither belongs in the primary flow.
  const contextLine = outcome?.product ? `Matched: ${outcome.product.name}` : null;
  const roundMetaByNumber = useMemo(() => {
    const m = new Map();
    for (const r of groupRoundsFromTrace(trace)) m.set(r.round, r);
    return m;
  }, [trace]);

  const [revealed, setRevealed] = useState([]);
  const [typingSpeaker, setTypingSpeaker] = useState(null);
  const [showContext, setShowContext] = useState(false);
  const [showSummary, setShowSummary] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const timers = [];
    setRevealed([]);
    setTypingSpeaker(null);
    setShowContext(false);
    setShowSummary(false);

    (async () => {
      if (contextLine) {
        setShowContext(true);
        await wait(280, timers);
      }
      for (const turn of turns) {
        if (cancelled) return;
        setTypingSpeaker(turn.speaker);
        await wait(typingDelay(turn.latency_ms), timers);
        if (cancelled) return;
        setTypingSpeaker(null);
        setRevealed((prev) => [...prev, turn]);
        await wait(GAP_MS, timers);
      }
      if (cancelled) return;
      await wait(320, timers);
      setShowSummary(true);
    })();

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trace]);

  return (
    <div className="space-y-3">
      <AnimatePresence>
        {showContext && contextLine && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-center text-xs text-parchment-500 pb-1"
          >
            {contextLine}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {revealed.map((turn, i) => (
          <MessageBubble key={`${turn.round}-${turn.speaker}-${i}`} turn={turn} roundMeta={roundMetaByNumber.get(turn.round)} />
        ))}
      </AnimatePresence>

      <AnimatePresence>{typingSpeaker && <TypingIndicator key="typing" speaker={typingSpeaker} />}</AnimatePresence>

      <AnimatePresence>{showSummary && outcome && <SummaryCard key="summary" outcome={outcome} />}</AnimatePresence>
    </div>
  );
}
