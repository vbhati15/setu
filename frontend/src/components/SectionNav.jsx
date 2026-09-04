import { useEffect, useState } from "react";

// Fixed dot navigation for the snap-scrolled sections -- lets a visitor jump
// straight to a section and always shows which one-screen "page" is active,
// reinforcing that only one section is meant to be in view at a time.
export default function SectionNav({ sections }) {
  const [active, setActive] = useState(sections[0]?.id);

  useEffect(() => {
    const els = sections.map((s) => document.getElementById(s.id)).filter(Boolean);
    if (els.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActive(visible.target.id);
      },
      { threshold: [0.4, 0.6] }
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav className="hidden md:flex fixed right-5 top-1/2 -translate-y-1/2 z-30 flex-col gap-3">
      {sections.map((s) => (
        <button
          key={s.id}
          onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" })}
          className="group relative flex items-center justify-end"
          aria-label={`Go to ${s.label}`}
        >
          <span className="pointer-events-none absolute right-6 whitespace-nowrap rounded border border-ink-600 bg-ink-900/90 px-2 py-1 text-[11px] font-mono text-parchment-300 opacity-0 group-hover:opacity-100 transition-opacity">
            {s.label}
          </span>
          <span
            className={`block rounded-full transition-all ${
              active === s.id ? "w-2.5 h-2.5 bg-gold-400" : "w-1.5 h-1.5 bg-ink-600 group-hover:bg-parchment-500"
            }`}
          />
        </button>
      ))}
    </nav>
  );
}
