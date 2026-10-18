import React from "react";
import { Img, staticFile, useCurrentFrame } from "remotion";
import { C, mono } from "../theme";
import { pop } from "./motion";

/** A real email from the team's inbox for the recorded run (cropped Gmail rows; no address or name in them). */
export const Inbox: React.FC<{ file: "rfq" | "counter" | "po"; at: number; width: number; style?: React.CSSProperties }> = ({ file, at, width, style }) => {
  const f = useCurrentFrame();
  const p = pop(f, at);
  const h = file === "rfq" ? 160 : 80;
  return (
    <div style={{
      position: "absolute", width, background: C.paper, borderRadius: 18, overflow: "hidden",
      boxShadow: "0 0 0 1px rgba(10,10,10,0.08), 0 30px 70px rgba(10,10,10,0.28)",
      opacity: p, transform: `translateY(${(1 - p) * 50}px) scale(${0.96 + 0.04 * p})`, ...style,
    }}>
      <div style={{ padding: "12px 20px", fontFamily: mono, fontSize: 14, letterSpacing: "0.1em", color: C.muted, borderBottom: "1px solid rgba(10,10,10,0.08)" }}>
        INBOX · REAL EMAIL, SENT THROUGH THE EVOLUS WORKFLOW
      </div>
      <Img src={staticFile(`inbox/${file}.png`)} style={{ width, height: (width * h) / 2240, display: "block" }} />
    </div>
  );
};
