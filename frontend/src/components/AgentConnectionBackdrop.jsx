import { motion } from "framer-motion";

// Ambient backdrop: two connected worlds sit on opposite edges of the hero
// -- a shaded globe (stylized continents + a scattered network mesh, like
// a global-network illustration) in the app's ink/gold palette, each
// spinning slowly with its own glow, linked by a pulsing energy bridge
// that carries offer/counter-offer packets back and forth. The negotiation
// loop rendered as two connected worlds, sitting quietly behind the
// content.
const LEFT_POS = "8%";
const RIGHT_POS = "92%";

const CONTINENTS = [
  // Greenland
  "M78,8 L94,5 L100,13 L92,24 L80,21 Z",
  // North America
  "M48,20 L70,14 L86,24 L90,40 L79,45 L83,55 L75,66 L66,70 L69,80 L60,96 L50,100 L45,90 L39,74 L36,58 L39,44 L30,35 Z",
  // South America
  "M55,106 L69,100 L79,109 L81,126 L75,146 L68,166 L60,179 L55,171 L50,150 L48,130 Z",
  // Europe
  "M118,29 L136,26 L143,38 L138,48 L127,52 L117,45 L114,35 Z",
  // Africa
  "M115,55 L141,49 L156,66 L150,91 L155,111 L147,131 L139,151 L129,166 L121,155 L117,135 L111,110 L107,85 L109,65 Z",
];

const NODES = [
  [60, 30], [100, 20], [140, 32], [170, 55], [180, 92], [170, 130], [145, 165],
  [100, 181], [55, 168], [25, 135], [14, 95], [25, 55], [75, 55], [125, 50],
  [150, 92], [125, 131], [75, 141], [50, 95], [95, 75], [110, 112], [70, 100],
  [130, 80], [90, 141], [60, 60],
];

const EDGES = [
  [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10],
  [10, 11], [11, 0], [0, 12], [12, 13], [13, 2], [13, 14], [14, 3], [14, 15], [15, 6],
  [15, 16], [16, 7], [16, 17], [17, 9], [17, 11], [11, 12], [12, 18], [18, 13], [18, 19],
  [19, 15], [19, 20], [20, 17], [20, 11], [18, 21], [21, 14], [21, 22], [22, 16], [22, 9],
  [0, 18], [1, 18], [2, 14], [3, 15], [5, 16], [6, 17],
];

function Globe({ size, delay, spinDuration, light, mid, dark, id }) {
  const gradId = `sphere-${id}`;
  const clipId = `clip-${id}`;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      {/* ambient glow, breathing */}
      <motion.span
        className="absolute inset-0 rounded-full"
        style={{
          background: `radial-gradient(circle, ${mid}22 0%, transparent 70%)`,
          transform: "scale(1.5)",
        }}
        animate={{ opacity: [0.3, 0.5, 0.3] }}
        transition={{ duration: 6, delay, repeat: Infinity, ease: "easeInOut" }}
      />

      <svg viewBox="0 0 200 200" width={size} height={size} className="relative" style={{ filter: `drop-shadow(0 0 6px ${mid}33)` }}>
        <defs>
          <radialGradient id={gradId} cx="32%" cy="28%" r="75%">
            <stop offset="0%" stopColor={light} />
            <stop offset="55%" stopColor={mid} />
            <stop offset="100%" stopColor={dark} />
          </radialGradient>
          <clipPath id={clipId}>
            <circle cx="100" cy="100" r="94" />
          </clipPath>
        </defs>

        <circle cx="100" cy="100" r="94" fill={`url(#${gradId})`} stroke={mid} strokeOpacity="0.5" strokeWidth="1" />

        <motion.g
          clipPath={`url(#${clipId})`}
          animate={{ rotate: 360 }}
          transition={{ duration: spinDuration, delay, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: "100px 100px" }}
        >
          {CONTINENTS.map((d, i) => (
            <path key={i} d={d} fill={light} fillOpacity="0.22" stroke={light} strokeOpacity="0.4" strokeWidth="1" />
          ))}

          {EDGES.map(([a, b], i) => (
            <line
              key={i}
              x1={NODES[a][0]}
              y1={NODES[a][1]}
              x2={NODES[b][0]}
              y2={NODES[b][1]}
              stroke="#f3ede1"
              strokeOpacity="0.12"
              strokeWidth="0.6"
            />
          ))}
          {NODES.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="1.4" fill="#f3ede1" fillOpacity="0.4" />
          ))}
        </motion.g>
      </svg>
    </div>
  );
}

function Packet({ reverse, delay, color }) {
  return (
    <motion.span
      className="absolute top-1/2 rounded-full"
      style={{ width: 4, height: 4, backgroundColor: color, filter: `drop-shadow(0 0 3px ${color})` }}
      initial={{ opacity: 0, left: reverse ? RIGHT_POS : LEFT_POS, y: 0 }}
      animate={{
        left: reverse ? [RIGHT_POS, "50%", LEFT_POS] : [LEFT_POS, "50%", RIGHT_POS],
        y: [0, -8, 0],
        opacity: [0, 1, 0],
      }}
      transition={{ duration: 2.4, delay, repeat: Infinity, repeatDelay: 2.2, ease: "easeInOut" }}
    />
  );
}

export default function AgentConnectionBackdrop({ className = "" }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden opacity-40 ${className}`}>
      {/* the bridge: a gradient beam connecting the two globes, brightening at the midpoint */}
      <motion.div
        className="absolute top-1/2 h-px -translate-y-1/2"
        style={{
          left: LEFT_POS,
          right: LEFT_POS,
          background:
            "linear-gradient(90deg, rgba(230,185,90,0) 0%, rgba(230,185,90,0.3) 50%, rgba(230,185,90,0) 100%)",
        }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1, opacity: [0.4, 0.75, 0.4] }}
        transition={{
          scaleX: { duration: 1.2, ease: "easeOut" },
          opacity: { duration: 3.5, repeat: Infinity, ease: "easeInOut" },
        }}
      />

      <div className="absolute top-1/2 left-[8%] -translate-y-1/2">
        <Globe size={168} delay={0.2} spinDuration={70} light="#f0cd7c" mid="#b8842e" dark="#161310" id="left" />
      </div>
      <div className="absolute top-1/2 right-[8%] -translate-y-1/2">
        <Globe size={190} delay={1.4} spinDuration={82} light="#f0cd7c" mid="#b8842e" dark="#161310" id="right" />
      </div>

      <Packet reverse={false} delay={0.6} color="#f0cd7c" />
      <Packet reverse={true} delay={1.9} color="#e6b95a" />
    </div>
  );
}
