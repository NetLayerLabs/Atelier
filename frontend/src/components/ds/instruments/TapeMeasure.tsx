"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { cx, INSTANT, NEEDLE_SPRING, TONE, type Tone } from "../tokens";
import { frac, niceStep, tidy } from "./scale";

export type TapeMarker = { value: number; label: string; tone?: Tone };

export type TapeMeasureProps = {
  min: number;
  max: number;
  /** The reading. `null`/`undefined` = no reading yet: the tape shows without a pointer (never a guessed value). */
  value?: number | null;
  /** Accessible name, e.g. "Landed unit cost". */
  label: string;
  /** Formats the readout (and tick labels unless `tickFormat`). */
  format?: (n: number) => string;
  tickFormat?: (n: number) => string;
  /** A tolerance band, e.g. target cost range or the pre-order quantity that covers the MOQ. */
  target?: { from: number; to: number; label?: string };
  /** Reference lines: MOQ, guardrail floor, last season, a supplier's quote. */
  markers?: TapeMarker[];
  /** Distance between numbered ticks (auto: ~6 across). */
  majorStep?: number;
  /** Pointer colour (default ink). Use ok/warn/bad when the reading is judged against a guardrail. */
  tone?: Tone;
  /** Replace the readout text (e.g. "€38.20 · 12% under target"). */
  readout?: ReactNode;
  className?: string;
};

/**
 * TapeMeasure: Atelier's linear instrument, a monochrome tailor's tape with thin cm-style ticks (Scenar's gauge,
 * unrolled). Use it wherever a
 * single quantity is read against a scale: unit cost vs target, pre-orders vs MOQ, lead time vs launch date.
 * Responsive without JS (ticks are laid out in %); the pointer settles with the needle spring.
 */
export function TapeMeasure({
  min,
  max,
  value,
  label,
  format = (n) => String(tidy(n)),
  tickFormat,
  target,
  markers = [],
  majorStep,
  tone = "neutral",
  readout,
  className,
}: TapeMeasureProps) {
  const reduce = useReducedMotion();
  const major = majorStep ?? niceStep(max - min, 6);
  const majors = Math.max(1, Math.round((max - min) / major));
  const minorPer = majors <= 6 ? 10 : majors <= 12 ? 5 : 2;
  const minor = major / minorPer;
  const count = Math.round((max - min) / minor);
  const ticks = Array.from({ length: count + 1 }, (_, i) => ({ v: min + i * minor, i }));
  const tf = tickFormat ?? format;
  const has = value != null && Number.isFinite(value);
  const p = has ? frac(value, min, max) * 100 : 0;
  const t = TONE[tone];
  const out = has && (value < min || value > max);

  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={has ? value : undefined}
      aria-valuetext={has ? format(value) : "No reading"}
      className={cx("relative w-full pt-9 select-none", markers.length || target?.label ? "pb-7" : "pb-1", className)}
    >
      {/* tape body */}
      <div className="relative h-12 overflow-hidden border-t border-line-bold">
        {target && (
          <div
            aria-hidden
            className="absolute inset-y-0 border-x border-line-strong bg-paper-2"
            style={{ left: `${frac(target.from, min, max) * 100}%`, right: `${100 - frac(target.to, min, max) * 100}%` }}
          />
        )}
        <svg aria-hidden className="absolute inset-0 h-full w-full overflow-visible">
          {ticks.map(({ v, i }) => {
            const x = `${(i / count) * 100}%`;
            const isMajor = i % minorPer === 0;
            const isMid = !isMajor && minorPer % 2 === 0 && i % (minorPer / 2) === 0;
            const h = isMajor ? 17 : isMid ? 11 : 6;
            return (
              <g key={i}>
                <line x1={x} x2={x} y1={0} y2={h} stroke={isMajor ? "var(--tick-major)" : isMid ? "var(--tick)" : "var(--tick-faint)"} strokeWidth={1} />
                {isMajor && (
                  <text
                    x={x}
                    y={33}
                    textAnchor={i === 0 ? "start" : i === count ? "end" : "middle"}
                    dx={i === 0 ? 3 : i === count ? -3 : 0}
                    className="fill-fg-faint text-[10.5px] tabular-nums"
                  >
                    {tf(tidy(v))}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {markers.map((m) => (
          <span
            key={`${m.label}-${m.value}`}
            aria-hidden
            className={cx("absolute inset-y-0 w-0 border-l-[1.5px] border-dashed", TONE[m.tone ?? "neutral"].border, m.tone ? "" : "border-fg/70")}
            style={{ left: `${frac(m.value, min, max) * 100}%` }}
          />
        ))}
      </div>

      {/* marker labels under the tape */}
      {(markers.length > 0 || target?.label) && (
        <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-6">
          {target?.label && (
            <span
              className="absolute top-1.5 text-micro whitespace-nowrap text-fg-muted"
              style={{
                left: `${((frac(target.from, min, max) + frac(target.to, min, max)) / 2) * 100}%`,
                transform: `translateX(-${((frac(target.from, min, max) + frac(target.to, min, max)) / 2) * 100}%)`,
              }}
            >
              {target.label}
            </span>
          )}
          {markers.map((m) => {
            const mp = frac(m.value, min, max) * 100;
            return (
              <span
                key={`${m.label}-${m.value}`}
                className={cx("absolute top-1.5 text-micro font-medium whitespace-nowrap", m.tone ? TONE[m.tone].text : "text-fg")}
                style={{ left: `${mp}%`, transform: `translateX(-${mp}%)` }}
              >
                {m.label}
              </span>
            );
          })}
        </div>
      )}

      {/* pointer + readout */}
      {has && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute top-0 bottom-0 w-0"
          initial={{ left: "0%" }}
          animate={{ left: `${p}%` }}
          transition={reduce ? INSTANT : NEEDLE_SPRING}
        >
          <span className={cx("absolute top-9 -left-px h-12 w-px", tone === "neutral" ? "bg-fg" : t.dot)} />
          <span className={cx("absolute top-[calc(5.25rem-4px)] -left-[3.5px] size-[7px] rounded-full", tone === "neutral" ? "bg-fg" : t.dot)} />
          <span
            className={cx("absolute top-[calc(2.25rem-7px)] -left-[5px] h-0 w-0 border-x-[5px] border-t-[6px] border-x-transparent border-t-current", tone === "neutral" ? "text-fg" : t.text)}
          />
          <motion.span
            className={cx(
              "absolute top-0 inline-flex h-6 items-center gap-1 rounded-full px-2.5 font-mono text-micro font-medium whitespace-nowrap",
              tone === "neutral" ? "bg-inverse text-on-inverse" : cx(t.soft, t.text),
            )}
            initial={{ x: "0%" }}
            animate={{ x: `-${p}%` }}
            transition={reduce ? INSTANT : NEEDLE_SPRING}
          >
            {out && <span>{value < min ? "◂" : "▸"}</span>}
            {readout ?? format(value)}
          </motion.span>
        </motion.div>
      )}
    </div>
  );
}
