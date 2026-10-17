import type { ReactNode, SVGProps } from "react";
import { cx, TONE, type Tone } from "./tokens";

/**
 * Atelier glyphs: the app's own inline symbols, drawn in place of the stock ✓ ✗ ⚠ ✋ ↻ ★ that the agent writes
 * into its text (they render as off-theme dingbats, ✋ as a yellow emoji hand). Same language as the icons (24
 * grid, round stroke, currentColor) but set like type: a 1em square on the baseline, so a glyph sits in a sentence
 * at any size without moving the line. Each has its tone token (`tone` overrides it; "inherit" takes the text
 * colour) and is announced by a short label (role="img"); pass `decorative` only when the words beside it already
 * say the same thing. `GlyphText` swaps them into a string. Showcase: /design.
 */
export type GlyphTone = Tone | "faint" | "inherit";
export type GlyphName = "check" | "cross" | "pin" | "hand" | "retry" | "star" | "star-empty";
export type GlyphProps = Omit<SVGProps<SVGSVGElement>, "children" | "role"> & {
  /** Colour token; each glyph has its own default. "inherit" takes the text colour around it. */
  tone?: GlyphTone;
  /** What a screen reader announces. Each glyph has a short default ("Done", "Failed", …). */
  label?: string;
  /** aria-hidden: only next to text that already says what the glyph means. */
  decorative?: boolean;
  /** 1em (the size of the text around it) by default; a number is px. */
  size?: number | string;
  strokeWidth?: number;
};

const colour = (tone: GlyphTone) => (tone === "inherit" ? undefined : tone === "faint" ? "text-fg-faint" : TONE[tone].text);

function Svg({
  tone,
  label,
  decorative,
  size = "1em",
  strokeWidth = 2,
  className,
  children,
  ...rest
}: GlyphProps & { tone: GlyphTone; label: string; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label })}
      className={cx("inline-block shrink-0 align-[-0.125em]", colour(tone), className)}
      {...rest}
    >
      {children}
    </svg>
  );
}

/** Default labels. GlyphText reads them too: a glyph is silent when the next word repeats its label's first word. */
const LABEL = {
  check: "Done",
  cross: "Failed",
  pin: "Warning",
  hand: "Hand-off to a person",
  retry: "Retrying",
} as const;

function make(name: string, tone: GlyphTone, label: string, body: ReactNode) {
  function Glyph({ tone: t = tone, label: l = label, ...rest }: GlyphProps) {
    return (
      <Svg tone={t} label={l} {...rest}>
        {body}
      </Svg>
    );
  }
  Glyph.displayName = `Glyph${name}`;
  return Glyph;
}

/** ✓ ✔ · Done: a tick sewn in two stitches, broken once along the long arm (one wide gap still reads at 12px). */
export const GlyphCheck = make(
  "Check",
  "ok",
  LABEL.check,
  <path d="M3.5 12.5L9.5 18.5L12.4 15.1M14.5 12.6L21 5" strokeWidth={2.2} />,
);
/** ✗ ✘ ✕ · Failed: one cross-stitch, the top thread laid over a parted bottom one. */
export const GlyphCross = make("Cross", "bad", LABEL.cross, <path d="M19 5L5 19M5 5l4.3 4.3M14.7 14.7L19 19" />);
/** ⚠ · Warning: a dressmaker's pin (round head, stroked shaft, point above the baseline), pinned for your attention. */
export const GlyphPin = make(
  "Pin",
  "warn",
  LABEL.pin,
  <>
    <path d="M14.7 6.5L8 20.5" strokeWidth={2.4} />
    <circle cx="15.6" cy="6.2" r="4" fill="currentColor" stroke="none" />
  </>,
);
/** ✋ · Hand-off to a person: an open hand, fingers spread so it stays a hand at 12px. */
export const GlyphHand = make(
  "Hand",
  "accent",
  LABEL.hand,
  <>
    <path d="M6.4 4.9L8.4 12v3.5a5 5 0 0 0 9.6 1L19 6.6" />
    <path d="M11.1 10.9l-.5-7.8M14.1 11.1l.9-7.4M8.4 15.6l-4.2-4" />
  </>,
);
/** ↻ · Retrying: a loop of thread turning clockwise, its needle (eye and point) running ahead as the arrow. */
export const GlyphRetry = make(
  "Retry",
  "neutral",
  LABEL.retry,
  <>
    <path d="M18.58 10.11A7 7 0 1 1 10.19 5.74" />
    <path
      d="M10.03 8.74L16.43 2.56L7.67 4.1a2.6 2.6 0 0 1 2.36 4.64zM11.69 5.59l1.42-.72a.55.55 0 0 0-.5-.98l-1.42.72a.55.55 0 0 0 .5.98z"
      fill="currentColor"
      fillRule="evenodd"
      stroke="none"
    />
  </>,
);

const STAR = "M12 4.8l2.29 5.34 5.79.53-4.37 3.84L17 20.18l-5-2.98-5 2.98 1.29-5.67-4.37-3.84 5.79-.53z";

/**
 * ★ ☆ · A rating star with rounded points: filled when rated (text colour), an outline in faint ink when not, so
 * shape and not only colour tells them apart. Read after a number ("4.2★"), hence the label "stars".
 */
