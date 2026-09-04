import { useEffect, useState } from "react";
import { motion } from "framer-motion";

// A two-panel shutter over the whole viewport on first load. The "Setu"
// wordmark + tagline is rendered twice -- once clipped to only its top
// half inside the top panel, once clipped to only its bottom half inside
// the bottom panel -- so when closed the two halves line up into one
// complete logo, and when the panels slide apart the logo visibly splits
// and rides away with them, uncovering the real hero underneath.
const HOLD_MS = 900;
const OPEN_MS = 950;
const EASE = [0.76, 0, 0.24, 1];

function DotGrid() {
  return (
    <div
      className="pointer-events-none absolute inset-0 opacity-[0.08]"
      style={{
        backgroundImage: "radial-gradient(circle at 1px 1px, #e6b95a 1px, transparent 0)",
        backgroundSize: "28px 28px",
      }}
    />
  );
}

function Wordmark() {
  return (
    <div className="flex flex-col items-center gap-3">
      <h1
        className="text-6xl sm:text-7xl font-semibold tracking-tight bg-clip-text text-transparent"
        style={{ backgroundImage: "linear-gradient(135deg, #f3ede1 30%, #e6b95a 70%, #f0cd7c 100%)" }}
      >
        Setu
      </h1>
      <p className="text-xs font-mono uppercase tracking-[0.3em] text-parchment-500">
        Negotiate. Pay. Explain.
      </p>
    </div>
  );
}

// `pin`: which edge of the 100vh-tall content block sits flush with the
// panel's own edge, so the wordmark's center line lands exactly on the
// seam and only half of it falls inside this panel's clipped 50vh.
function PanelContent({ pin }) {
  return (
    <div className={`absolute inset-x-0 h-screen flex items-center justify-center ${pin === "top" ? "top-0" : "bottom-0"}`}>
      <Wordmark />
    </div>
  );
}

export default function ShutterIntro() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(true);

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const openTimer = setTimeout(() => setOpen(true), HOLD_MS);
    const unmountTimer = setTimeout(() => {
      setMounted(false);
      document.body.style.overflow = prevOverflow;
    }, HOLD_MS + OPEN_MS + 50);
    return () => {
      clearTimeout(openTimer);
      clearTimeout(unmountTimer);
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  if (!mounted) return null;

  return (
    <>
      <motion.div
        className="fixed top-0 inset-x-0 h-[50vh] overflow-hidden bg-ink-950 z-[100]"
        style={{ borderBottom: "1px solid rgba(217,164,65,0.3)" }}
        animate={{ y: open ? "-100%" : "0%" }}
        transition={{ duration: OPEN_MS / 1000, ease: EASE }}
      >
        <DotGrid />
        <PanelContent pin="top" />
      </motion.div>

      <motion.div
        className="fixed bottom-0 inset-x-0 h-[50vh] overflow-hidden bg-ink-950 z-[100]"
        style={{ borderTop: "1px solid rgba(217,164,65,0.3)" }}
        animate={{ y: open ? "100%" : "0%" }}
        transition={{ duration: OPEN_MS / 1000, ease: EASE }}
      >
        <DotGrid />
        <PanelContent pin="bottom" />
      </motion.div>

      <motion.div
        className="fixed top-1/2 inset-x-0 h-px -translate-y-1/2 z-[101] pointer-events-none"
        style={{ background: "linear-gradient(90deg, transparent, rgba(230,185,90,0.8), transparent)" }}
        initial={{ opacity: 0.5 }}
        animate={{ opacity: open ? [0.5, 1, 0] : 0.5 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />
    </>
  );
}
