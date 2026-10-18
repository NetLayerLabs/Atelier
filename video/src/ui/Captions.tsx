import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { inter, mono, SCENE_TONE, TONE } from "../theme";
import { T } from "../timing";
import { clamp } from "./motion";

/** Narration captions: the current phrase, each word lighting up as it is spoken. */
export const Captions: React.FC<{ hidden?: (frame: number) => boolean; bottom?: number }> = ({ hidden, bottom = 96 }) => {
  const frame = useCurrentFrame();
  if (hidden?.(frame)) return null;
  const sc = T.scenes.find((s) => frame >= s.from && frame < s.from + s.durationInFrames);
  const line = T.scenes.flatMap((s) => s.lines).find((l) => frame >= l.startFrame - 4 && frame <= l.words[l.words.length - 1].end + 14);
  if (!line || !sc) return null;
  const tone = TONE[SCENE_TONE[sc.id] ?? "light"];
  const chunks: (typeof line.words)[] = [];
  let cur: typeof line.words = [];
  for (const w of line.words) {
    cur.push(w);
    if ((/[.,:;?]$/.test(w.word) && cur.length >= 4) || cur.length >= 10) { chunks.push(cur); cur = []; }
  }
  if (cur.length) chunks.push(cur);
  let shown = chunks[0];
  for (const c of chunks) if (frame >= c[0].start - 3) shown = c;
  const lastEnd = line.words[line.words.length - 1].end;
  const op = interpolate(frame, [line.startFrame - 4, line.startFrame + 4, lastEnd + 6, lastEnd + 14], [0, 1, 1, 0], clamp);
  const anchor = line.voice === "agent";
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom, display: "flex", justifyContent: "center", opacity: op, pointerEvents: "none" }}>
      <div style={{
        maxWidth: 1300, textAlign: "center", fontFamily: inter, fontSize: 30, fontWeight: 450, lineHeight: 1.35, letterSpacing: "-0.01em",
        padding: "10px 26px", borderRadius: 18,
        background: tone.bg !== "#0A0A0A" ? "rgba(255,255,255,0.82)" : "rgba(20,20,20,0.55)",
        boxShadow: tone.bg !== "#0A0A0A" ? "0 0 0 1px rgba(10,10,10,0.08), 0 10px 30px rgba(10,10,10,0.10)" : "none",
        backdropFilter: "blur(20px)",
      }}>
        {anchor ? <span style={{ fontFamily: mono, fontSize: 16, letterSpacing: "0.14em", color: "#FBBF24", marginRight: 14, verticalAlign: "middle" }}>AGENT · VOICED FROM THE APP’S REAL MESSAGE</span> : null}
        {shown.map((w, i) => (
          <span key={i} style={{ color: frame >= w.start - 2 ? tone.ink : tone.muted, opacity: frame >= w.start - 2 ? 1 : 0.55 }}>{w.word} </span>
        ))}
      </div>
    </div>
  );
};
