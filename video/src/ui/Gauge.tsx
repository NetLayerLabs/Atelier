import React from "react";
import { interpolate } from "remotion";
import { C, mono } from "../theme";
import { clamp, expo } from "./motion";

/**
 * The film's motif: Atelier's tailor's gauge (the logo is an arc with one tick at the top). The needle reads from
 * GUESS (left, 0) to SOLD (12 o'clock, 0.5). `value` is the needle position 0..1 across the half circle, `draw`
 * 0..1 lights the ticks left to right, `tension` tints the filled arc from green through amber to red.
 */
export const Gauge: React.FC<{
  size: number;
  value: number;
  draw?: number;
  ink?: string;
  faint?: string;
  labels?: boolean;
  tension?: boolean;
  click?: number; // 0..1: the 12 o'clock tick "clicks" (lengthens) when the needle arrives
  style?: React.CSSProperties;
}> = ({ size, value, draw = 1, ink = C.ink, faint = C.tick, labels = true, tension = true, click = 0, style }) => {
  const W = 1000, H = 560, CX = 500, CY = 520, R = 430;
  const pt = (f: number, r: number) => {
    const a = Math.PI * (1 - f);
    return [CX + r * Math.cos(a), CY - r * Math.sin(a)];
  };
  const N = 81;
  const v = Math.max(0, Math.min(1, value));
  const ticks = Array.from({ length: N }, (_, i) => {
    const f = i / (N - 1);
    const major = i % 10 === 0;
    const top = i === (N - 1) / 2;
    const lit = interpolate(draw, [f * 0.85, f * 0.85 + 0.15], [0, 1], clamp);
    const len = (top ? 64 + 26 * click : major ? 44 : 22);
    const [x1, y1] = pt(f, R + 12);
    const [x2, y2] = pt(f, R + 12 + len);
    return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={top ? ink : major ? ink : faint} strokeOpacity={lit * (major || top ? 1 : 0.9)} strokeWidth={top ? 6 : major ? 4 : 2.4} strokeLinecap="round" />;
  });
  // the filled arc up to the needle
  const steps = 60;
  const arc: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const [x, y] = pt((v * i) / steps, R);
    arc.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  const col = tension ? (v < 0.3 ? C.green : v < 0.45 ? C.amber : v <= 0.52 ? C.green : C.red) : ink;
  const [nx, ny] = pt(v, R - 40);
  const needleIn = interpolate(draw, [0.4, 1], [0, 1], { ...clamp, easing: expo });
  return (
    <svg width={size} height={(size * H) / W} viewBox={`0 0 ${W} ${H}`} style={style}>
      <path d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`} fill="none" stroke={faint} strokeWidth={3} strokeOpacity={draw} />
      {ticks}
      <path d={arc.join(" ")} fill="none" stroke={col} strokeWidth={9} strokeLinecap="round" opacity={needleIn} />
      <line x1={CX} y1={CY} x2={nx} y2={ny} stroke={ink} strokeWidth={5} strokeLinecap="round" opacity={needleIn} />
      <circle cx={CX} cy={CY} r={13} fill={ink} opacity={needleIn} />
      {labels ? (
        <>
          <text x={CX - R - 6} y={CY + 34} textAnchor="middle" fontFamily={mono} fontSize={26} letterSpacing={3} fill={ink} opacity={draw * 0.75}>GUESS</text>
          <text x={CX} y={CY - R - 104 - 26 * click} textAnchor="middle" fontFamily={mono} fontSize={26} letterSpacing={3} fill={ink} opacity={draw * 0.75}>SOLD</text>
        </>
      ) : null}
    </svg>
  );
};
