// Same dot-grid look as Hero, at rest -- static and subtle, not animated,
// so it never risks staying invisible on a section taller than the
// viewport (whileInView-based fades were unreliable there).
export default function SectionBackdrop() {
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
