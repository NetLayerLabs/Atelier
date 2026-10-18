import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { T } from "../timing";
import { mono, SCENE_TONE, TONE } from "../theme";
import { clamp } from "./motion";
import { NetLayer } from "./NetLayer";

/** Corner furniture, kept to two pieces: the live URL bottom left, "Built by NetLayer Labs" bottom right. */
export const Chrome: React.FC<{ hideAfter?: number }> = ({ hideAfter }) => {
  const f = useCurrentFrame();
  const sc = T.scenes.find((s) => f >= s.from && f < s.from + s.durationInFrames) ?? T.scenes[T.scenes.length - 1];
  const toneId = SCENE_TONE[sc.id] ?? "light";
  const tone = TONE[toneId];
  const op = hideAfter != null ? interpolate(f, [hideAfter, hideAfter + 12], [1, 0], clamp) : 1;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={{ position: "absolute", left: 52, bottom: 32, fontFamily: mono, fontSize: 15, letterSpacing: "0.06em", color: tone.muted, opacity: op }}>atelier.netlayerlabs.com</div>
      <NetLayer height={20} dark={toneId !== "night"} labelColor={tone.muted} style={{ position: "absolute", right: 52, bottom: 30, opacity: op }} />
    </AbsoluteFill>
  );
};
