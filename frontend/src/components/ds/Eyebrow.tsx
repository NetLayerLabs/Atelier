import type { ReactNode } from "react";
import { cx, TONE, type Tone } from "./tokens";

/**
 * A status dot. `live` breathes (connected and working). 8px by default; 6px for dense rows.
 * Decorative: always pair it with text that says the same thing.
 */
export function StatusDot({
  tone = "neutral",
  live,
  size = 8,
  className,
}: {
  tone?: Tone | "faint";
  live?: boolean;
  size?: 6 | 8 | 10;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cx(
        "inline-block shrink-0 rounded-full",
        tone === "faint" ? "bg-fg-faint/60" : TONE[tone].dot,
        live && "ds-live",
        className,
      )}
    />
  );
}

/**
 * The "● label" eyebrow above every section and card title: a dot plus a small muted label in sentence case.
 * `numeral` adds a chapter numeral ("● I · The signal"). `tone` colours the dot only.
 */
export function Eyebrow({
  children,
  numeral,
  tone = "neutral",
  live,
  className,
  as: Tag = "p",
}: {
  children: ReactNode;
  numeral?: string;
  tone?: Tone | "faint";
  live?: boolean;
  className?: string;
  as?: "p" | "span" | "div";
}) {
  return (
    <Tag className={cx("inline-flex items-center gap-2 text-small text-fg-muted", className)}>
      <StatusDot tone={tone} live={live} />
      {numeral && (
        <>
          <span className="leading-none font-medium text-fg">{numeral}</span>
          <span aria-hidden className="text-fg-faint">
            ·
          </span>
        </>
      )}
      <span className="min-w-0">{children}</span>
    </Tag>
  );
}

/** Small muted label (Scenar's "Progress to goal"): field labels, card captions, instrument scales. */
export function Label({ children, className, as: Tag = "span" }: { children: ReactNode; className?: string; as?: "span" | "p" | "dt" | "div" }) {
  return <Tag className={cx("text-micro font-medium text-fg-faint", className)}>{children}</Tag>;
}

/**
 * Section heading: eyebrow, a light display title and an optional lede. `size` picks the display step:
 * xl = hero, l = chapter / page title, m = section inside a chapter.
 */
export function SectionHeading({
  eyebrow,
  title,
  lede,
  size = "l",
  actions,
  id,
  className,
  as: Tag = "h2",
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  size?: "xl" | "l" | "m";
  actions?: ReactNode;
  id?: string;
  className?: string;
  as?: "h1" | "h2" | "h3";
}) {
  return (
    <header className={cx("flex flex-col gap-5 md:flex-row md:items-end md:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow}
        <Tag
          id={id}
          className={cx(
            "text-balance text-fg",
            eyebrow ? "mt-4" : undefined,
            size === "xl" && "text-display-xl",
            size === "l" && "text-display-l",
            size === "m" && "text-display-m",
          )}
        >
          {title}
        </Tag>
        {lede && <p className="mt-4 max-w-2xl text-body-l text-pretty text-fg-muted">{lede}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/**
 * Emphasis inside a display heading, Scenar-style: no serif, no italics, no colour. The emphasised words drop to
 * muted ink (`accent` keeps them full ink, for a heading whose first half is muted instead).
 */
export function Em({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <em className={cx("not-italic", accent ? "text-fg" : "text-fg-muted")}>{children}</em>;
}
