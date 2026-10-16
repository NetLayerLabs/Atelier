// Design tokens for TypeScript (motion, chart colours). Colours themselves live in app/globals.css as CSS
// variables; always reference them as `var(--token)` so both themes work. See docs/DESIGN.md.

/** Join class names, dropping falsy parts. */
export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/** The signature easing (Scenar's): a long, soft settle. CSS: `ease-thread` / var(--ease-thread). */
export const EASE = [0.16, 1, 0.3, 1] as const;

/** Durations in seconds. */
export const DUR = {
  /** hover, press, colour changes */
  micro: 0.16,
  /** popovers, menus, tabs */
  ui: 0.28,
  /** sheets, modals */
  sheet: 0.45,
  /** section / card entrances */
  reveal: 0.7,
  /** instrument needles and rings settling on a value */
  settle: 1.1,
} as const;

/** The only spring in the system: instrument needles (a slight overshoot, like a real gauge). */
export const NEEDLE_SPRING = { type: "spring", stiffness: 70, damping: 13, mass: 1 } as const;
/**
 * Reduced motion: instruments keep the same `initial` (so the server and client render the same markup - the
 * reduced-motion preference is only known in the browser) and settle with this zero-length transition instead.
 */
export const INSTANT = { duration: 0 } as const;

/** Standard entrance: rise 20px and fade in. Use with `initial="hidden" animate="show"`. */
export const RISE = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: DUR.reveal, ease: EASE } },
} as const;

/** CSS colour references for SVG/charts. Never hard-code hex in components. */
export const C = {
  fg: "var(--fg)",
  fgMuted: "var(--fg-muted)",
  fgFaint: "var(--fg-faint)",
  line: "var(--line)",
  lineStrong: "var(--line-strong)",
  lineBold: "var(--line-bold)",
  tick: "var(--tick)",
  tickFaint: "var(--tick-faint)",
  tickMajor: "var(--tick-major)",
  fgDim: "var(--fg-dim)",
  accent: "var(--accent)",
  accentSoft: "var(--accent-soft)",
  ok: "var(--ok)",
  okSoft: "var(--ok-soft)",
  warn: "var(--warn)",
  warnSoft: "var(--warn-soft)",
  bad: "var(--bad)",
  badSoft: "var(--bad-soft)",
  surface: "var(--surface)",
  paper: "var(--paper)",
  paper2: "var(--paper-2)",
  tensionGood: "var(--tension-good)",
  tensionMid: "var(--tension-mid)",
  tensionBad: "var(--tension-bad)",
} as const;

/** The tension gradient stops (0 = good / calm, 1 = bad / heated). Matches --tension-grad. */
const TENSION: [number, [number, number, number]][] = [
  [0, [16, 185, 129]], // #10b981
  [0.55, [245, 158, 11]], // #f59e0b
  [1, [239, 68, 68]], // #ef4444
];

/** Colour at position `t` (0–1) on the tension gradient, as rgb(). For SVG strokes that must match --tension-grad. */
export function tensionColor(t: number): string {
  const x = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0));
  for (let i = 0; i < TENSION.length - 1; i++) {
    const [a, ca] = TENSION[i];
    const [b, cb] = TENSION[i + 1];
    if (x <= b) {
      const f = (x - a) / (b - a);
      const c = ca.map((n, k) => Math.round(n + (cb[k] - n) * f));
      return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
    }
  }
  return "rgb(239, 68, 68)";
}

export type Tone = "neutral" | "accent" | "ok" | "warn" | "bad";

/** Text / soft background / dot classes per tone. */
export const TONE: Record<Tone, { text: string; soft: string; dot: string; border: string; stroke: string }> = {
  neutral: { text: "text-fg-muted", soft: "bg-paper-2", dot: "bg-fg", border: "border-line-strong", stroke: C.fg },
  accent: { text: "text-accent", soft: "bg-accent-soft", dot: "bg-accent", border: "border-accent/40", stroke: C.accent },
  ok: { text: "text-ok", soft: "bg-ok-soft", dot: "bg-ok", border: "border-ok/40", stroke: C.ok },
  warn: { text: "text-warn", soft: "bg-warn-soft", dot: "bg-warn", border: "border-warn/40", stroke: C.warn },
  bad: { text: "text-bad", soft: "bg-bad-soft", dot: "bg-bad", border: "border-bad/40", stroke: C.bad },
};
