import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from "remotion";
import footage from "../footage.json";
import { inter, mono, C } from "../theme";
import { clamp, soft } from "./motion";

export interface Rect { x: number; y: number; w: number; h: number }
export interface Clip { file: string; width: number; height: number; durationFrames: number; marks?: Record<string, number>; rects?: Record<string, Rect> }
const LIB = footage as unknown as Record<string, Clip>;
export const clip = (name: string): Clip | undefined => LIB[name];

/** The page the footage was recorded at, in CSS pixels. */
export const PAGE = { w: 1920, h: 1080 };

/**
 * A browser window playing a recorded clip of the live app. The camera moves
 * from the whole page to `focus` (a rect in page CSS pixels) between frames
 * `focusAt[0]` and `focusAt[1]`, at `zoom` times the window's fit.
 */
export const Browser: React.FC<{
  name: string; url: string; width: number; left: number; top: number;
  startFrom?: number; focus?: Rect | string; zoom?: number; focusAt?: [number, number]; unfocusAt?: [number, number];
  still?: string; enter?: number; tilt?: number;
}> = ({ name, url, width, left, top, startFrom = 0, focus, zoom = 1.8, focusAt = [0, 1], unfocusAt, still, enter = 0, tilt = 0 }) => {
  const f = useCurrentFrame();
  const c = clip(name);
  const bar = 46;
  const vh = (width * PAGE.h) / PAGE.w;
  const k = width / PAGE.w;
  const rect: Rect | undefined = typeof focus === "string" ? c?.rects?.[focus] : focus;
  let p = rect ? interpolate(f, focusAt, [0, 1], { ...clamp, easing: soft }) : 0;
  if (rect && unfocusAt) p *= interpolate(f, unfocusAt, [1, 0], { ...clamp, easing: soft });
  const s = 1 + (zoom - 1) * p;
  const cx = rect ? rect.x + rect.w / 2 : PAGE.w / 2;
  const cy = rect ? rect.y + rect.h / 2 : PAGE.h / 2;
  // Keep the page edges inside the window while zoomed.
  const txFull = width / 2 - cx * k * s;
  const tyFull = vh / 2 - cy * k * s;
  const tx = Math.min(0, Math.max(width - PAGE.w * k * s, txFull)) * (p > 0 ? 1 : 0);
  const ty = Math.min(0, Math.max(vh - PAGE.h * k * s, tyFull)) * (p > 0 ? 1 : 0);
  const inP = interpolate(f, [enter, enter + 18], [0, 1], { ...clamp, easing: soft });
  return (
    <div style={{
      position: "absolute", left, top, width, height: vh + bar, borderRadius: 22, overflow: "hidden",
      background: C.white, boxShadow: "0 0 0 1px rgba(10,10,10,0.10), 0 40px 90px rgba(10,10,10,0.22)",
      opacity: inP, transform: `translateY(${(1 - inP) * 40}px) perspective(2400px) rotateX(${tilt * (1 - inP)}deg)`,
    }}>
      <div style={{ height: bar, display: "flex", alignItems: "center", gap: 9, padding: "0 18px", background: "#F6F5F2", borderBottom: "1px solid #E4E1DA" }}>
        {["#D4D2CC", "#D4D2CC", "#D4D2CC"].map((col, i) => <span key={i} style={{ width: 12, height: 12, borderRadius: 6, background: col }} />)}
        <div style={{ marginLeft: 18, flex: 1, height: 28, borderRadius: 14, background: "#ECEAE4", display: "flex", alignItems: "center", padding: "0 14px", fontFamily: mono, fontSize: 14, color: C.muted }}>{url}</div>
      </div>
      <div style={{ position: "relative", width, height: vh, overflow: "hidden", background: C.frame }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: PAGE.w, height: PAGE.h, transformOrigin: "0 0", transform: `translate(${tx}px, ${ty}px) scale(${k * s})` }}>
          {c ? (
            <OffthreadVideo src={staticFile(c.file)} startFrom={startFrom} muted style={{ width: PAGE.w, height: PAGE.h }} />
          ) : still ? (
            <Img src={staticFile(still)} style={{ width: PAGE.w, height: PAGE.h }} />
          ) : (
            <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", fontFamily: inter, color: C.muted, fontSize: 28 }}>footage “{name}” pending</AbsoluteFill>
          )}
        </div>
      </div>
    </div>
  );
};

/** Frame in the "live" recording where a named mark happened (src/footage.json), plus an offset in frames. */
export const liveAt = (mark: string, offset = 0): number => {
  const m = clip("live")?.marks?.[mark];
  return Math.max(0, (m ?? 0) + offset);
};
