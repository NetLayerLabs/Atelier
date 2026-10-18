import React from "react";
import { AbsoluteFill, Audio, Freeze, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { T, scene, wordAt, lineStart } from "./timing";
import { C } from "./theme";
import { Chrome } from "./ui/Chrome";
import { Captions } from "./ui/Captions";
import { Grain } from "./ui/Grain";
import { clamp } from "./ui/motion";
import { Open } from "./scenes/Open";
import { Evidence } from "./scenes/Evidence";
import { Gap } from "./scenes/Gap";
import { Turn } from "./scenes/Turn";
import { Trend, Sketch, Paperwork, Handoff, Preorder, Po, Different } from "./scenes/Product";
import { Close } from "./scenes/Close";

const SCENES: Record<string, React.FC> = {
  open: Open, evidence: Evidence, gap: Gap, turn: Turn, trend: Trend, sketch: Sketch,
  paperwork: Paperwork, handoff: Handoff, preorder: Preorder, po: Po, different: Different, close: Close,
};
const OVERLAP = 10; // frames each scene starts early, to cross-dissolve with the last

/** Each scene eases in (a short rise and un-blur) over the tail of the previous one. */
const SceneIn: React.FC<{ S: React.FC; first: boolean }> = ({ S, first }) => {
  const f = useCurrentFrame();
  if (first) return <S />;
  const p = interpolate(f, [0, OVERLAP], [0, 1], { ...clamp, easing: (t) => 1 - Math.pow(1 - t, 3) });
  // While it dissolves in over the previous scene, the new one holds its first frame.
  const body = f < OVERLAP ? <Freeze frame={0}><S /></Freeze> : <Sequence from={OVERLAP} layout="none"><S /></Sequence>;
  return <AbsoluteFill style={{ opacity: p, transform: `scale(${1.03 - 0.03 * p})`, filter: p < 1 ? `blur(${(1 - p) * 10}px)` : undefined }}>{body}</AbsoluteFill>;
};

// --- Music: ducked under every spoken line.
const LINES = T.scenes.flatMap((s) => s.lines.map((l) => [l.startFrame, l.words[l.words.length - 1].end] as const));
const DUCK: number[] = (() => {
  const v = new Array<number>(T.totalFrames + 1).fill(0);
  for (let f = 0; f <= T.totalFrames; f++) {
    let d = 0;
    for (const [a, b] of LINES) d = Math.max(d, interpolate(f, [a - 10, a, b, b + 14], [0, 1, 1, 0], clamp));
    v[f] = d;
  }
  return v;
})();
const musicVolume = (f: number) => {
  const end = T.totalFrames;
  const fadeIn = interpolate(f, [0, 24], [0, 1], clamp);
  const fadeOut = interpolate(f, [end - 60, end], [1, 0], clamp);
  return (0.5 - 0.33 * DUCK[Math.min(end, Math.max(0, f))]) * fadeIn * fadeOut;
};

interface Fx { file: string; at: number; vol: number; dur?: number }
function effects(): Fx[] {
  const sc = (id: string) => scene(id).from;
  const w = (id: string, word: string, n = 0) => wordAt(id, word, n);
  const fx: Fx[] = [
    { file: "tick", at: 8, vol: 0.3 }, { file: "tick", at: 38, vol: 0.3 },
    { file: "scratch", at: w("open", "Guess.") - 3, vol: 0.55 },
    ...["Design", "hundreds", "Hope"].map((x) => ({ file: "pop", at: w("open", x) - 1, vol: 0.4 })),
    { file: "buzzer", at: w("open", "Hope") + 10, vol: 0.32 },
    { file: "whoosh", at: sc("evidence") - 6, vol: 0.3 },
    { file: "swoosh_up", at: w("evidence", "two") - 4, vol: 0.3 },
    { file: "stamp", at: w("evidence", "destroy") - 1, vol: 0.6 },
    { file: "whoosh", at: sc("gap") - 6, vol: 0.3 },
    { file: "paper", at: w("gap", "hours"), vol: 0.45 },
    { file: "paper", at: w("gap", "hours") + 24, vol: 0.35 },
    { file: "tick", at: w("gap", "yes.") - 2, vol: 0.45 },
    { file: "riser", at: sc("turn") - 95, vol: 0.38 },
    { file: "impact", at: w("turn", "Atelier.") - 3, vol: 0.55 },
    { file: "chime", at: w("turn", "sold.") - 2, vol: 0.3 },
    { file: "whoosh", at: sc("trend") - 6, vol: 0.3 },
    ...["Gemma", "AMD", "reads"].map((x) => ({ file: "pop", at: w("trend", x) - 1, vol: 0.32 })),
    { file: "whoosh", at: sc("sketch") - 6, vol: 0.3 },
    { file: "snip", at: w("sketch", "Mandarin") - 2, vol: 0.5 },
    { file: "snip", at: w("sketch", "Half") - 2, vol: 0.5 },
    { file: "snip", at: w("sketch", "Side") - 2, vol: 0.5 },
    { file: "whoosh", at: sc("paperwork") - 6, vol: 0.3 },
    { file: "click", at: w("paperwork", "approve,") - 1, vol: 0.5 },
    { file: "sewing", at: w("paperwork", "agents") - 2, vol: 0.32 },
    { file: "typing", at: w("paperwork", "Quote") - 2, vol: 0.2 },
    { file: "pop", at: w("paperwork", "first") + 4, vol: 0.4 },
    { file: "whoosh", at: sc("handoff") - 6, vol: 0.3 },
    { file: "pop", at: w("handoff", "comes") + 15, vol: 0.45 },
    { file: "pop", at: w("handoff", "tunic") + 5, vol: 0.4 },
    { file: "buzzer", at: w("handoff", "breaks") - 2, vol: 0.45 },
    { file: "click", at: w("handoff", "negotiate.") - 2, vol: 0.5 },
    { file: "typing", at: w("handoff", "drafts") - 2, vol: 0.2 },
    { file: "whoosh", at: sc("preorder") - 6, vol: 0.3 },
    { file: "chime", at: w("preorder", "passes.") - 2, vol: 0.35 },
    { file: "register", at: w("preorder", "live") - 2, vol: 0.45 },
    { file: "tick", at: w("preorder", "waits.") - 2, vol: 0.45 },
    { file: "tick", at: w("preorder", "waits.") + 20, vol: 0.4 },
    { file: "whoosh", at: sc("po") - 6, vol: 0.3 },
    ...[0, 6, 12, 18, 24].map((d) => ({ file: "pop", at: w("po", "Five") + d, vol: 0.3 })),
    { file: "stamp", at: w("po", "purchase") + 3, vol: 0.6 },
    { file: "chime", at: w("po", "purchase") + 6, vol: 0.32 },
    { file: "swoosh_up", at: sc("different") - 6, vol: 0.32 },
    ...["Taste", "Rules,", "nothing"].map((x) => ({ file: "impact", at: w("different", x) - 4, vol: 0.2 })),
    { file: "whoosh", at: sc("close") - 6, vol: 0.3 },
    { file: "chime", at: w("close", "Atelier.") - 2, vol: 0.42 },
  ];
  return fx.filter((x) => x.at >= 0 && x.at < T.totalFrames);
}

export const Film: React.FC = () => {
  // Captions sit out where the picture already carries the words (big kinetic type, cards).
  const hideCaptions = (f: number) => {
    const s = T.scenes.find((x) => f >= x.from && f < x.from + x.durationInFrames);
    return !s || ["open", "turn", "different", "close"].includes(s.id) || f < lineStart("open", 0) - 4;
  };
  return (
    <AbsoluteFill style={{ background: C.frame }}>
      {T.scenes.map((s, i) => {
        const S = SCENES[s.id];
        const from = i === 0 ? s.from : s.from - OVERLAP;
        const dur = s.durationInFrames + (i === 0 ? 0 : OVERLAP);
        return S ? (
          <Sequence key={s.id} from={from} durationInFrames={dur} name={s.id}>
            <SceneIn S={S} first={i === 0} />
          </Sequence>
        ) : null;
      })}
      <Grain opacity={0.05} />
      <Chrome hideAfter={scene("close").from + 40} />
      <Captions hidden={hideCaptions} />
      <Audio src={staticFile("audio/music.mp3")} volume={musicVolume} />
      {T.scenes.flatMap((s) => s.lines).map((l, i) => (
        <Sequence key={`vo${i}`} from={l.startFrame} durationInFrames={l.durationFrames} name={`vo ${l.text.slice(0, 18)}`}>
          <Audio src={staticFile(l.file)} volume={1} />
        </Sequence>
      ))}
      {effects().map((x, i) => (
        <Sequence key={`fx${i}`} from={x.at} durationInFrames={x.dur ?? 150} name={`fx ${x.file}`}>
          <Audio src={staticFile(`audio/sfx/${x.file}.mp3`)} volume={(f) => x.vol * (x.dur ? interpolate(f, [0, 8, x.dur - 20, x.dur], [0, 1, 1, 0], clamp) : 1)} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
