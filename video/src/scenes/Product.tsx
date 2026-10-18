import React from "react";
import { AbsoluteFill, Img, Sequence, interpolate, staticFile } from "remotion";
import { C, inter, mono, serif } from "../theme";
import { clamp, pop, ramp } from "../ui/motion";
import { Browser, liveAt } from "../ui/Footage";
import { Glass } from "../ui/Glass";
import { Words } from "../ui/Words";
import { Inbox } from "../ui/Inbox";
import data from "../data.json";
import { eur, useScene } from "./util";

const URL = "atelier.netlayerlabs.com";
const Chip: React.FC<{ t: string; at: number; f: number; dark?: boolean }> = ({ t, at, f, dark }) => {
  const p = pop(f, at);
  return (
    <span style={{ transform: `scale(${p})`, opacity: p, padding: "10px 18px", borderRadius: 999, background: dark ? "#FAFAFA" : C.ink, color: dark ? C.ink : "#FAFAFA", fontFamily: mono, fontSize: 17, letterSpacing: "0.04em", whiteSpace: "nowrap" }}>{t}</span>
  );
};

/** 05 · Gemma 4 on AMD reads the trend from the brand's own mood board. */
export const Trend: React.FC = () => {
  const { f, rel } = useScene("trend");
  return (
    <AbsoluteFill style={{ background: C.linen, fontFamily: inter }}>
      <Browser name="live" url={URL} width={1400} left={260} top={150} startFrom={liveAt("trend_done", -150)} enter={0} tilt={8}
        focus={{ x: 0, y: 140, w: 1920, h: 700 }} zoom={1.25} focusAt={[rel("reads") + 4, rel("reads") + 40]} />
      <div style={{ position: "absolute", left: 260, top: 80, display: "flex", gap: 12 }}>
        <Chip t="Gemma 4 · Google, open model" at={rel("Gemma")} f={f} />
        <Chip t="AMD GPUs · AMD Token Factory" at={rel("AMD")} f={f} />
        <Chip t={`a real model call · ${data.trendSecs} s`} at={rel("reads")} f={f} />
      </div>
    </AbsoluteFill>
  );
};

