"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { C, cx, DUR, EASE, INSTANT, TONE, type Tone } from "../tokens";
import { clamp } from "./scale";

/**
 * Ring: a score / confidence ring, like Scenar's report ring. A soft grey track; the reading is a thick ink arc
 * drawn from 12 o'clock. Centre: a big light numeral and a caption. Use for forecast confidence, voice coverage,
 * workspace completeness. `value` is 0–1; null = unknown (empty stitched ring, "-").
 */
export function Ring({
  value,
  label,
  display,
  caption,
  tone = "neutral",
  size = 168,
  thickness = 5,
  className,
}: {
  value: number | null | undefined;
  /** Accessible name, e.g. "Forecast confidence". */
  label: string;
  /** Centre text; default the percentage. */
  display?: ReactNode;
  /** Small text under the numeral ("confidence", "out of 100"). */
  caption?: ReactNode;
  tone?: Tone;
  size?: number;
  thickness?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const has = value != null && Number.isFinite(value);
  const v = has ? clamp(value, 0, 1) : 0;
  const r = 50 - thickness / 2 - 1;
  const stroke = TONE[tone].stroke;
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={has ? Math.round(v * 100) : undefined}
      aria-valuetext={has ? `${Math.round(v * 100)}%` : "Unknown"}
      className={cx("relative inline-grid shrink-0 place-items-center", className)}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full -rotate-90" aria-hidden>
        <circle cx={50} cy={50} r={r} fill="none" stroke={C.paper2} strokeWidth={thickness} />
        {has && (
          <motion.circle
            cx={50}
            cy={50}
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth={thickness}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: Math.max(v, 0.001) }}
            transition={reduce ? INSTANT : { duration: DUR.settle, ease: EASE }}
          />
        )}
      </svg>
      <div className="relative flex flex-col items-center text-center">
        <span className="tabular leading-none font-light tracking-[-0.04em] text-fg" style={{ fontSize: size * 0.3 }}>
          {display ?? (has ? Math.round(v * 100) : "-")}
        </span>
        {caption && <span className="mt-2 max-w-[70%] text-micro text-fg-muted">{caption}</span>}
      </div>
    </div>
  );
}
