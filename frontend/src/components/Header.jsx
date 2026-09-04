import { useEffect, useState } from "react";
import { motion } from "framer-motion";

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

function NavLink({ onClick, children }) {
  return (
    <button onClick={onClick} className="group relative py-1.5 text-parchment-300 hover:text-parchment-100 transition-colors">
      {children}
      <span className="absolute left-0 -bottom-0.5 h-px w-full origin-left scale-x-0 bg-gold-400 transition-transform duration-300 group-hover:scale-x-100" />
    </button>
  );
}

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
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <motion.button
          onClick={() => scrollTo("hero")}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          className="text-base font-semibold tracking-tight bg-clip-text text-transparent"
          style={{ backgroundImage: "linear-gradient(135deg, #f3ede1 20%, #e6b95a 100%)" }}
        >
          Setu
        </motion.button>
        <nav className="flex items-center gap-7 text-sm font-medium">
          <NavLink onClick={() => scrollTo("how-it-works")}>How it works</NavLink>
          <NavLink onClick={() => scrollTo("live-feed")}>Try it</NavLink>
        </nav>
      </div>
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
