"use client";

import {
  animate,
  cubicBezier,
  motion,
  useInView,
  useMotionValue,
  usePageInView,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { EASE } from "@/components/ds";
import { prefersReducedMotion } from "../ui";
import { useInViewPause, useReducedMotionSafe } from "./motion";

/*
 * The landing's first screen: a giant thin-line gauge that spans the viewport, its needle drifting between
 * "agreed" and "stuck" while fragments of a negotiation surface around it - the creative director on one side,
 * a mill on the other. It is an ILLUSTRATION: the numbers are a scale, never a reading, and it says so.
 * Decorative: no pointer events, hidden from assistive tech (the caption below the hero says what it is).
 *
 * Ignition (once per page load, only if the gauge is on screen at hydration and motion is allowed): the needle swings
 * from 0 to 12 o'clock while the ticks light in two sweeps that meet there, the top tick clicks, and for a beat the
 * gauge is the Atelier mark - an arc with one tick at the top. Then the needle eases into its drift. The server HTML,
 * no-JS and reduced motion rest on the mark.
 */

const W = 1000;
const H = 520;
const CX = 500;
const CY = 500;
const R = 440;
const ARC = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`;

/** 12 o'clock: the needle upright under the top tick, the mark. */
const MARK = 0.5;
/** Slow calm ↔ tense drift (0 = agreed, 1 = stuck): the old loop (0.14 → … → 0.14) entered at the mark. */
const DRIFT = [MARK, 0.46, 0.8, 0.9, 0.64, 0.38, 0.14, 0.32, 0.24, 0.55, MARK];
/** The old pace: 26 s for nine legs. */
const DRIFT_S = (26 / 9) * (DRIFT.length - 1);

/** Ignition, in ms: the swing to the mark, the beat the mark holds, one tick lighting, the top tick's click. */
const SWING_MS = 1100;
const HOLD_MS = 1200;
const LIGHT_MS = 450;
const CLICK_MS = 600;
/** The needle's spring: stiff enough to visibly land on 12 o'clock as the swing ends; the slow drift barely notices. */
const NEEDLE = { stiffness: 120, damping: 21, mass: 1 };
const THREAD = `cubic-bezier(${EASE.join(", ")})`;

/** Once per page load: a remount (back from the workspace) starts on the mark. */
let ignited = false;

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
  return { i, t, x1, y1, x2, y2, major, mid };
});
const TOP = 40; // the 12 o'clock tick

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

/**
 * When (ms) the needle - the spring chasing the swing - first reaches each tick of the left half (index 0-40), so
 * that half lights as the needle passes it. Integrated in 1 ms steps; the top tick lands with the swing.
 */
function passTimes(): number[] {
  const swing = cubicBezier(...EASE);
  const at: number[] = [];
  let x = 0;
  let v = 0;
  for (let ms = 0; ms < SWING_MS && at.length < TOP; ms++) {
    const goal = MARK * swing(ms / SWING_MS);
    v += (-NEEDLE.stiffness * (x - goal) - NEEDLE.damping * v) / NEEDLE.mass / 1000;
    x += v / 1000;
    while (at.length < TOP && x >= at.length / 80) at.push(ms);
  }
  while (at.length <= TOP) at.push(SWING_MS);
  return at;
}

/**
 * Lights the scale with WAAPI, fill "backwards": each element waits unlit, lights, then belongs to the stylesheet
 * again. The left half lights under the needle, the right half closes in from the far end on the mirrored beat, and
 * the top tick clicks as the needle lands: it springs out from its arc end in full ink, holds the mark, then lets go.
 */
function lightScale(svg: SVGSVGElement, top: SVGLineElement): Animation[] {
  const pass = passTimes();
  const lit: Animation[] = [];
  svg.querySelectorAll<SVGElement>("[data-sweep]").forEach((el) => {
    const t = Number(el.dataset.sweep);
    const delay = pass[Math.round(Math.min(t, 1 - t) * 80)];
    lit.push(el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: LIGHT_MS, delay, easing: THREAD, fill: "backwards" }));
  });
  // From the landing: the click (out to 1.3 in full ink and back), the ink held for the mark, then released over
  // another click's length as the drift begins.
  const total = HOLD_MS + CLICK_MS;
  const ink = { opacity: 1, stroke: "var(--fg)", strokeWidth: "1.5px" };
  lit.push(
    top.animate(
      [
        { ...ink, opacity: 0, transform: "scaleY(1)" },
        { ...ink, transform: "scaleY(1.3)", offset: 70 / total, easing: THREAD },
        { ...ink, transform: "scaleY(1)", offset: CLICK_MS / total },
        { ...ink, transform: "scaleY(1)", offset: HOLD_MS / total, easing: THREAD },
        { opacity: 1, transform: "scaleY(1)", stroke: "var(--tick-major)", strokeWidth: "1px" },
      ],
      { duration: total, delay: SWING_MS, fill: "backwards" },
    ),
  );
  return lit;
}

export function HeroGauge() {
  const reduce = useReducedMotionSafe();
  const rootRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const topRef = useRef<SVGLineElement>(null);
  const needleRef = useRef<SVGGElement>(null);
  const fillRef = useRef<SVGPathElement>(null);
  const inView = useInView(rootRef, { amount: 0.05 });
  const pageVisible = usePageInView();
  useInViewPause(rootRef); // the bubbles' CSS loop holds still off-screen
  // The ignition is over (or was skipped): the drift may run.
  const [settled, setSettled] = useState(false);

  const fade = useMotionValue(0);
  const target = useMotionValue(MARK);
  const value = useSpring(target, NEEDLE);

  // Recede: as the hero scrolls away the gauge sinks, shrinks a little and dims while the copy scrolls normally.
  // Only from md and with motion allowed (globals.css pins .hg-recede otherwise).
  const { scrollYProgress } = useScroll({ target: rootRef, offset: ["start start", "end start"] });
  const sink = useTransform(scrollYProgress, [0, 1], ["0vh", "10vh"]);
  const shrink = useTransform(scrollYProgress, [0, 1], [1, 0.95]);
  // A function, not a range: framer would hand a range-mapped opacity to a ViewTimeline, and the hero's clipping
  // (overflow: hidden, so a scroll container) would hold that timeline at 0 - the gauge would never dim.
  const dim = useTransform(scrollYProgress, (p) => 1 - 0.65 * Math.min(1, Math.max(0, p)));

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

  // Ignition, right after hydration. The preference is read directly: the hook still reports the server's `false`
  // during this first pass.
  useEffect(() => {
    const root = rootRef.current;
    const svg = svgRef.current;
    const top = topRef.current;
    if (!root || !svg || !top) return;
    const box = root.getBoundingClientRect();
    const seen = box.bottom > 0 && box.top < window.innerHeight && document.visibilityState === "visible";
    if (ignited || !seen || prefersReducedMotion()) {
      fade.jump(1);
      setSettled(true);
      return;
    }
    ignited = true;
    let finished = false;
    target.jump(0);
    value.jump(0);
    const runs = [
      animate(fade, 1, { duration: 0.8, ease: EASE }), // opacity only: a scale would fight the sweep
      animate(target, MARK, { duration: SWING_MS / 1000, ease: EASE }),
    ];
    const lit = lightScale(svg, top);
    const timer = window.setTimeout(() => {
      finished = true;
      setSettled(true);
    }, SWING_MS + HOLD_MS);
    return () => {
      // Unmounted mid-ignition (or React's dev double mount): undo it so the next mount can play it.
      window.clearTimeout(timer);
      runs.forEach((r) => r.stop());
      lit.forEach((a) => a.cancel());
      if (!finished) ignited = false;
    };
  }, [fade, target, value]);

  // The drift: from the mark, paused while off-screen or the tab is hidden, resumed where it stopped.
  const drift = useRef<ReturnType<typeof animate> | null>(null);
  useEffect(() => {
    if (reduce) {
      drift.current?.stop();
      drift.current = null;
      target.jump(MARK);
      value.jump(MARK);
      return;
    }
    if (!settled) return;
    if (!inView || !pageVisible) drift.current?.pause();
    else if (drift.current) drift.current.play();
    else drift.current = animate(target, DRIFT, { duration: DRIFT_S, ease: "easeInOut", repeat: Infinity });
  }, [reduce, settled, inView, pageVisible, target, value]);
  useEffect(() => () => drift.current?.stop(), []);

  return (
    <motion.div
      ref={rootRef}
      aria-hidden
      className="hero-gauge pointer-events-none absolute inset-0 z-0 overflow-hidden select-none"
      style={{ opacity: fade }}
    >
      <motion.div className="hg-recede absolute inset-0" style={{ y: sink, scale: shrink, opacity: dim }}>
        <div className="hero-gauge-stage">
          <svg ref={svgRef} className="block h-auto w-full overflow-visible" viewBox={`0 0 ${W} ${H}`} fill="none">
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

            {/* data-sweep: where on the scale each mark sits, so the ignition can light it as the needle passes */}
            {TICKS.map((t) =>
              t.i === TOP ? (
                <line key={t.i} ref={topRef} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} className="hg-tick-major hg-top" />
              ) : (
                <line
                  key={t.i}
                  x1={t.x1}
                  y1={t.y1}
                  x2={t.x2}
                  y2={t.y2}
                  data-sweep={t.t}
                  className={t.major ? "hg-tick-major" : t.mid ? "hg-tick-mid" : "hg-tick"}
                />
              ),
            )}
            {/* the baseline the semicircle stands on */}
            <line x1={CX - R - 60} y1={CY} x2={CX - R - 20} y2={CY} data-sweep={0} className="hg-tick-mid" />
            <line x1={CX + R + 20} y1={CY} x2={CX + R + 60} y2={CY} data-sweep={1} className="hg-tick-mid" />

            {/* Track + tension fill up to the needle */}
            <path d={ARC} className="hg-track" />
            <path ref={fillRef} d={fillArc(MARK)} stroke="url(#hero-tension)" className="hg-fill" />

            {/* Needle */}
            <g ref={needleRef} transform={`translate(${CX} ${CY}) rotate(${MARK * 180 - 90})`}>
              <line x1="0" y1="0" x2="0" y2={-(R - 18)} stroke="url(#hero-needle)" className="hg-needle" />
              <circle cx="0" cy={-(R - 18)} r="3.5" className="hg-ink" />
            </g>
            {/* Scale numbers above the needle, knocked out of it (it rests across "50" on the mark) */}
            {LABELS.map((l) => (
              <text
                key={l.v}
                x={l.x}
                y={l.y}
                data-sweep={l.v / 100}
                className="hg-num"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {l.v}
              </text>
            ))}
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
    </motion.div>
  );
}
