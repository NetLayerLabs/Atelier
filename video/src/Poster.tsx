import React from "react";
import { AbsoluteFill } from "remotion";
import { C, inter, mono, serif } from "./theme";
import { Gauge } from "./ui/Gauge";
import { Lockup, Partner } from "./ui/Brand";

/** The thumbnail: the mark at 12 o'clock, the line, the stack. */
export const Poster: React.FC = () => (
  <AbsoluteFill style={{ background: C.paper, fontFamily: inter, color: C.ink, alignItems: "center", justifyContent: "center" }}>
    <Gauge size={560} value={0.5} labels={false} click={0.6} />
    <div style={{ marginTop: 20 }}><Lockup height={70} /></div>
    <div style={{ marginTop: 40, fontSize: 96, fontWeight: 300, letterSpacing: "-0.045em" }}>
      Make only what&rsquo;s already <span style={{ fontFamily: serif, fontStyle: "italic", color: C.green }}>sold.</span>
    </div>
    <div style={{ marginTop: 44, display: "flex", alignItems: "center", gap: 30 }}>
      <span style={{ fontFamily: mono, fontSize: 18, letterSpacing: "0.12em", color: C.muted }}>BUILT ON</span>
      <Partner name="amd" height={30} />
      <Partner name="gemma" height={34} />
      <Partner name="evolus" height={32} />
    </div>
  </AbsoluteFill>
);
