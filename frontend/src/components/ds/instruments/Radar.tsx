"use client";

import { motion, useReducedMotion } from "framer-motion";
import { C, cx, DUR, EASE, INSTANT, TONE, type Tone } from "../tokens";
import { clamp } from "./scale";

export type RadarSeries = {
  name: string;
  /** One value per axis, 0–max. Missing data: pass null (drawn at the centre and listed as "no data"). */
  values: (number | null)[];
  tone?: Tone;
  /** Dashed outline, no fill: a comparison (last season, the brand book). */
  dashed?: boolean;
};

/**
 * Fit radar: a spider chart for 3–8 themes (customer-voice themes: fit, fabric, price, length, care…).
 * Scenar's monochrome radar: grey rings and spokes, the first series in ink over a light grey fill; comparisons dashed.
 * Axis labels carry the first series' value underneath. Keep axis names to ~12 characters.
 */
export function Radar({
  axes,
  series,
  max = 1,
  format = (n) => String(Math.round(n * 100)),
  label,
  size = 380,
  className,
}: {
  axes: string[];
  series: RadarSeries[];
  max?: number;
  format?: (n: number) => string;
  /** Accessible summary name, e.g. "Customer voice by theme". */
  label: string;
  size?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const n = axes.length;
  const VB = 400;
  const c = VB / 2;
  const R = 112;
  const pt = (i: number, f: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return { x: c + R * f * Math.cos(a), y: c + R * f * Math.sin(a) };
  };
  const poly = (f: (i: number) => number) =>
    axes
      .map((_, i) => {
        const p = pt(i, f(i));
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      })
      .join(" ");
  const first = series[0];
  return (
    <figure className={cx("w-full", className)} style={{ maxWidth: size }}>
      <svg viewBox={`0 ${VB * 0.06} ${VB} ${VB * 0.9}`} className="w-full overflow-visible" role="img" aria-label={label}>
        <desc>
          {series
            .map((s) => `${s.name}: ${axes.map((a, i) => `${a} ${s.values[i] == null ? "no data" : format(s.values[i] as number)}`).join(", ")}`)
            .join(". ")}
        </desc>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <polygon key={f} points={poly(() => f)} fill="none" stroke={f === 1 ? C.tick : C.lineStrong} strokeWidth={1} />
        ))}
        {axes.map((_, i) => {
          const p = pt(i, 1);
          return <line key={i} x1={c} y1={c} x2={p.x} y2={p.y} stroke={C.lineStrong} />;
        })}
        {series.map((s, si) => {
          const stroke = TONE[s.tone ?? (si === 0 ? "neutral" : "accent")].stroke;
          const pts = poly((i) => clamp((s.values[i] ?? 0) / max, 0, 1));
          return (
            <g key={s.name}>
              <motion.polygon
                points={pts}
                fill={s.dashed ? "none" : stroke}
                fillOpacity={s.dashed ? 0 : 0.06}
                stroke={stroke}
                strokeWidth={s.dashed ? 1.25 : 1.6}
                strokeDasharray={s.dashed ? "4 4" : undefined}
                strokeLinejoin="round"
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                style={{ transformOrigin: `${c}px ${c}px` }}
                transition={reduce ? INSTANT : { duration: DUR.settle, ease: EASE, delay: si * 0.15 }}
              />
              {!s.dashed &&
                s.values.map((v, i) => {
                  if (v == null) return null;
                  const p = pt(i, clamp(v / max, 0, 1));
                  return <circle key={i} cx={p.x} cy={p.y} r={3.4} fill={stroke} />;
                })}
            </g>
          );
        })}
        {axes.map((a, i) => {
          const p = pt(i, 1.16);
          const anchor = Math.abs(p.x - c) < 8 ? "middle" : p.x > c ? "start" : "end";
          const v = first?.values[i];
          return (
            <g key={a}>
              <text x={p.x} y={p.y - 2} textAnchor={anchor} className="fill-fg-muted text-[13px]">
                {a}
              </text>
              <text x={p.x} y={p.y + 18} textAnchor={anchor} className="tabular fill-fg text-[17px]">
                {v == null ? "-" : format(v)}
              </text>
            </g>
          );
        })}
      </svg>
      {series.length > 1 && (
        <figcaption className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-1 text-micro text-fg-muted">
          {series.map((s, si) => (
            <span key={s.name} className="inline-flex items-center gap-2">
              <span
                aria-hidden
                className={cx("h-0 w-5 border-t-2", s.dashed && "border-dashed")}
                style={{ borderColor: TONE[s.tone ?? (si === 0 ? "neutral" : "accent")].stroke }}
              />
              {s.name}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}
