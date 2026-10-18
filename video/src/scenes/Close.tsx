import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, inter, mono } from "../theme";
import { clamp, expo, ramp } from "../ui/motion";
import { Gauge } from "../ui/Gauge";
import { Lockup, Partner } from "../ui/Brand";
import { Words } from "../ui/Words";
import { useScene } from "./util";

/** The mark again, the line, the stack it runs on, and what was real. */
export const Close: React.FC = () => {
  const { f, rel } = useScene("close");
  const tBuilt = rel("Built");
  const v = interpolate(f, [0, 30], [0.2, 0.5], { ...clamp, easing: expo });
  const strip = ramp(f, tBuilt - 4, tBuilt + 16);
  return (
    <AbsoluteFill style={{ background: C.paper, fontFamily: inter, color: C.ink }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start", paddingTop: 120 }}>
        <Gauge size={420} value={v} draw={ramp(f, 0, 24)} labels={false} click={interpolate(f, [26, 34, 50], [0, 1, 0.4], clamp)} />
        <div style={{ marginTop: 18, opacity: ramp(f, 10, 26) }}><Lockup height={64} /></div>
        <div style={{ marginTop: 40, fontSize: 76, fontWeight: 300, letterSpacing: "-0.04em" }}>
          <Words text="Make only what's already sold." at={rel("Make")} every={3} accent={{ "sold.": C.green }} />
        </div>
        <div style={{ marginTop: 50, display: "flex", alignItems: "center", gap: 34, opacity: strip, transform: `translateY(${(1 - strip) * 16}px)` }}>
          <span style={{ fontFamily: mono, fontSize: 16, letterSpacing: "0.12em", color: C.muted }}>BUILT ON</span>
          <Partner name="amd" height={30} />
          <span style={{ width: 1, height: 34, background: C.line }} />
          <Partner name="gemma" height={34} />
          <span style={{ width: 1, height: 34, background: C.line }} />
          <Partner name="evolus" height={32} />
        </div>
        <div style={{ marginTop: 34, fontFamily: mono, fontSize: 24, letterSpacing: "0.06em", opacity: strip }}>atelier.netlayerlabs.com</div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 140, right: 140, bottom: 70, textAlign: "center", fontFamily: mono, fontSize: 15, lineHeight: 1.6, color: C.faint, opacity: ramp(f, tBuilt + 10, tBuilt + 30) }}>
        Recorded live, 17 Oct 2026 · model waits shortened · test quotes, test-card order, demo threshold of 5 · the agent's line is voiced from the app's real message
      </div>
    </AbsoluteFill>
  );
};
