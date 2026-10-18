import React from "react";
import { Img, staticFile } from "remotion";

/** The Atelier lockup / mark: the app's PNGs used as a mask painted in `color` (as ds/Logo.tsx does). */
export const Lockup: React.FC<{ height: number; color?: string; mark?: boolean; style?: React.CSSProperties }> = ({ height, color = "#0A0A0A", mark, style }) => {
  const src = staticFile(mark ? "brand/atelier-mark.png" : "brand/atelier-header.png");
  const w = mark ? height : Math.round((height * 1200) / 251);
  const m = `url(${src}) center / contain no-repeat`;
  return <div style={{ width: w, height, background: color, mask: m, WebkitMask: m, ...style }} />;
};

/** Official partner marks (frontend/public/brand/partners, sourced from each company's own site), single colour. */
export const Partner: React.FC<{ name: "amd" | "gemma" | "evolus"; height: number; color?: string }> = ({ name, height, color = "#0A0A0A" }) => {
  const file = name === "evolus" ? "brand/evolus.png" : `brand/${name}.svg`;
  const aspect = name === "amd" ? 4.1933 : name === "evolus" ? 3.8357 : 3.2;
  const m = `url(${staticFile(file)}) center / contain no-repeat`;
  if (name === "gemma") {
    // The official sparkle mark, then the name set in the film's type (as the app's footer does).
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: height * 0.3, color }}>
        <Img src={staticFile(file)} style={{ height, filter: color === "#FAFAFA" || color === "#FFFFFF" ? "invert(1)" : undefined }} />
        <span style={{ fontSize: height * 0.95, fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1 }}>Gemma 4</span>
      </span>
    );
  }
  return <div style={{ width: height * aspect, height, background: color, mask: m, WebkitMask: m }} />;
};
