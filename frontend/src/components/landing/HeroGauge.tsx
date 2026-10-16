"use client";

import { animate, motion, useInView, useMotionValue, useSpring } from "framer-motion";
import { useEffect, useRef, useSyncExternalStore } from "react";

/*
 * The landing's first screen: a giant thin-line gauge that spans the viewport, its needle drifting between
 * "agreed" and "stuck" while fragments of a negotiation surface around it - the creative director on one side,
 * a mill on the other. It is an ILLUSTRATION: the numbers are a scale, never a reading, and it says so.
 * Decorative: no pointer events, hidden from assistive tech (the caption below the hero says what it is).
 */

const W = 1000;
const H = 520;
const CX = 500;
const CY = 500;
const R = 440;
const ARC = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`;
const STATIC_VALUE = 0.62;

/** Slow calm ↔ tense loop (0 = agreed, 1 = stuck). */
const LOOP = [0.14, 0.32, 0.24, 0.55, 0.46, 0.8, 0.9, 0.64, 0.38, 0.14];

function polar(r: number, t: number) {
  const a = Math.PI * (1 - t); // t: 0 → left end, 1 → right end
  // Rounded so server and client render identical attribute strings.
  return [Math.round((CX + r * Math.cos(a)) * 100) / 100, Math.round((CY - r * Math.sin(a)) * 100) / 100] as const;
}

/** Arc from the left end to the needle (≤ 180°, so the small-arc flag always applies). */
function fillArc(t: number) {
  const [x, y] = polar(R, Math.max(0.001, t));
  return `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${x} ${y}`;
}

// A tailor's tape bent into a semicircle: 80 divisions, a long tick every 10, a mid tick every 5.
const TICKS = Array.from({ length: 81 }, (_, i) => {
  const t = i / 80;
  const major = i % 20 === 0;
  const mid = i % 10 === 0;
  const half = i % 5 === 0;
  const [x1, y1] = polar(R + 14, t);
  const [x2, y2] = polar(R + (major ? 44 : mid ? 32 : half ? 25 : 20), t);
  return { i, x1, y1, x2, y2, major, mid };
});

const LABELS = [0, 25, 50, 75, 100].map((v) => {
  const [x, y] = polar(R - 30, v / 100);
  return { v, x, y };
});

/** Illustrative lines (not a transcript): `director` = the human, black bubble; otherwise a mill, grey bubble. */
const FRAGMENTS: { text: string; director?: boolean; mobile?: boolean }[] = [
  { text: "Make it darker, cropped, more Margiela.", director: true, mobile: true },
  { text: "Our price is €58 a unit…", mobile: true },
  { text: "Can you hold that until pre-orders close?", director: true },
  { text: "Lead time is six weeks.", mobile: true },
  { text: "Only make what's sold.", director: true },
  { text: "We can sample by Friday." },
];

const RM_QUERY = "(prefers-reduced-motion: reduce)";
const subscribeRM = (cb: () => void) => {
  const mq = window.matchMedia(RM_QUERY);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
/** Reduced-motion preference that is `false` during SSR and hydration (no mismatch), then follows the OS live. */
export function useReducedMotionSafe() {
  return useSyncExternalStore(
    subscribeRM,
    () => window.matchMedia(RM_QUERY).matches,
    () => false,
  );
}

export function HeroGauge() {
  const reduce = useReducedMotionSafe();
  const rootRef = useRef<HTMLDivElement>(null);
  const needleRef = useRef<SVGGElement>(null);
  const fillRef = useRef<SVGPathElement>(null);
  const inView = useInView(rootRef, { amount: 0.05 });

  const target = useMotionValue(LOOP[0]);
  const value = useSpring(target, { stiffness: 38, damping: 11, mass: 1 });

  // Paint the needle + tinted arc straight from the spring (no React re-render per frame).
  useEffect(() => {
    const paint = (v: number) => {
      const t = Math.max(0, Math.min(1, v));
      needleRef.current?.setAttribute("transform", `translate(${CX} ${CY}) rotate(${t * 180 - 90})`);
      fillRef.current?.setAttribute("d", fillArc(t));
    };
    paint(value.get());
    return value.on("change", paint);
  }, [value]);

  useEffect(() => {
    if (reduce) {
      target.jump(STATIC_VALUE);
      value.jump(STATIC_VALUE);
      return;
    }
    if (!inView) return;
    const controls = animate(target, LOOP, { duration: 26, ease: "easeInOut", repeat: Infinity });
    return () => controls.stop();
  }, [reduce, inView, target, value]);

  const initialT = LOOP[0];

  return (
    <motion.div
      ref={rootRef}
      aria-hidden
      className="hero-gauge pointer-events-none absolute inset-0 z-0 overflow-hidden select-none"
      initial={{ opacity: 0, scale: 1.05 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={reduce ? { duration: 0 } : { duration: 1.8, ease: [0.16, 1, 0.3, 1] }}
      style={{ transformOrigin: "50% 60%" }}
    >
      <div className="hero-gauge-stage">
        <svg className="block h-auto w-full overflow-visible" viewBox={`0 0 ${W} ${H}`} fill="none">
          <defs>
            <linearGradient id="hero-tension" x1={CX - R} y1="0" x2={CX + R} y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="var(--tension-good)" />
              <stop offset="55%" stopColor="var(--tension-mid)" />
              <stop offset="100%" stopColor="var(--tension-bad)" />
            </linearGradient>
            {/* In the needle's own (rotated) frame: fades out towards the hub. */}
            <linearGradient id="hero-needle" x1="0" y1="0" x2="0" y2={-(R - 18)} gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="var(--fg)" stopOpacity="0.08" />
              <stop offset="45%" stopColor="var(--fg)" stopOpacity="0.5" />
              <stop offset="100%" stopColor="var(--fg)" stopOpacity="1" />
            </linearGradient>
          </defs>

          {/* Inner guide arcs; the middle one is a seam (the one fashion touch) */}
          <path d={`M ${CX - 330} ${CY} A 330 330 0 0 1 ${CX + 330} ${CY}`} className="hg-guide" />
          <path d={`M ${CX - 220} ${CY} A 220 220 0 0 1 ${CX + 220} ${CY}`} className="hg-seam" />
          <path d={`M ${CX - 110} ${CY} A 110 110 0 0 1 ${CX + 110} ${CY}`} className="hg-guide" />

          {TICKS.map((t) => (
            <line key={t.i} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} className={t.major ? "hg-tick-major" : t.mid ? "hg-tick-mid" : "hg-tick"} />
          ))}
          {LABELS.map((l) => (
            <text key={l.v} x={l.x} y={l.y} className="hg-num" textAnchor="middle" dominantBaseline="middle">
              {l.v}
            </text>
          ))}
          {/* the baseline the semicircle stands on */}
          <line x1={CX - R - 60} y1={CY} x2={CX - R - 20} y2={CY} className="hg-tick-mid" />
          <line x1={CX + R + 20} y1={CY} x2={CX + R + 60} y2={CY} className="hg-tick-mid" />

          {/* Track + tension fill up to the needle */}
          <path d={ARC} className="hg-track" />
          <path ref={fillRef} d={fillArc(initialT)} stroke="url(#hero-tension)" className="hg-fill" />

          {/* Needle */}
          <g ref={needleRef} transform={`translate(${CX} ${CY}) rotate(${initialT * 180 - 90})`}>
            <line x1="0" y1="0" x2="0" y2={-(R - 18)} stroke="url(#hero-needle)" className="hg-needle" />
            <circle cx="0" cy={-(R - 18)} r="3.5" className="hg-ink" />
          </g>
          <circle cx={CX} cy={CY} r="16" className="hg-hub-ring" />
          <circle cx={CX} cy={CY} r="6" className="hg-ink" />
        </svg>
      </div>

      <div className="absolute inset-0">
        {FRAGMENTS.map((f, i) => (
          <span
            key={f.text}
            className={`hg-frag ${f.director ? "hg-director" : ""} ${f.mobile ? "" : "hg-desktop"}`}
            style={{ ["--i" as string]: i }}
          >
            {f.text}
          </span>
        ))}
      </div>
    </motion.div>
  );
}
