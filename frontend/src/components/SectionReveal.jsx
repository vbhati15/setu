import { motion } from "framer-motion";

// Shared scroll-entrance effect for every section after the hero.
//
// Trigger timing matters more than the effect itself here: with
// scroll-snap on, a section can go from "not visible" to "fully snapped
// into place" in a single fast motion. A trigger that waits for ~35%
// visibility (the old `amount: 0.35`) often doesn't fire until the snap is
// basically done, so the fade plays out on an already-settled screen and
// reads as "nothing happened". `margin` below grows the trigger zone
// *past* the bottom of the viewport, so the reveal starts while the
// section is still scrolling into view -- it now plays alongside the
// scroll instead of after it.
export default function SectionReveal({ children, className = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ amount: "some", once: true, margin: "0px 0px 200px 0px" }}
      transition={{ duration: 0.55, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
