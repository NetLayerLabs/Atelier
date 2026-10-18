import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, inter, mono, serif } from "../theme";
import { clamp, expo, pop, ramp } from "../ui/motion";
import { Words } from "../ui/Words";
import { useScene } from "./util";

/** The two sourced facts: the surplus, and the EU ban on destroying it. */
export const Evidence: React.FC = () => {
  const { f, rel } = useScene("evidence");
  const tNum = rel("two");
  const n = ramp(f, tNum - 4, tNum + 16);
  const tBan = rel("July");
  const stamp = pop(f, rel("destroy") - 2);
  // a field of hangers: one mark per item of a tiny sample, to give the number a body (illustration)
  const cols = 34, rows = 7;
  const fill = interpolate(f, [tNum, tNum + 50], [0, cols * rows], clamp);
  return (
    <AbsoluteFill style={{ background: C.paper, fontFamily: inter, color: C.ink }}>
      <div style={{ position: "absolute", left: 140, top: 150, fontFamily: mono, fontSize: 20, letterSpacing: "0.14em", color: C.muted, opacity: ramp(f, 0, 14) }}>2023 · ITEMS OF EXCESS STOCK</div>
      <div style={{ position: "absolute", left: 132, top: 196, fontSize: 210, fontWeight: 300, letterSpacing: "-0.06em", lineHeight: 1, opacity: n, transform: `translateY(${(1 - n) * 40}px)` }}>
        2.5–5 <span style={{ fontFamily: serif, fontStyle: "italic", fontSize: 150, letterSpacing: "-0.02em" }}>billion</span>
      </div>
      <div style={{ position: "absolute", left: 140, top: 430, fontSize: 30, fontWeight: 300, color: C.muted, opacity: n }}>
        <Words text="made, and not sold. An estimate, worth $70–140 bn in sales." at={tNum + 10} every={2} />
      </div>
      <svg style={{ position: "absolute", left: 140, top: 520 }} width={1640} height={250}>
        {Array.from({ length: cols * rows }, (_, i) => {
          const x = (i % cols) * 48, y = Math.floor(i / cols) * 34;
          const on = i < fill;
          return (
            <g key={i} transform={`translate(${x} ${y})`} opacity={on ? 0.85 : 0.08}>
              <path d="M16 6 a4 4 0 1 1 4 4 v3 L32 22 H0 L12 13" fill="none" stroke={C.ink} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
            </g>
          );
        })}
      </svg>
      <div style={{ position: "absolute", left: 140, top: 790, fontFamily: mono, fontSize: 15, letterSpacing: "0.06em", color: C.faint, opacity: n }}>
        SOURCE · MCKINSEY &amp; BOF, THE STATE OF FASHION 2025 · ILLUSTRATION: ONE HANGER IS NOT ONE ITEM
      </div>
      {/* the ban */}
      <div style={{
        position: "absolute", right: 150, top: 150, width: 520, padding: "28px 32px", borderRadius: 24, background: C.ink, color: "#FAFAFA",
        opacity: ramp(f, tBan - 6, tBan + 10), transform: `translateY(${(1 - ramp(f, tBan - 6, tBan + 10)) * 30}px)`,
      }}>
        <div style={{ fontFamily: mono, fontSize: 18, letterSpacing: "0.12em", opacity: 0.6 }}>EU · SINCE 19 JULY 2026</div>
        <div style={{ fontSize: 38, fontWeight: 300, letterSpacing: "-0.02em", marginTop: 12, lineHeight: 1.2 }}>Large companies may no longer destroy unsold clothing.</div>
        <div style={{ fontFamily: mono, fontSize: 14, opacity: 0.55, marginTop: 14 }}>REGULATION (EU) 2024/1781, ART. 25</div>
      </div>
      <div style={{
        position: "absolute", right: 250, top: 430, padding: "10px 26px", border: `6px solid ${C.red}`, color: C.red, borderRadius: 12,
        fontFamily: mono, fontSize: 54, fontWeight: 500, letterSpacing: "0.12em",
        opacity: stamp, transform: `rotate(-9deg) scale(${2.2 - 1.2 * stamp})`,
      }}>NOT ALLOWED</div>
    </AbsoluteFill>
  );
};
