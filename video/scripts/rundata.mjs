// After scripts/capture-live.mjs: name the moments the film cuts to (.cache/marks.json, epoch seconds) and pull the
// run's real numbers into src/data.json, then fill {quote}/{retail} in script.json from them.
//   ATELIER_TOKEN=... node scripts/rundata.mjs [baseUrl]
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const BASE = process.argv[2] || "https://atelier.netlayerlabs.com";
const tl = JSON.parse(readFileSync(join(ROOT, ".cache/timeline.json"), "utf8"));
const first = (type, re) => tl.find((e) => e.type === type && re.test(e.caption || e.id || e.did || e.text || ""));

const NAMES = {
  trend_done: ["beat", /names the trend/i],
  sketch_done: ["beat", /keeps the taste|pick the design/i],
  techpack: ["beat", /tech pack carries/i],
  rfqs: ["beat", /RFQs go out/i],
  quotes: ["beat", /quote documents/i],
  handoff: ["beat", /breaks a brand guardrail/i],
  counter: ["beat", /^Negotiate/i],
  revised: ["beat", /revised quote; if it passes/i],
  shopify: ["seg", /^shopify$/],
  po_sent: ["beat", /Demand validated/i],
  inference: ["beat", /Every model call/i],
  close: ["beat", /factory-ready/i],
};
const marks = {};
for (const [k, [type, re]] of Object.entries(NAMES)) {
  const e = first(type, re);
  if (e) marks[k] = e.t; else console.log(`mark ${k}: not found`);
}
writeFileSync(join(ROOT, ".cache/marks.json"), JSON.stringify(marks, null, 1));
console.log("marks:", Object.keys(marks).join(", "));

const runId = tl.find((e) => e.type === "run")?.runId;
const head = process.env.ATELIER_TOKEN ? { Authorization: `Bearer ${process.env.ATELIER_TOKEN}` } : {};
const run = runId ? await (await fetch(`${BASE}/api/runs/${runId}`, { headers: head })).json() : null;
const data = JSON.parse(readFileSync(join(ROOT, "src/data.json"), "utf8"));
if (run) {
  const tp = run.techPack || {};
  const quotes = run.quotes || [];
  const first320 = quotes.find((q) => Math.round(q.unitPrice) === 320);
  const passing = quotes.filter((q) => q !== first320).sort((a, b) => (b.revision || 0) - (a.revision || 0))[0];
  const po = run.demand?.purchaseOrder || {};
  const rp = Number(tp.targetRetailPrice || data.retail);
  Object.assign(data, {
    note: `From the recorded live run ${runId} on ${BASE} (17 Oct 2026).`,
    trendName: run.trend?.name || data.trendName,
    retail: Math.round(rp * 100) / 100,
    quote: first320 ? 320 : data.quote,
    target: run.decision?.counterOffer?.targetUnitPrice ?? Math.floor(rp * 0.4 * 100) / 100,
    revised: passing?.unitPrice ?? data.revised,
    poNumber: po.poNumber || data.poNumber,
    poQty: po.quantity || data.poQty,
    poTotal: po.total || data.poTotal,
  });
}
const wait = (re) => { const e = first("beat", re); const w = tl.filter((x) => x.type === "wait_end" && e && x.t <= e.t + 2).pop(); return w?.secs; };
data.trendSecs = wait(/names the trend/i) ?? data.trendSecs;
writeFileSync(join(ROOT, "src/data.json"), JSON.stringify(data, null, 1));
console.log("data:", JSON.stringify(data));

// the narration line that quotes the run's own numbers
const sp = join(ROOT, "script.json");
const script = JSON.parse(readFileSync(sp, "utf8"));
const words = (n) => n.toLocaleString("en-GB", { maximumFractionDigits: 0 });
for (const s of script.scenes) for (const l of s.lines) {
  if (l.template) l.text = l.template;
  if (/\{quote\}|\{retail\}/.test(l.text)) { l.template = l.text; l.text = l.text.replace("{quote}", words(data.quote)).replace("{retail}", `${words(Math.round(data.retail))} euros`); }
}
writeFileSync(sp, JSON.stringify(script, null, 1));
console.log("handoff line:", script.scenes.find((s) => s.id === "handoff").lines[0].text);
