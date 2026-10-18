import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";

export const inter = loadInter("normal", { weights: ["200", "300", "400", "500", "600"], subsets: ["latin"] }).fontFamily;
export const mono = loadMono("normal", { weights: ["400", "500"], subsets: ["latin"] }).fontFamily;
export const serif = loadSerif("italic", { weights: ["400"], subsets: ["latin"] }).fontFamily;

/**
 * Atelier's palette, from the app's tokens (frontend/src/app/globals.css): monochrome ink on white, a warm linen
 * for the paper scenes, and the hero gauge's tension colours (ok / warn / bad) as the only accents.
 */
export const C = {
  linen: "#F3EFE7",
  paper: "#FFFFFF",
  white: "#FFFFFF",
  ink: "#0A0A0A",
  ink2: "#1C1C1E",
  muted: "#5F5F63",
  faint: "#8E8E93",
  line: "rgba(10,10,10,0.10)",
  tick: "rgba(10,10,10,0.24)",
  night: "#0A0A0A",
  green: "#15803D",
  greenLit: "#4ADE80",
  amber: "#B45309",
  amberLit: "#FBBF24",
  red: "#C42020",
  redLit: "#F87171",
  frame: "#F3EFE7",
  accent: "#0A0A0A",
};

export type Tone = "light" | "night" | "white";
export const TONE: Record<Tone, { bg: string; ink: string; muted: string; line: string }> = {
  light: { bg: C.linen, ink: C.ink, muted: C.muted, line: "rgba(10,10,10,0.12)" },
  white: { bg: C.paper, ink: C.ink, muted: C.muted, line: "rgba(10,10,10,0.10)" },
  night: { bg: C.night, ink: "#FAFAFA", muted: "rgba(250,250,250,0.58)", line: "rgba(250,250,250,0.14)" },
};

/** Which look each scene uses; the corner chrome and captions follow it. */
export const SCENE_TONE: Record<string, Tone> = {
  open: "night", evidence: "white", gap: "light", turn: "white", trend: "light", sketch: "light",
  paperwork: "light", handoff: "night", preorder: "light", po: "white", different: "night", close: "white",
};

export const SCENE_LABEL: Record<string, string> = {
  open: "01 · the business model", evidence: "02 · the evidence", gap: "03 · the bill", turn: "04 · atelier",
  trend: "05 · the signal", sketch: "06 · the design", paperwork: "07 · the paperwork", handoff: "08 · the hand-off",
  preorder: "09 · sell first", po: "10 · then make", different: "11 · why it's different", close: "12 · make only what's sold",
};

export const EXPO = [0.16, 1, 0.3, 1] as const;
