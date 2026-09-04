import { useEffect, useState } from "react";

export default function Header() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 inset-x-0 z-40 transition-all duration-300 ${
        scrolled ? "backdrop-blur-md bg-ink-950/80 shadow-[0_1px_24px_rgba(0,0,0,0.35)]" : "bg-transparent"
      }`}
    >
      <div className="h-14" />
      <div
        className="h-px w-full transition-opacity duration-300"
        style={{
          backgroundImage: "linear-gradient(90deg, transparent, rgba(230,185,90,0.4), transparent)",
          opacity: scrolled ? 1 : 0.4,
        }}
      />
    </header>
  );
}
