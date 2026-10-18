import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, inter, serif } from "../theme";
import { clamp, expo, ramp } from "../ui/motion";
import { Gauge } from "../ui/Gauge";
import { Lockup } from "../ui/Brand";
import { Words } from "../ui/Words";
import { useScene } from "./util";

/** The needle leaves GUESS and finds 12 o'clock: the gauge becomes the Atelier mark. */
export const Turn: React.FC = () => {
  const { f, rel } = useScene("turn");
  const tName = rel("Atelier.");
  const swing = interpolate(f, [0, tName + 4], [0.06, 0.5], { ...clamp, easing: expo });
  const click = interpolate(f, [tName + 2, tName + 10, tName + 26], [0, 1, 0.35], clamp);
  const word = ramp(f, tName - 2, tName + 16);
  const lift = interpolate(f, [rel("Make") - 10, rel("Make") + 10], [0, -90], { ...clamp, easing: expo });
  return (
    <AbsoluteFill style={{ background: C.paper, fontFamily: inter, color: C.ink }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `translateY(${lift - 60}px)` }}>
        <Gauge size={760} value={swing} draw={ramp(f, 0, 20)} click={click} />
        <div style={{ marginTop: 26, opacity: word, transform: `translateY(${(1 - word) * 20}px)` }}>
          <Lockup height={74} />
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 820, textAlign: "center", fontSize: 72, fontWeight: 300, letterSpacing: "-0.035em" }}>
        <Words text="Make only what's already sold." at={rel("Make")} every={3} accent={{ "sold.": C.green }} />
      </div>
      <div style={{ display: "none", fontFamily: serif }} />
    </AbsoluteFill>
  );
};
