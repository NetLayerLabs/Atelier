import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, inter, mono, serif } from "../theme";
import { clamp, pop, ramp } from "../ui/motion";
import { useScene } from "./util";

/** Small labels: spared the ban, not the bill. The paperwork piles up before anyone has said yes. */
export const Gap: React.FC = () => {
  const { f, rel } = useScene("gap");
  const papers = ["Tech pack", "Size chart", "Costing", "RFQ · Italian", "RFQ · English", "Quote", "Counter-offer", "Revised quote", "Purchase order"];
  const tHours = rel("hours");
  const tYes = rel("yes.");
  return (
    <AbsoluteFill style={{ background: C.linen, fontFamily: inter, color: C.ink }}>
      <div style={{ position: "absolute", left: 140, top: 190, fontSize: 92, fontWeight: 300, letterSpacing: "-0.045em", lineHeight: 1.1 }}>
        <div style={{ opacity: ramp(f, rel("spared") - 4, rel("spared") + 10) }}>
          Spared the ban. <span style={{ fontSize: 70, color: C.green }}>✓</span>
        </div>
        <div style={{ opacity: ramp(f, rel("Not") - 4, rel("Not") + 10) }}>
          <span style={{ fontFamily: serif, fontStyle: "italic", fontSize: 120 }}>Not</span> the bill. <span style={{ fontSize: 70, color: C.red }}>✗</span>
        </div>
      </div>
      {/* the pile */}
      {papers.map((p, i) => {
        const at = tHours + i * 5;
        const k = pop(f, at);
        const x = 1090 + ((i * 53) % 260) - 60, y = 640 - i * 46;
        return (
          <div key={p} style={{
            position: "absolute", left: x, top: y, width: 420, height: 92, borderRadius: 14, background: C.paper,
            boxShadow: "0 0 0 1px rgba(10,10,10,0.08), 0 14px 30px rgba(10,10,10,0.10)", display: "flex", alignItems: "center", padding: "0 26px",
            fontSize: 30, fontWeight: 400, letterSpacing: "-0.02em", opacity: k, transform: `translateY(${(1 - k) * -220}px) rotate(${((i * 37) % 9) - 4}deg)`,
          }}>
            <span style={{ fontFamily: mono, fontSize: 15, color: C.faint, marginRight: 18 }}>{String(i + 1).padStart(2, "0")}</span>{p}
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 140, top: 600, width: 760, opacity: ramp(f, tYes - 10, tYes + 6) }}>
        <div style={{ fontFamily: mono, fontSize: 20, letterSpacing: "0.14em", color: C.muted }}>CUSTOMERS WHO HAVE SAID YES</div>
        <div style={{ fontSize: 200, fontWeight: 300, letterSpacing: "-0.05em", lineHeight: 1, transform: `scale(${interpolate(f, [tYes, tYes + 10, tYes + 20], [1, 1.08, 1], clamp)})`, transformOrigin: "left center" }}>0</div>
      </div>
    </AbsoluteFill>
  );
};
