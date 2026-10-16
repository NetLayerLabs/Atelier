"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { cx, DUR, EASE, INSTANT, TONE, type Tone } from "../tokens";
import { clamp } from "./scale";

/**
 * Progress bar: a 4px seam on a grey track (Scenar's metric bars). `value` 0–1, or omit it for an
 * indeterminate "working" shimmer. `stitch` draws the track as a dashed seam (for "planned", not "measured").
 * With `label`/`detail` it shows a header row: label left, detail (e.g. "45%" or "18 / 40") right.
 */
export function ProgressBar({
  value,
  label,
  detail,
  tone = "neutral",
  stitch,
  size = "md",
  className,
}: {
  value?: number | null;
  label?: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
  stitch?: boolean;
  size?: "sm" | "md";
  className?: string;
}) {
  const reduce = useReducedMotion();
  const indeterminate = value == null;
  const v = indeterminate ? 0 : clamp(value, 0, 1);
  return (
    <div className={cx("w-full", className)}>
      {(label || detail) && (
        <div className="mb-2 flex items-baseline justify-between gap-3 text-small">
          {label && <span className="text-fg-muted">{label}</span>}
          {detail && <span className="tabular font-medium text-fg">{detail}</span>}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : Math.round(v * 100)}
        aria-label={typeof label === "string" ? label : undefined}
        className={cx(
          "relative w-full overflow-hidden rounded-full",
          size === "sm" ? "h-[3px]" : "h-1",
          stitch ? "bg-transparent" : "bg-paper-2",
          indeterminate && "ds-skeleton",
        )}
      >
        {stitch && <span aria-hidden className="ds-stitch absolute inset-x-0 top-1/2 -translate-y-1/2" />}
        {!indeterminate && (
          <motion.span
            className={cx("absolute inset-y-0 left-0 rounded-full", tone === "neutral" ? "bg-fg" : TONE[tone].dot)}
            initial={{ width: "0%" }}
            animate={{ width: `${v * 100}%` }}
            transition={reduce ? INSTANT : { duration: DUR.settle, ease: EASE }}
          />
        )}
      </div>
    </div>
  );
}
