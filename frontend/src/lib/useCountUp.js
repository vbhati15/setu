import { useEffect, useRef, useState } from "react";

// Animates a number from 0 to `target` once, when `target` first becomes
// truthy/changes and the caller says it's visible. Pure display polish --
// the final value is always the real number passed in.
export function useCountUp(target, { duration = 900, start = false } = {}) {
  const [value, setValue] = useState(0);
  const rafRef = useRef(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!start || target == null) return;
    if (startedRef.current) return;
    startedRef.current = true;

    const t0 = performance.now();
    const from = 0;
    const to = target;

    function tick(now) {
      const elapsed = now - t0;
      const p = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(from + (to - from) * eased));
      if (p < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(to);
      }
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [start, target, duration]);

  return value;
}
