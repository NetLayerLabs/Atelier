"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { C, cx, DUR, EASE, INSTANT, TONE, type Tone } from "../tokens";
import { niceStep, tidy } from "./scale";

const line = (pts: { x: number; y: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");

/**
 * Sparkline: a small trend line (pre-orders per day, mentions per week). Stretches to its container; the
 * stroke stays crisp. The last point gets a dot. `values` with fewer than 2 points renders an empty baseline.
 */
export function Sparkline({
  values,
  label,
  tone = "neutral",
  area = true,
  height = 40,
  className,
}: {
  values: number[];
  label: string;
  tone?: Tone;
  area?: boolean;
  height?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const W = 100;
  const H = 100;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, min + 1);
  const pts = values.map((v, i) => ({ x: (i / Math.max(1, values.length - 1)) * W, y: H - ((v - min) / (max - min)) * (H - 8) - 4 }));
  const stroke = TONE[tone].stroke;
  const last = pts[pts.length - 1];
  return (
    <div role="img" aria-label={`${label}: ${values.join(", ")}`} className={cx("relative w-full", className)} style={{ height }}>
      <motion.svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full overflow-visible"
        aria-hidden
        initial={{ clipPath: "inset(-10% 100% -10% 0)" }}
        animate={{ clipPath: "inset(-10% 0% -10% 0)" }}
        transition={reduce ? INSTANT : { duration: DUR.settle, ease: EASE }}
      >
        <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} stroke={C.line} vectorEffect="non-scaling-stroke" />
        {pts.length > 1 && (
          <>
            {area && <path d={`${line(pts)} L${W} ${H} L0 ${H} Z`} fill={stroke} fillOpacity={0.07} />}
            <path d={line(pts)} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          </>
        )}
      </motion.svg>
      {last && pts.length > 1 && (
        <span
          aria-hidden
          className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface"
          style={{ left: `${last.x}%`, top: `${last.y}%`, background: stroke }}
        />
      )}
    </div>
  );
}

export type FanPoint = {
  /** x-axis label (a date, "W1"). */
  x: string;
  /** Median forecast. */
  p50: number;
  /** Outer band (e.g. p10–p90). */
  lo?: number;
  hi?: number;
  /** Inner band (e.g. p25–p75). */
  lo2?: number;
  hi2?: number;
  /** Observed value (real pre-orders so far). */
  actual?: number;
};

/**
 * FanChart: an explained forecast. Observed values in solid ink, the median forecast as a dashed ink line,
 * uncertainty as nested grey bands, and an optional threshold (the MOQ the pre-orders must cover). Responsive; axes are HTML so
 * labels never stretch. Provide only real points: the chart draws what it is given and nothing else.
 */
export function FanChart({
  points,
  label,
  threshold,
  format = (n) => String(tidy(n)),
  height = 260,
  legend = true,
  className,
}: {
  points: FanPoint[];
  label: string;
  threshold?: { value: number; label: string };
  format?: (n: number) => string;
  height?: number;
  legend?: boolean;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const W = 100;
  const H = 100;
  const all = points.flatMap((p) => [p.p50, p.lo, p.hi, p.actual].filter((v): v is number => v != null));
  if (threshold) all.push(threshold.value);
  const step = niceStep(Math.max(...all, 1), 4);
  const top = Math.ceil((Math.max(...all, 1) * 1.08) / step) * step;
  const yOf = (v: number) => H - (v / top) * H;
  const xOf = (i: number) => (i / Math.max(1, points.length - 1)) * W;
  const band = (lo: (p: FanPoint) => number | undefined, hi: (p: FanPoint) => number | undefined) => {
    const idx = points.map((p, i) => ({ p, i })).filter(({ p }) => lo(p) != null && hi(p) != null);
    if (idx.length < 2) return null;
    const upper = idx.map(({ p, i }) => ({ x: xOf(i), y: yOf(hi(p) as number) }));
    const lower = idx.map(({ p, i }) => ({ x: xOf(i), y: yOf(lo(p) as number) })).reverse();
    return `${line(upper)} ${line(lower).replace(/^M/, "L")} Z`;
  };
  const outer = band((p) => p.lo, (p) => p.hi);
  const inner = band((p) => p.lo2, (p) => p.hi2);
  const median = points.map((p, i) => ({ x: xOf(i), y: yOf(p.p50) }));
  const actual = points.map((p, i) => (p.actual != null ? { x: xOf(i), y: yOf(p.actual) } : null)).filter((v): v is { x: number; y: number } => !!v);
  const yTicks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const xLabels = points.length <= 8 ? points.map((p, i) => ({ i, x: p.x })) : [0, Math.floor((points.length - 1) / 2), points.length - 1].map((i) => ({ i, x: points[i].x }));

  return (
    <figure className={cx("w-full", className)}>
      <div className="flex gap-3">
        <div aria-hidden className="relative w-10 shrink-0 font-mono text-micro text-fg-faint" style={{ height }}>
          {yTicks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2 tabular" style={{ top: `${yOf(t)}%` }}>
              {format(t)}
            </span>
          ))}
        </div>
        <div className="relative min-w-0 flex-1" style={{ height }}>
          <motion.svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full overflow-visible"
            role="img"
            aria-label={label}
            initial={{ clipPath: "inset(-5% 100% -5% 0)" }}
            animate={{ clipPath: "inset(-5% 0% -5% 0)" }}
            transition={reduce ? INSTANT : { duration: DUR.settle, ease: EASE }}
          >
            {yTicks.map((t) => (
              <line key={t} x1={0} x2={W} y1={yOf(t)} y2={yOf(t)} stroke={t === 0 ? C.lineBold : C.line} vectorEffect="non-scaling-stroke" />
            ))}
            {outer && <path d={outer} fill={C.fg} fillOpacity={0.05} />}
            {inner && <path d={inner} fill={C.fg} fillOpacity={0.09} />}
            {threshold && (
              <line
                x1={0}
                x2={W}
                y1={yOf(threshold.value)}
                y2={yOf(threshold.value)}
                stroke={C.fg}
                strokeDasharray="6 5"
                strokeWidth={1.25}
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path d={line(median)} fill="none" stroke={C.fg} strokeWidth={1.75} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            {actual.length > 1 && (
              <path d={line(actual)} fill="none" stroke={C.fg} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            )}
          </motion.svg>
          {actual.map((p, i) => (
            <span
              key={i}
              aria-hidden
              className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-surface bg-fg"
              style={{ left: `${p.x}%`, top: `${p.y}%` }}
            />
          ))}
          {threshold && (
            <span
              aria-hidden
              className="absolute right-0 -translate-y-[calc(100%+4px)] rounded-full bg-surface px-2 text-micro font-medium text-fg shadow-e1"
              style={{ top: `${yOf(threshold.value)}%` }}
            >
              {threshold.label} · {format(threshold.value)}
            </span>
          )}
          <div aria-hidden className="absolute inset-x-0 -bottom-6 h-5 font-mono text-micro text-fg-faint">
            {xLabels.map(({ i, x }) => {
              const p = xOf(i);
              return (
                <span key={i} className="absolute whitespace-nowrap" style={{ left: `${p}%`, transform: `translateX(-${p}%)` }}>
                  {x}
                </span>
              );
            })}
          </div>
        </div>
      </div>
      {legend && (
        <figcaption className="mt-9 flex flex-wrap gap-x-5 gap-y-1.5 text-micro text-fg-muted">
          {actual.length > 0 && <LegendKey swatch={<span className="h-0.5 w-5 rounded-full bg-fg" />}>Observed</LegendKey>}
          <LegendKey swatch={<span className="w-5 border-t-2 border-dashed border-fg" />}>Median forecast</LegendKey>
          {outer && <LegendKey swatch={<span className="h-2.5 w-5 rounded-sm bg-fg/10" />}>Likely range</LegendKey>}
          {threshold && <LegendKey swatch={<span className="w-5 border-t-[1.5px] border-dashed border-fg" />}>{threshold.label}</LegendKey>}
        </figcaption>
      )}
    </figure>
  );
}

function LegendKey({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="inline-flex items-center">
        {swatch}
      </span>
      {children}
    </span>
  );
}
