"use client";

import { motion, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { useEffect, useId, type ReactNode } from "react";
import { C, cx, NEEDLE_SPRING, tensionColor, TONE, type Tone } from "../tokens";
import { arcPath, frac, polar, tidy } from "./scale";

const W = 260;
const CX = 130;
const CY = 136;
const R = 104; // track radius

const angle = (f: number) => 180 - f * 180;
/** x of the arc at fraction f, as a % of the track's width (for gradient stops that follow the arc). */
const arcX = (f: number) => ((1 - Math.cos(f * Math.PI)) / 2) * 100;

export type DialZone = { from: number; to: number; tone: Tone; label?: string };

export type DialProps = {
  min?: number;
  max?: number;
  /** The reading; null = no reading yet (dial shows, needle parked at min and dimmed). */
  value?: number | null;
  /** Accessible name, e.g. "Margin". */
  label: string;
  format?: (n: number) => string;
  /** Faint bands on the track (e.g. below floor = bad, target = ok). */
  zones?: DialZone[];
  /** A hard line on the track: the guardrail floor. Turns the arc into the tension gradient (bad → good). */
  floor?: { value: number; label?: string };
  /** Solid colour for the arc behind the needle; overrides the floor gradient. Default: ink without a floor. */
  tone?: Tone;
  /** Numbered ticks (default: min, 25%, 50%, 75%, max). */
  majors?: number[];
  /** Readout under the dial; default: the formatted value, `label` and (with a floor) a verdict pill. */
  readout?: ReactNode;
  caption?: ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
};

/**
 * Dial: Scenar's tension meter, for one ratio judged against a limit (margin vs the brand's floor, sell-through
 * vs plan). A thin semicircle with fine ticks and light numbers, an ink needle with a dot at the tip, and a thick
 * rounded arc behind the needle. With a `floor`, the arc carries the tension gradient - red below the floor,
 * amber at it, green with headroom - so the colour is the verdict. Everything else stays ink.
 */
export function Dial({
  min = 0,
  max = 100,
  value,
  label,
  format = (n) => String(tidy(n)),
  zones = [],
  floor,
  tone,
  majors,
  readout,
  caption,
  size = "md",
  className,
}: DialProps) {
  const reduce = useReducedMotion();
  const gid = `dial-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const has = value != null && Number.isFinite(value);
  const target = has ? frac(value, min, max) : 0;
  const f = useSpring(0, NEEDLE_SPRING);
  useEffect(() => {
    if (reduce) f.jump(target);
    else f.set(target);
  }, [target, reduce, f]);

  const tip = useTransform(f, (v) => polar(CX, CY, R - 18, angle(v)));
  const x2 = useTransform(tip, (p) => p.x);
  const y2 = useTransform(tip, (p) => p.y);
  const arc = useTransform(f, (v) => arcPath(CX, CY, R, 180, angle(Math.max(v, 0.0001))));

  // Verdict: how far the reading sits from trouble (0 = comfortable, 1 = below the floor).
  const ff = floor ? frac(floor.value, min, max) : 0;
  const headroom = 0.2; // 20% of the scale above the floor reads as fully "good"
  const bad = floor && has ? (value < floor.value ? 1 : Math.max(0, 0.55 * (1 - (target - ff) / headroom))) : 0;
  const verdictTone: Tone = tone ?? (floor && has ? (value >= floor.value ? (bad > 0.35 ? "warn" : "ok") : "bad") : "neutral");
  const verdictColour = tone ? TONE[tone].stroke : floor && has ? tensionColor(bad) : C.fg;
  const marks = majors ?? [0, 0.25, 0.5, 0.75, 1].map((q) => min + q * (max - min));
  const useGradient = !tone && !!floor;

  return (
    <figure
      role="meter"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={has ? value : undefined}
      aria-valuetext={has ? `${format(value)}${floor ? ` (floor ${format(floor.value)})` : ""}` : "No reading"}
      className={cx("flex flex-col items-center", size === "sm" && "w-44", size === "md" && "w-full max-w-[22rem]", size === "lg" && "w-full max-w-[30rem]", className)}
    >
      <svg viewBox={`0 0 ${W} 146`} className="w-full overflow-visible" aria-hidden>
        <defs>
          {useGradient && (
            // Left (low) = red, the floor = amber, headroom above it = green: the tension gradient, reversed for "higher is better".
            <linearGradient id={`${gid}-g`} x1={CX - R} y1="0" x2={CX + R} y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="var(--tension-bad)" />
              <stop offset={`${arcX(ff)}%`} stopColor="var(--tension-mid)" />
              <stop offset={`${arcX(Math.min(1, ff + headroom))}%`} stopColor="var(--tension-good)" />
              <stop offset="100%" stopColor="var(--tension-good)" />
            </linearGradient>
          )}
        </defs>

        {/* faint inner guide arcs, as on Scenar's hero gauge */}
        <path d={arcPath(CX, CY, 70, 180, 0)} fill="none" stroke={C.tickFaint} strokeDasharray="1.5 4" />
        <path d={arcPath(CX, CY, 36, 180, 0)} fill="none" stroke={C.tickFaint} />

        {/* zones (soft bands under the track) */}
        {zones.map((z, i) => (
          <path
            key={i}
            d={arcPath(CX, CY, R, angle(frac(z.from, min, max)), angle(frac(z.to, min, max)))}
            fill="none"
            stroke={TONE[z.tone].stroke}
            strokeOpacity={0.12}
            strokeWidth={7}
          />
        ))}

        {/* track: a soft grey well, like Scenar's meter */}
        <path d={arcPath(CX, CY, R, 180, 0)} fill="none" stroke={C.paper2} strokeWidth={7} strokeLinecap="round" />

        {/* ticks: thin, outside the track; majors longer and darker */}
        {Array.from({ length: 41 }, (_, i) => {
          const a = 180 - i * 4.5;
          const isMajor = i % 10 === 0;
          const isMid = i % 5 === 0;
          const p0 = polar(CX, CY, R + 9, a);
          const p1 = polar(CX, CY, R + (isMajor ? 20 : isMid ? 15 : 12), a);
          return (
            <line
              key={i}
              x1={p0.x}
              y1={p0.y}
              x2={p1.x}
              y2={p1.y}
              stroke={isMajor ? C.tickMajor : isMid ? C.tick : C.tickFaint}
              strokeWidth={1}
              strokeLinecap="round"
            />
          );
        })}
        {marks.map((m) => {
          const p = polar(CX, CY, R - 22, angle(frac(m, min, max)));
          return (
            <text key={m} x={p.x} y={p.y + 3.5} textAnchor="middle" className="fill-fg-faint text-[9px] tabular-nums">
              {format(tidy(m))}
            </text>
          );
        })}

        {/* floor line */}
        {floor &&
          (() => {
            const a = angle(ff);
            const p0 = polar(CX, CY, R - 7, a);
            const p1 = polar(CX, CY, R + 22, a);
            const pl = polar(CX, CY, R + 31, a);
            return (
              <g>
                <line x1={p0.x} y1={p0.y} x2={p1.x} y2={p1.y} stroke={C.fg} strokeWidth={1.25} strokeLinecap="round" />
                {floor.label && (
                  <text x={pl.x} y={pl.y} textAnchor={a > 95 ? "end" : a < 85 ? "start" : "middle"} className="fill-fg-muted text-[9px] font-medium">
                    {floor.label}
                  </text>
                )}
              </g>
            );
          })()}

        {/* value arc + needle */}
        {has && (
          <motion.path
            d={arc}
            fill="none"
            stroke={useGradient ? `url(#${gid}-g)` : verdictColour}
            strokeWidth={7}
            strokeLinecap="round"
          />
        )}
        <g opacity={has ? 1 : 0.25}>
          <motion.line x1={CX} y1={CY} x2={x2} y2={y2} stroke={C.fg} strokeWidth={1.75} strokeLinecap="round" />
          <motion.circle cx={x2} cy={y2} r={2.6} fill={C.fg} />
        </g>
        <circle cx={CX} cy={CY} r={6} fill={C.fg} />
        <circle cx={CX} cy={CY} r={2} fill={C.surface} />
      </svg>
      <figcaption className="mt-2 flex flex-col items-center text-center">
        {readout ?? (
          <>
            <span className={cx("tabular leading-none font-light tracking-[-0.04em] text-fg", size === "sm" ? "text-[1.7rem]" : "text-[2.9rem]")}>
              {has ? format(value) : "-"}
            </span>
            <span className="mt-2 text-micro font-medium text-fg-muted">{label}</span>
            {floor && has && (
              <span
                className={cx("mt-3 inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-micro font-medium", TONE[verdictTone].soft, TONE[verdictTone].text)}
              >
                <span aria-hidden className="size-1.5 rounded-full" style={{ background: verdictColour }} />
                {value >= floor.value ? "Above floor" : "Below floor"}
              </span>
            )}
          </>
        )}
        {caption && <span className="mt-1.5 text-micro text-fg-faint">{caption}</span>}
      </figcaption>
    </figure>
  );
}