/** 06 · The designer's own sketch, read like a pattern cutter. */
export const Sketch: React.FC = () => {
  const { f, rel } = useScene("sketch");
  const reads: [string, string][] = [["Mandarin collar", "Mandarin"], ["Half placket", "Half"], ["Side slits", "Side"]];
  return (
    <AbsoluteFill style={{ background: C.linen, fontFamily: inter, color: C.ink }}>
      <div style={{ position: "absolute", left: 120, top: 150, width: 560, height: 720, borderRadius: 24, overflow: "hidden", background: C.paper, boxShadow: "0 0 0 1px rgba(10,10,10,0.08), 0 30px 70px rgba(10,10,10,0.14)", opacity: ramp(f, 0, 14), transform: `rotate(${-2 + 2 * ramp(f, 0, 20)}deg)` }}>
        <Img src={staticFile("demo/senator-tunic-sketch.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        <div style={{ position: "absolute", left: 16, top: 16, fontFamily: mono, fontSize: 14, letterSpacing: "0.1em", padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.85)" }}>THE DESIGNER'S SKETCH</div>
      </div>
      <Browser name="live" url={URL} width={1080} left={740} top={150} startFrom={liveAt("sketch_done", -90)} enter={6} />
      <div style={{ position: "absolute", left: 740, top: 800, display: "flex", gap: 14 }}>
        {reads.map(([t, w]) => {
          const p = pop(f, rel(w));
          return (
            <Glass key={t} style={{ padding: "14px 22px", opacity: p, transform: `translateY(${(1 - p) * 24}px)` }}>
              <span style={{ fontFamily: mono, fontSize: 14, color: C.muted, marginRight: 10 }}>READ</span>
              <span style={{ fontSize: 28, fontWeight: 400, letterSpacing: "-0.02em" }}>{t}</span>
            </Glass>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** 07 · Approve, and the agents take the paperwork. */
export const Paperwork: React.FC = () => {
  const { s, f, rel } = useScene("paperwork");
  const tRfq = rel("Quote");
  const tTime = rel("first");
  const cut = tRfq - 6;
  return (
    <AbsoluteFill style={{ background: C.linen, fontFamily: inter, color: C.ink }}>
      <Sequence durationInFrames={cut} layout="none">
        <Browser name="live" url={URL} width={1300} left={310} top={140} startFrom={liveAt("techpack", -30)} enter={0}
          focus={{ x: 300, y: 120, w: 1320, h: 760 }} zoom={1.3} focusAt={[rel("costed"), rel("costed") + 30]} />
      </Sequence>
      <Sequence from={cut} layout="none">
        <Browser name="live" url={URL} width={1300} left={310} top={140} startFrom={liveAt("rfqs", -20)} enter={0} />
      </Sequence>
      <div style={{ position: "absolute", left: 310, top: 76, display: "flex", gap: 12 }}>
        <Chip t="Evolus agent · Gemma 4 on AMD" at={rel("agents")} f={f} />
        <Chip t="grounded in the brand book" at={rel("grounded")} f={f} />
        <Chip t="Italian · English alongside" at={rel("language.")} f={f} />
      </div>
      <Inbox file="rfq" at={rel("language.") + 4} width={1240} style={{ left: 120, bottom: 150 }} />
      <Glass style={{ position: "absolute", right: 70, bottom: 120, padding: "22px 30px", opacity: ramp(f, tTime - 4, tTime + 10), transform: `scale(${0.9 + 0.1 * ramp(f, tTime - 4, tTime + 10)})` }}>
        <div style={{ fontFamily: mono, fontSize: 14, letterSpacing: "0.1em", color: C.muted }}>APPROVE → RFQS SENT · FIRST LIVE RUN, 17 OCT</div>
        <div style={{ fontSize: 96, fontWeight: 300, letterSpacing: "-0.04em", lineHeight: 1 }}>{data.firstRunApproveToRfqs}<span style={{ fontSize: 40, color: C.muted }}> min</span></div>
      </Glass>
      <div style={{ display: "none" }}>{s.id}</div>
    </AbsoluteFill>
  );
};

/** 08 · The comic peak: €320 for a tunic that sells for less. The agent stops and asks. */
export const Handoff: React.FC = () => {
  const { f, rel } = useScene("handoff");
  const tQuote = rel("comes");
  const tAgent = rel("breaks");
  const tNeg = rel("negotiate.");
  const margin = (1 - data.quote / data.retail) * 100;
  const tag = (label: string, v: string, at: number, col: string, rot: number) => {
    const p = pop(f, at);
    return (
      <div style={{ opacity: p, transform: `translateY(${(1 - p) * 40}px) rotate(${rot}deg)`, background: "#FAFAFA", color: C.ink, borderRadius: 18, padding: "18px 26px", minWidth: 300 }}>
        <div style={{ fontFamily: mono, fontSize: 15, letterSpacing: "0.12em", color: C.muted }}>{label}</div>
        <div style={{ fontSize: 92, fontWeight: 300, letterSpacing: "-0.045em", lineHeight: 1, color: col }}>{v}</div>
      </div>
    );
  };
  const showFootage = f >= tNeg - 20;
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: inter, color: "#FAFAFA" }}>
      {!showFootage ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 40, flexDirection: "row", top: -60 }}>
          {tag("SUPPLIER QUOTE / PIECE", eur(data.quote), tQuote + 16, C.red, -3)}
          <div style={{ fontFamily: serif, fontStyle: "italic", fontSize: 90, opacity: ramp(f, rel("tunic"), rel("tunic") + 8) }}>vs</div>
          {tag("SHOP PRICE", eur(data.retail), rel("tunic") + 6, C.ink, 2)}
        </AbsoluteFill>
      ) : null}
      {!showFootage ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 690, textAlign: "center", opacity: ramp(f, tAgent - 10, tAgent) }}>
          <span style={{ fontFamily: mono, fontSize: 22, letterSpacing: "0.1em", color: "#FBBF24" }}>MARGIN {margin.toFixed(1)}% · FLOOR {data.marginFloor}% · CAP {eur(data.costCap)}</span>
        </div>
      ) : null}
      {showFootage ? (
        <>
          <Browser name="live" url={URL} width={1300} left={310} top={140} startFrom={liveAt("counter", -60)} enter={tNeg - 20}
            focus={{ x: 260, y: 160, w: 1400, h: 760 }} zoom={1.35} focusAt={[tNeg + 10, tNeg + 40]} />
          <div style={{ position: "absolute", left: 310, top: 76, display: "flex", gap: 12 }}>
            <Chip t={`target ${eur(data.target)} = ${eur(data.retail)} × (1 − ${data.marginFloor}%)`} at={rel("exact")} f={f} dark />
            <Chip t="plain arithmetic · then Gemma 4 writes it" at={rel("margin", 1)} f={f} dark />
            <Chip t="sent through Evolus" at={rel("Evolus")} f={f} dark />
          </div>
          <Inbox file="counter" at={rel("Evolus") + 4} width={1300} style={{ left: 310, bottom: 150 }} />
        </>
      ) : null}
    </AbsoluteFill>
  );
};

/** 09 · The pre-order goes live; the factory order waits. */
export const Preorder: React.FC = () => {
  const { f, rel } = useScene("preorder");
  const tWait = rel("waits.");
  return (
    <AbsoluteFill style={{ background: C.linen, fontFamily: inter, color: C.ink }}>
      <Browser name="live" url="atelier-demo-kpy5tj2x.myshopify.com" width={1300} left={310} top={140} startFrom={liveAt("shopify", 20)} enter={0} />
      <div style={{ position: "absolute", left: 310, top: 76, display: "flex", gap: 12 }}>
        <Chip t={`revised ${eur(data.revised)} · inside every rule`} at={rel("passes.")} f={f} />
        <Chip t="a real Shopify product · test store" at={rel("Shopify.")} f={f} />
      </div>
      <Glass style={{ position: "absolute", right: 80, bottom: 120, padding: "22px 30px", opacity: ramp(f, tWait - 14, tWait), transform: `rotate(${-3 * ramp(f, tWait - 14, tWait)}deg)` }}>
        <div style={{ fontFamily: mono, fontSize: 14, letterSpacing: "0.12em", color: C.muted }}>FACTORY ORDER</div>
        <div style={{ fontFamily: serif, fontStyle: "italic", fontSize: 92, lineHeight: 1 }}>waiting…</div>
        <div style={{ fontFamily: mono, fontSize: 16, color: C.muted }}>0 / {data.threshold} PRE-ORDERS</div>
      </Glass>
    </AbsoluteFill>
  );
};

