import { motion, useScroll, useSpring } from "framer-motion";

// Thin progress bar tracking scroll position across the whole page -- sits
// under the header so it reads as one continuous piece of chrome rather
// than a separate widget.
export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 300, damping: 40, mass: 0.2 });

  return (
    <motion.div
      style={{ scaleX }}
      className="fixed top-14 left-0 right-0 h-[2px] bg-gold-400 origin-left z-40 pointer-events-none"
    />
  );
}
