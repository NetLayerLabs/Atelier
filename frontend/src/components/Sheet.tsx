"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import type { PipelineRun } from "@/lib/types";
import { cx, Eyebrow, Label, type Tone } from "@/components/ds";
import { RouteTag } from "./Inference";

/**
 * The one money formatter: an amount in an ISO currency - the brand currency (see `runCurrency`), or the currency
 * a mill or the store quoted in. Without a currency the bare number is shown, never a guessed "$".
 */
export const money = (n: number, currency?: string | null, digits = 2) => {
  const plain = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits === 0 ? 0 : digits,
    maximumFractionDigits: digits,
  });
  if (!currency) return plain.format(n);
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency.toUpperCase(),
      minimumFractionDigits: digits === 0 ? 0 : undefined,
      maximumFractionDigits: digits,
    }).format(n);
  } catch {
    return `${currency.toUpperCase()} ${plain.format(n)}`;
  }
};

/** The brand currency of a run: its tech pack's, else the guardrails' (both come from the Brand workspace). */
export function runCurrency(run?: PipelineRun | null): string | undefined {
  return run?.techPack?.currency ?? run?.guardrailReport?.guardrails.currency ?? undefined;
}

/** The symbol (or code) of a currency, for input prefixes: "€", "$", "CHF". */
export function currencySymbol(currency?: string | null): string {
  if (!currency) return "";
  try {
    const part = new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() })
      .formatToParts(0)
      .find((p) => p.type === "currency");
    return part?.value ?? currency.toUpperCase();
  } catch {
    return currency.toUpperCase();
  }
}

/** Shown wherever a document did not state a value - never a default. */
export const NOT_STATED = "not stated";

export const int = (n: number) => Math.round(n).toLocaleString("en-US");

export const pct = (n: number, digits = 0) => `${(n * 100).toFixed(digits)}%`;

/** Signed money delta, e.g. "−€38.00" / "+$4.10" (true minus sign). */
export function signedMoney(n: number, currency?: string | null, digits = 2): string {
  if (Math.abs(n) < 0.005) return money(0, currency, digits);
  return `${n < 0 ? "−" : "+"}${money(Math.abs(n), currency, digits)}`;
}

/**
 * Production section heading: a "● kicker" eyebrow, a light display title and (right) badges / actions plus the
 * route that produced the content. Used by every chapter-IV panel so they read as one console.
 */
export function SheetHeading({
  kicker,
  title,
  route,
  aside,
  lede,
  tone = "neutral",
  live,
  className,
}: {
  kicker: ReactNode;
  title: ReactNode;
  /** v5: the real path that produced the content (shown as a badge). */
  route?: string;
  aside?: ReactNode;
  /** One or two sentences under the title. */
  lede?: ReactNode;
  /** Colour of the eyebrow dot (state, never decoration). */
  tone?: Tone | "faint";
  live?: boolean;
  className?: string;
}) {
  return (
    <div className={cx("mb-6 flex flex-col gap-4 sm:mb-8 md:flex-row md:items-end md:justify-between", className)}>
      <div className="min-w-0">
        <Eyebrow tone={tone} live={live}>
          {kicker}
        </Eyebrow>
        <h3 className="mt-3 text-display-m text-balance text-fg">{title}</h3>
        {lede && <p className="mt-3 max-w-2xl text-body text-pretty text-fg-muted">{lede}</p>}
      </div>
      {(aside || route) && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {aside}
          <RouteTag route={route} />
        </div>
      )}
    </div>
  );
}

/** Small dashed label for a qualifier that is not a status, e.g. "Test order", "Assumption". */
export function OutlineBadge({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border border-dashed border-line-bold px-2.5 text-micro font-medium whitespace-nowrap text-fg-muted"
    >
      {children}
    </span>
  );
}

/** Key / value rows in a definition list (mono values, right-aligned). */
export function KeyValues({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <dl className={cx("grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 text-small", className)}>
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className={cx("py-2 text-fg-muted", i > 0 && "border-t border-line")}>{k}</dt>
          <dd
            className={cx(
              "py-2 text-right font-mono text-[0.78rem] break-words text-fg",
              i > 0 && "border-t border-line",
            )}
          >
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A labelled cell: a small muted label, a value, an optional caption. For stat-like facts inside cards. */
export function Fact({
  label,
  value,
  caption,
  mono,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  caption?: ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={cx("min-w-0", className)}>
      <Label as="p">{label}</Label>
      <p className={cx("mt-1.5 break-words text-fg", mono ? "font-mono text-small" : "text-title font-normal")}>
        {value}
      </p>
      {caption && <p className="mt-0.5 text-micro text-fg-faint">{caption}</p>}
    </div>
  );
}

/** A number that counts from its previous value to the new one. */
export function CountUp({
  value,
  format = int,
  duration = 0.7,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(value);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration, ease: [0.22, 1, 0.36, 1] });
    return () => controls.stop();
  }, [value, duration, mv, reduce]);
  return <motion.span className={className}>{text}</motion.span>;
}