/** 10 · Five pre-orders, then the purchase order. */
export const Po: React.FC = () => {
  const { f, rel } = useScene("po");
  const tPo = rel("purchase");
  const stamp = pop(f, tPo + 4);
  const n = Math.min(data.threshold, Math.floor(interpolate(f, [rel("Five"), rel("threshold.")], [0, data.threshold], clamp)));
  return (
    <AbsoluteFill style={{ background: C.paper, fontFamily: inter, color: C.ink }}>
      <Browser name="live" url={URL} width={1080} left={110} top={170} startFrom={liveAt("po_sent", -60)} enter={0} />
      <div style={{ position: "absolute", left: 1250, top: 200, width: 560 }}>
        <div style={{ fontFamily: mono, fontSize: 18, letterSpacing: "0.12em", color: C.muted }}>PRE-ORDERS · DEMO THRESHOLD</div>
        <div style={{ fontSize: 150, fontWeight: 300, letterSpacing: "-0.05em", lineHeight: 1 }}>{n}<span style={{ color: C.faint }}> / {data.threshold}</span></div>
        <div style={{ height: 10, borderRadius: 5, background: "rgba(10,10,10,0.08)", marginTop: 18 }}>
          <div style={{ height: 10, borderRadius: 5, width: `${(n / data.threshold) * 100}%`, background: n >= data.threshold ? C.green : C.ink }} />
        </div>
      </div>
      <Inbox file="po" at={tPo + 20} width={1080} style={{ left: 110, top: 850 }} />
      <div style={{
        position: "absolute", left: 1270, top: 520, padding: "22px 30px", border: `5px solid ${C.ink}`, borderRadius: 16,
        opacity: stamp, transform: `rotate(-6deg) scale(${2 - stamp})`, background: C.paper,
      }}>
        <div style={{ fontFamily: mono, fontSize: 52, fontWeight: 500, letterSpacing: "0.08em" }}>{data.poNumber}</div>
        <div style={{ fontSize: 26, marginTop: 8 }}>{data.poQty} × {eur(data.revised)} = {eur(data.poTotal)}</div>
        <div style={{ fontFamily: mono, fontSize: 15, color: C.muted, marginTop: 6 }}>SENT TO THE MILL THROUGH EVOLUS</div>
      </div>
    </AbsoluteFill>
  );
};

/** 11 · Three things, each with its proof. */
export const Different: React.FC = () => {
  const { f, rel } = useScene("different");
  const claims: [string, string, string, number][] = [
    ["Taste stays human", "4 creative calls · every money decision is yours", "01", rel("Taste")],
    ["Rules, not vibes", "margins are plain arithmetic · the AI can't be sweet-talked", "02", rel("Rules,")],
    ["Nothing made up", "every model call measured, live, on AMD", "03", rel("nothing")],
  ];
  const showInference = f >= rel("measured,") - 10;
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: inter, color: "#FAFAFA" }}>
      <div style={{ position: "absolute", left: 120, top: 150, fontSize: 70, fontWeight: 300, letterSpacing: "-0.04em" }}>
        <Words text="Three things make it different." at={rel("Three")} every={3} accent={{ "different.": "#FBBF24" }} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 330, display: "flex", flexDirection: "column", gap: 22, width: showInference ? 760 : 1680 }}>
        {claims.map(([t, proof, n, at]) => {
          const p = pop(f, at);
          return (
            <div key={n} style={{ opacity: p, transform: `translateX(${(1 - p) * -40}px)`, display: "flex", gap: 28, alignItems: "baseline", borderTop: "1px solid rgba(250,250,250,0.14)", paddingTop: 22 }}>
              <span style={{ fontFamily: mono, fontSize: 20, opacity: 0.5 }}>{n}</span>
              <div>
                <div style={{ fontFamily: serif, fontStyle: "italic", fontSize: 76, lineHeight: 1 }}>{t}</div>
                <div style={{ fontFamily: mono, fontSize: 19, opacity: 0.62, marginTop: 8 }}>{proof}</div>
              </div>
            </div>
          );
        })}
      </div>
      {showInference ? (
        <Browser name="live" url={URL} width={900} left={930} top={330} startFrom={liveAt("inference", 20)} enter={rel("measured,") - 10} />
      ) : null}
    </AbsoluteFill>
  );
};