export function GlyphStar({
  filled = true,
  tone = filled ? "inherit" : "faint",
  label = filled ? "stars" : "empty star",
  ...rest
}: GlyphProps & { filled?: boolean }) {
  return (
    <Svg tone={tone} label={label} {...rest}>
      <path d={STAR} fill={filled ? "currentColor" : "none"} strokeWidth={filled ? 1.5 : undefined} />
    </Svg>
  );
}

/** A star rating row, announced as one phrase ("4 out of 5 stars"). `value` is rounded to whole stars. */
export function GlyphRating({ value, max = 5, className }: { value: number; max?: number; className?: string }) {
  const n = Number.isFinite(value) ? Math.max(0, Math.min(max, Math.round(value))) : 0;
  return (
    <span role="img" aria-label={`${n} out of ${max} stars`} className={cx("whitespace-nowrap", className)}>
      {Array.from({ length: max }, (_, i) => (
        <GlyphStar key={i} filled={i < n} decorative />
      ))}
    </span>
  );
}

// GlyphText ----------------------------------------------------------------------------------------------------

/** The stock characters each glyph replaces. A variation selector after one (U+FE0F / U+FE0E) goes with it. */
export const GLYPH_CHARS: Readonly<Record<string, GlyphName>> = {
  "✓": "check",
  "✔": "check",
  "✗": "cross",
  "✘": "cross",
  "✕": "cross",
  "⚠": "pin",
  "✋": "hand",
  "↻": "retry",
  "★": "star",
  "☆": "star-empty",
};

type Single = keyof typeof LABEL;
const GLYPH: Record<Single, (p: GlyphProps) => ReactNode> = {
  check: GlyphCheck,
  cross: GlyphCross,
  pin: GlyphPin,
  hand: GlyphHand,
  retry: GlyphRetry,
};
// "✋ Hand-off: …" and "↻ Retrying…" already say it: those glyphs are aria-hidden instead of read twice.
const ECHO = Object.fromEntries(
  Object.entries(LABEL).map(([k, l]) => [k, new RegExp(`^\\s*${l.split(" ")[0]}\\b`, "i")]),
) as Record<Single, RegExp>;
// Captures the character, drops a variation selector after it. split() puts the captures at odd indices.
const SPLIT = new RegExp(`([${Object.keys(GLYPH_CHARS).join("")}])[\\uFE0E\\uFE0F]?`);
// Breakable spaces only: a no-break space keeps a glyph with its word, as it kept the character.
const SPACE = /([ \t\n\r\f]+)/;

type Piece = string | { glyph: Single; decorative: boolean } | { stars: boolean[] };

/** Text runs (split at spaces), single glyphs, and runs of stars (a rating). */
function pieces(text: string): Piece[] {
  const parts = text.split(SPLIT);
  const out: Piece[] = [];
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      for (const s of part.split(SPACE)) if (s) out.push(s);
      return;
    }
    const name = GLYPH_CHARS[part];
    if (name === "star" || name === "star-empty") {
      const last = out[out.length - 1];
      if (typeof last === "object" && "stars" in last) last.stars.push(name === "star");
      else out.push({ stars: [name === "star"] });
    } else {
      out.push({ glyph: name, decorative: ECHO[name].test(parts[i + 1] ?? "") });
    }
  });
  return out;
}

function glyphNode(p: Exclude<Piece, string>, key: string) {
  if ("glyph" in p) {
    const G = GLYPH[p.glyph];
    return <G key={key} decorative={p.decorative} />;
  }
  if (p.stars.length === 1) return <GlyphStar key={key} filled={p.stars[0]} />;
  const n = p.stars.filter(Boolean).length;
  const label = p.stars.includes(false) ? `${n} out of ${p.stars.length} stars` : `${n} stars`;
  return (
    <span key={key} role="img" aria-label={label} className="whitespace-nowrap">
      {p.stars.map((filled, i) => (
        <GlyphStar key={i} filled={filled} decorative />
      ))}
    </span>
  );
}

/**
 * Renders `text` with the stock symbols in GLYPH_CHARS drawn as glyphs; every other character and all spacing
 * stay exactly as given. A glyph touching a word ("4.2★") is kept on its line with it, as the character was.
 * Pure: the same text renders the same markup on the server and the client.
 */
export function GlyphText({ text, className }: { text: string; className?: string }) {
  if (!SPLIT.test(text)) return className ? <span className={className}>{text}</span> : <>{text}</>;
  const ps = pieces(text);
  const nodes: ReactNode[] = [];
  let word: number[] = [];
  const flush = () => {
    const items = word.map((i) => {
      const p = ps[i];
      return typeof p === "string" ? p : glyphNode(p, `g${i}`);
    });
    if (word.length > 1) {
      nodes.push(
        <span key={`w${word[0]}`} className="whitespace-nowrap">
          {items}
        </span>,
      );
    } else nodes.push(...items);
    word = [];
  };
  ps.forEach((p, i) => {
    if (typeof p === "string" && SPACE.test(p)) {
      flush();
      nodes.push(p);
    } else word.push(i);
  });
  flush();
  return className ? <span className={className}>{nodes}</span> : <>{nodes}</>;
}
