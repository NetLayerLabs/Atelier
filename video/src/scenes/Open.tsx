import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, inter, mono, serif } from "../theme";
import { clamp, expo, pop } from "../ui/motion";
import { Gauge } from "../ui/Gauge";
import { Words } from "../ui/Words";
import { useScene } from "./util";

/** Cold open on the joke the whole film answers: fashion's business model is one word. */
export const Open: React.FC = () => {
  const { f, rel } = useScene("open");
  const tGuess = rel("Guess.");
  const g = interpolate(f, [tGuess - 2, tGuess + 10], [0, 1], { ...clamp, easing: expo });
  // the needle can't settle: it wobbles around GUESS
  const wobble = 0.06 + 0.05 * Math.sin(f / 3.2) + 0.03 * Math.sin(f / 1.7);
  const tDesign = rel("Design");
  const lineOut = interpolate(f, [tDesign - 8, tDesign], [1, 0], clamp);
  const steps: [string, string, number][] = [
    ["01", "Design it.", rel("Design")],
    ["02", "Make hundreds.", rel("hundreds")],
    ["03", "Hope.", rel("Hope")],
  ];
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: inter, color: "#FAFAFA" }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start", paddingTop: 170, opacity: lineOut }}>
        <div style={{ fontSize: 64, fontWeight: 300, letterSpacing: "-0.03em", textAlign: "center", lineHeight: 1.2 }}>
          <Words text="Fashion has a business model." at={rel("Fashion")} every={3} />
          <br />
          <span style={{ color: "rgba(250,250,250,0.55)" }}><Words text="It fits in one word." at={rel("It")} every={3} /></span>
        </div>
        <div style={{
          marginTop: 30, fontFamily: serif, fontStyle: "italic", fontSize: 250, lineHeight: 1, letterSpacing: "-0.02em",
          opacity: g, transform: `scale(${0.6 + 0.4 * g}) rotate(${(1 - g) * -8}deg)`, color: "#FBBF24",
        }}>Guess.</div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 60, display: "flex", justifyContent: "center", opacity: interpolate(f, [tGuess, tGuess + 14], [0, 1], clamp) * lineOut }}>
        <Gauge size={640} value={wobble} draw={interpolate(f, [tGuess, tGuess + 30], [0, 1], clamp)} ink="#FAFAFA" faint="rgba(250,250,250,0.28)" />
      </div>
      {/* the season, in three steps */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 26, flexDirection: "row" }}>
        {steps.map(([n, t, at], i) => {
          const p = pop(f, at);
          const last = i === 2;
          return (
            <div key={n} style={{
              width: 470, height: 330, borderRadius: 28, padding: "34px 36px", display: "flex", flexDirection: "column", justifyContent: "space-between",
              background: last ? "#FAFAFA" : "rgba(250,250,250,0.06)", color: last ? C.ink : "#FAFAFA",
              border: last ? "none" : "1px solid rgba(250,250,250,0.16)",
              opacity: p, transform: `translateY(${(1 - p) * 60}px) rotate(${last ? (1 - p) * 6 - 2 : 0}deg)`,
            }}>
              <div style={{ fontFamily: mono, fontSize: 20, letterSpacing: "0.14em", opacity: 0.6 }}>STEP {n}</div>
              <div style={{ fontSize: last ? 0 : 58, fontWeight: 300, letterSpacing: "-0.03em" }}>{last ? null : t}</div>
              {last ? <div style={{ fontFamily: serif, fontStyle: "italic", fontSize: 130, lineHeight: 0.9, color: C.red }}>Hope.</div> : null}
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
