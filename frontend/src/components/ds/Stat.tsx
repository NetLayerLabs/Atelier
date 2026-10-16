"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { cx, EASE, TONE, type Tone } from "./tokens";

/** A number that counts from its previous value to the new one (instant under reduced motion). */
export function CountUp({
  value,
  format = (n) => Math.round(n).toLocaleString("en-US"),
  duration = 0.8,
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
    const c = animate(mv, value, { duration, ease: EASE });
    return () => c.stop();
  }, [value, duration, mv, reduce]);
  return <motion.span className={className}>{text}</motion.span>;
}

/**
 * Stat: a big light numeral with a label (Scenar's report numerals, in tabular figures).
 * Pass `value` as text, or `count` (+ `format`) to animate. `unit` sits small after the number.
 * `delta` is a short comparison line coloured by `deltaTone`. Missing data: pass `value="-"` and a `caption`
 * that says why (never a made-up number).
 */
export function Stat({
  label,
  value,
  count,
  format,
  unit,
  delta,
  deltaTone = "neutral",
  caption,
  size = "md",
  align = "left",
  className,
}: {
  label: ReactNode;
  value?: ReactNode;
  count?: number;
  format?: (n: number) => string;
  unit?: ReactNode;
  delta?: ReactNode;
  deltaTone?: Tone;
  caption?: ReactNode;
  size?: "sm" | "md" | "lg";
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <dl className={cx("flex min-w-0 flex-col", align === "center" && "items-center text-center", className)}>
      <dt className="order-2 mt-1.5 text-small text-fg-muted">{label}</dt>
      <dd className="order-1 flex items-baseline gap-1.5 text-fg">
        <span
          className={cx(
            "tabular leading-none font-light tracking-[-0.04em]",
            size === "sm" && "text-[1.6rem]",
            size === "md" && "text-[2.4rem]",
            size === "lg" && "text-[clamp(2.8rem,6vw,4.4rem)]",
          )}
        >
          {count != null ? <CountUp value={count} format={format} /> : value}
        </span>
        {unit && <span className="text-small text-fg-muted">{unit}</span>}
      </dd>
      {delta && <dd className={cx("order-3 mt-1 text-micro font-medium", TONE[deltaTone].text)}>{delta}</dd>}
      {caption && <dd className="order-4 mt-1 text-micro text-fg-faint">{caption}</dd>}
    </dl>
  );
}

/** A row of stats separated by hairlines; 2 columns on mobile. */
export function StatGroup({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        "grid grid-cols-2 gap-x-6 gap-y-6 sm:flex sm:flex-wrap sm:gap-x-10 sm:*:border-l sm:*:border-line sm:*:pl-6 sm:*:first:border-l-0 sm:*:first:pl-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
