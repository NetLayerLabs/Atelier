// Records Atelier's submission video on the live site: a REAL run, nothing staged.
// Order: title card -> the landing -> the Brand workspace -> the app's own guided tour (?demo=1&captions=1) against the
// real services. This script only does what the tour leaves to a person: press Approve, upload the supplier quotes
// (TEST documents, labelled as such), press Send on the counter-offer, place a Shopify test-gateway order. Then an end
// card. Frames come from Chrome's screencast (exact 1920x1080), stamped with wall-clock time; timeline.json marks the
// model waits (sped up in editing, with an on-screen badge) and the narration anchors.
//
//   ATELIER_TOKEN=<admin token> node scripts/capture-live.mjs <outDir> [baseUrl]      (the token is read from the env, never printed)
// Playwright: from this project or wherever it is installed (PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs).
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve(process.argv[2] || new URL("../.cache", import.meta.url).pathname);
const BASE = process.argv[3] || "https://atelier.netlayerlabs.com";
const TOKEN = process.env.ATELIER_TOKEN || "";
const STOP_AT = process.env.STOP_AT || ""; // dry run: stop when this tour prompt appears (e.g. "Press Approve")
const SUPPLIER = "Demo supplier - our inbox";
const FR = path.join(OUT, "frames", "live");
fs.mkdirSync(FR, { recursive: true });
const FRAMES = [];

const timeline = [];
const now = () => Date.now() / 1000;
const save = () => {
  fs.writeFileSync(path.join(OUT, "timeline.json"), JSON.stringify(timeline, null, 1));
  const marks = {}; const seen = {};
  for (const e of timeline) { const k = e.type + ":" + (e.id || e.did || e.caption || e.runId || ""); seen[k] = (seen[k] || 0) + 1; marks[(seen[k] > 1 ? k + "#" + seen[k] : k).slice(0, 80)] = e.t; }
  fs.writeFileSync(path.join(OUT, "marks.json"), JSON.stringify(marks, null, 1));
  fs.writeFileSync(path.join(FR, "frames.json"), JSON.stringify(FRAMES));
};
const mark = (type, data = {}) => {
  timeline.push({ t: now(), type, ...data });
  save();
  console.log(`${new Date().toISOString().slice(11, 19)} ${type} ${JSON.stringify(data).slice(0, 150)}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--window-size=1920,1167"] });
const ctx = await browser.newContext({ viewport: null, colorScheme: "light", locale: "en-GB" });
// Personal data stays off a public video: the team inbox is masked the way the app masks it for signed-out visitors,
// in every page (app, workspace, Shopify checkout), and email inputs are blurred.
// INBOX_EMAIL: the team inbox the demo suppliers route to; it is masked on screen and used for the test checkout.
const INBOX = process.env.INBOX_EMAIL || "";
await ctx.addInitScript((inbox) => {
  const RE = new RegExp(inbox.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") || "(?!)", "gi");
  const scrub = (root) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) if (n.nodeValue && inbox && n.nodeValue.toLowerCase().includes(inbox.toLowerCase())) n.nodeValue = n.nodeValue.replace(RE, inbox[0] + "\u2022\u2022\u2022@" + inbox.split("@")[1]);
  };
  const css = 'input[type="email"],input[name="email"],#email{filter:blur(6px)}';
  const start = () => {
    const st = document.createElement("style"); st.textContent = css; document.documentElement.appendChild(st);
    scrub(document.body);
    new MutationObserver((ms) => ms.forEach((m) => {
      if (m.type === "characterData") scrub(m.target.parentNode || document.body);
      m.addedNodes.forEach((n) => scrub(n.nodeType === 3 ? n.parentNode || document.body : n));
    })).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  };
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
  // film capture: the tour's status pill stays off camera (the film has its own captions)
  const addHide = () => {
    const hide = document.createElement("style");
    hide.textContent = "div.fixed.bottom-4.left-4.z-50{opacity:0!important}";
    document.head.appendChild(hide);
  };
  if (document.head) addHide(); else document.addEventListener("DOMContentLoaded", addHide);
}, INBOX);

// ---- sign in (session cookie), so Approve and the steps after it are allowed
if (TOKEN) {
  const r = await ctx.request.post(`${BASE}/api/auth/login`, { data: { token: TOKEN }, headers: { Origin: BASE } });
  if (!r.ok()) throw new Error(`sign-in failed: HTTP ${r.status()}`);
  const s = await (await ctx.request.get(`${BASE}/api/auth/status`)).json();
  if (!s.authenticated) throw new Error("sign-in did not stick");
  console.log("signed in");
}

// ---- screencast: one recorder that can follow the active page
let rec = null;
async function record(page) {
  if (rec) await stopRecording();
  const cdp = await ctx.newCDPSession(page);
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    const file = path.join(FR, `f${String(FRAMES.length).padStart(6, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(data, "base64"));
    FRAMES.push({ file, t: metadata.timestamp });
    await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 86, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  rec = cdp;
}
async function stopRecording() {
  if (!rec) return;
  await rec.send("Page.stopScreencast").catch(() => {});
  await rec.detach().catch(() => {});
  rec = null;
}

// ---- overlays drawn into the page (part of the video, never part of the app)
const OVERLAY_CSS = `
#vid-card{position:fixed;inset:0;z-index:2147483646;display:flex;flex-direction:column;justify-content:center;
  align-items:flex-start;padding:0 160px;background:var(--paper,#fff);color:var(--fg,#0b0b0b);font-family:Inter,ui-sans-serif,system-ui;
  opacity:0;transition:opacity .7s cubic-bezier(.16,1,.3,1)}
#vid-card.on{opacity:1}
#vid-card .k{font-size:22px;letter-spacing:.02em;color:var(--fg-muted,#555)}
#vid-card h1{font-size:112px;line-height:1.02;font-weight:300;letter-spacing:-.045em;margin:28px 0 0}
#vid-card h1 em{font-style:normal;color:var(--fg-muted,#666)}
#vid-card p{font-size:28px;font-weight:300;line-height:1.45;color:var(--fg-muted,#555);margin:36px 0 0;max-width:1300px}
#vid-card .s{font-size:18px;margin-top:54px;color:var(--fg-faint,#888);line-height:1.6}
#vid-cap{position:fixed;left:50%;bottom:44px;transform:translateX(-50%);z-index:2147483645;max-width:1100px;
  padding:16px 28px;border-radius:20px;border:1px solid var(--line,#e5e5e5);background:color-mix(in srgb,var(--surface,#fff) 92%,transparent);
  backdrop-filter:blur(10px);box-shadow:0 18px 50px -20px rgba(0,0,0,.35);font:300 26px/1.35 Inter,ui-sans-serif,system-ui;
  letter-spacing:-.02em;color:var(--fg,#0b0b0b);text-align:center;opacity:0;transition:opacity .45s ease}
#vid-cap.on{opacity:1}
#vid-fast{position:fixed;right:28px;bottom:28px;z-index:2147483645;padding:9px 16px;border-radius:999px;
  background:var(--fg,#0b0b0b);color:var(--paper,#fff);font:500 15px/1 Inter,ui-sans-serif,system-ui;opacity:0;transition:opacity .3s}
#vid-fast.on{opacity:.92}`;
async function overlays(page) {
  await page.addStyleTag({ content: OVERLAY_CSS }).catch(() => {});
}
async function card(page, html, ms) {
  if (process.env.FILM) return;
  await overlays(page);
  await page.evaluate((h) => {
    let c = document.getElementById("vid-card");
    if (!c) { c = document.createElement("div"); c.id = "vid-card"; document.body.appendChild(c); }
    c.innerHTML = h;
    requestAnimationFrame(() => c.classList.add("on"));
  }, html);
  await sleep(ms);
  await page.evaluate(() => document.getElementById("vid-card")?.classList.remove("on"));
  await sleep(800);
  await page.evaluate(() => document.getElementById("vid-card")?.remove());
}
async function caption(page, text) {
  if (process.env.FILM) return;
  await overlays(page);
  await page.evaluate((t) => {
    let c = document.getElementById("vid-cap");
    if (!c) { c = document.createElement("div"); c.id = "vid-cap"; document.body.appendChild(c); }
    if (!t) { c.classList.remove("on"); return; }
    c.textContent = t;
    requestAnimationFrame(() => c.classList.add("on"));
  }, text || "");
}
async function fastBadge(page, on, secs) {
  if (process.env.FILM) return;
  await page.evaluate(([o, s]) => {
    let b = document.getElementById("vid-fast");
    if (!b) { b = document.createElement("div"); b.id = "vid-fast"; document.body.appendChild(b); }
    b.textContent = s ? `Sped up in editing · real wait ${s}` : "Sped up in editing · model working on AMD";
    b.classList.toggle("on", o);
  }, [on, secs || ""]).catch(() => {});
}
async function smoothScrollTo(page, selector, ms = 1800) {
  await page.evaluate(([sel, dur]) => new Promise((done) => {
    const el = document.querySelector(sel);
    if (!el) return done();
    const from = scrollY, to = Math.max(0, el.getBoundingClientRect().top + scrollY - 90);
    const t0 = performance.now();
    const ease = (x) => 1 - Math.pow(1 - x, 3);
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      scrollTo(0, from + (to - from) * ease(k));
      k < 1 ? requestAnimationFrame(step) : done();
    };
    requestAnimationFrame(step);
  }), [selector, ms]);
}

// ---- watch for model waits: any loading indicator for > 2.5 s becomes a sped-up interval with a badge
function busyWatcher(getPage) {
  let since = null, marked = false, stopped = false;
  (async () => {
    while (!stopped) {
      const page = getPage();
      let busy = false;
      try {
        busy = await page.evaluate(() => {
          const status = document.querySelector('[role="status"]')?.textContent || "";
          if (/waiting for a (supplier quote|real pre-order)|revised quote|press approve|press send/i.test(status)) return false;
          return !!document.querySelector('[aria-busy="true"], [role="progressbar"]:not([aria-valuenow]), .animate-spin');
        });
      } catch { /* navigating */ }
      const t = now();
      if (busy && since == null) since = t;
      if (busy && !marked && t - since > 2.5) { marked = true; mark("wait_start", { from: since + 2 }); await fastBadge(page, true); }
      if (!busy && since != null) {
        if (marked) { mark("wait_end", { secs: Math.round(t - since) }); await fastBadge(page, false); }
        since = null; marked = false;
      }
      await sleep(400);
    }
  })();
  return () => { stopped = true; };
}

// ---- quote PDFs (TEST documents) for the live run's own RFQ reference
async function quotePdf(file, number, ref, price, note) {
  const p = await ctx.newPage();
  await p.setContent(`<!doctype html><meta charset="utf-8"><body style="font:12pt Helvetica;margin:40px">
<h2>[Atelier TEST] Supplier quotation</h2>
<p>Test document written by the Atelier team for the demo recording. Not a real supplier.</p>
<p><b>Supplier:</b> ${SUPPLIER}<br><b>Quote number:</b> ${number}<br><b>Date:</b> 17 October 2026<br>
<b>RFQ reference:</b> ${ref}</p>
<table border="1" cellpadding="6" style="border-collapse:collapse">
<tr><th>Item</th><th>Unit price</th><th>Currency</th><th>MOQ</th><th>Lead time</th></tr>
<tr><td>Tailored garment as per your tech pack, sizes S-XXL</td><td>${price.toFixed(2)}</td><td>EUR</td><td>50 units</td>
<td>6 weeks</td></tr></table>
<p><b>Payment terms:</b> 30% deposit, balance before shipment<br><b>Incoterms:</b> FOB Lagos<br>
<b>Valid until:</b> 15 November 2026</p>${note}</body>`);
  await p.pdf({ path: file, format: "A4" });
  await p.close();
  return file;
}

// ================================================================== the recording
const page = await ctx.newPage();
let runId = null;
page.on("request", (r) => {
  const m = r.url().match(/\/api\/runs\/(run_[0-9a-f]+)/);
  if (m && m[1] !== runId) { runId = m[1]; mark("run", { runId }); }
});
page.on("pageerror", (e) => mark("pageerror", { msg: String(e).slice(0, 200) }));

await page.goto(BASE, { waitUntil: "networkidle" });
await record(page);
let current = page;
const stopBusy = busyWatcher(() => current);

// 1. title card
mark("seg", { id: "title" });
await card(page, `<div class="k">AMD Developer Hackathon · ACT III</div>
  <h1>Atelier.<br><em>Make only what&rsquo;s already sold.</em></h1>
  <p>An AI agent for fashion brands: trend, sketch, tech pack, suppliers, pre-order, purchase order.</p>
  <div class="s">Recorded live on the production site, 17 October 2026 · Gemma 4 on AMD GPUs (AMD Token Factory) · Evolus · Shopify</div>`, 6000);

// 2. the landing (reload so the hero's entrance plays on camera)
mark("seg", { id: "landing" });
await page.goto(BASE, { waitUntil: "domcontentloaded" });
await sleep(5200);
mark("seg", { id: "problem" });
await smoothScrollTo(page, "#landing-problem", 2200);
await sleep(6500);
mark("seg", { id: "how" });
await smoothScrollTo(page, "#landing-how", 2000);
await sleep(5000);
mark("seg", { id: "agents" });
await smoothScrollTo(page, "#landing-agents", 2000);
await sleep(4000);
await smoothScrollTo(page, "#landing-agents ol", 2600);
await sleep(2500);
mark("seg", { id: "stack" });
await smoothScrollTo(page, "#landing-stack", 2200);
await sleep(6000);
mark("seg", { id: "value" });
await smoothScrollTo(page, "#landing-value", 2000);
await sleep(5000);

// 3. the Brand workspace
mark("seg", { id: "workspace" });
await page.goto(`${BASE}/workspace`, { waitUntil: "networkidle" });
await sleep(4000);
for (const want of [/supplier/i, /guardrail/i]) {
  const h = page.getByRole("heading", { name: want }).first();
  if (await h.count()) { await h.scrollIntoViewIfNeeded().catch(() => {}); await sleep(4000); }
}

// 4. the guided tour on the real services
mark("seg", { id: "tour" });
await page.goto(`${BASE}/?demo=1&captions=1`, { waitUntil: "domcontentloaded" });
let lastBeat = "", lastMsg = "", done = new Set(), idleSince = null, quoteFiles = null, blockedSince = null;
const deadline = Date.now() + 40 * 60 * 1000;
while (Date.now() < deadline) {
  await sleep(500);
  let st;
  try {
    st = await page.evaluate(() => ({
      status: document.querySelector('[role="status"]')?.innerText || "",
      caption: document.querySelector("[data-demo-caption] p")?.innerText || "",
    }));
  } catch { continue; }
  if (st.caption && st.caption !== lastBeat) { lastBeat = st.caption; mark("beat", { caption: st.caption }); }
  if (st.status !== lastMsg) { lastMsg = st.status; mark("status", { text: st.status.replace(/\s+/g, " ").slice(0, 220) }); }
  const s = st.status;
  if (STOP_AT && s.includes(STOP_AT)) { mark("stop_at", { STOP_AT }); break; }

  if (/blocked|failed|error/i.test(s) && !/waiting/i.test(s)) {
    blockedSince ??= Date.now();
    if (Date.now() - blockedSince > 90_000) { mark("abort", { reason: "tour blocked > 90 s" }); break; }
  } else blockedSince = null;

  if (/Press Approve/i.test(s) && !done.has("approve")) {
    done.add("approve");
    await sleep(3500); // let the viewer read the recipients line
    await page.click('[data-demo="approve-button"]');
    mark("action", { did: "approve" });
  }
  if (/Waiting for a supplier quote/i.test(s) && !done.has("quote1") && runId) {
    done.add("quote1");
    const run = await (await ctx.request.get(`${BASE}/api/runs/${runId}`)).json();
    const ref = run.quoteRound?.rfqRef || `ATL-${runId}`;
    const retail = Number(run.techPack?.targetRetailPrice || 0);
    const pass = Math.round((Math.min(250, retail * 0.4) - 5) * 100) / 100;
    quoteFiles = {
      first: await quotePdf(path.join(OUT, "quote-TEST-Q-320.pdf"), "TEST-Q-320", ref, 320, ""),
      revised: await quotePdf(path.join(OUT, "quote-TEST-Q-REV1.pdf"), "TEST-Q-REV1", ref, pass, "<p>Revised after your counter-offer.</p>"),
    };
    mark("quotes_ready", { ref, retail, pass });
    await sleep(2500);
    await page.selectOption('[data-demo="quote-upload"] select', SUPPLIER).catch(() => {});
    await page.setInputFiles('[data-demo="quote-upload"] input[type="file"]', quoteFiles.first);
    mark("action", { did: "upload quote 320" });
    await page.waitForFunction(() => /Stop waiting/.test(document.body.innerText) &&
      ![...document.querySelectorAll("button")].find((b) => /Stop waiting/.test(b.textContent || ""))?.disabled,
      null, { timeout: 180_000 }).catch(() => {});
    await sleep(3000);
    const stop = page.getByRole("button", { name: /Stop waiting/ });
    if (await stop.count()) { await stop.first().click(); mark("action", { did: "stop waiting & recommend" }); }
  }
  if (/press Send/i.test(s) && !done.has("send")) {
    done.add("send");
    await sleep(4000);
    await page.click('[data-demo="counter-send"]');
    mark("action", { did: "send counter-offer" });
  }
  if (/revised quote/i.test(s) && /Waiting for/i.test(s) && !done.has("quote2") && quoteFiles) {
    done.add("quote2");
    await sleep(2500);
    await page.selectOption('[data-demo="quote-upload"] select', SUPPLIER).catch(() => {});
    await page.setInputFiles('[data-demo="quote-upload"] input[type="file"]', quoteFiles.revised);
    mark("action", { did: "upload revised quote" });
  }
  if (/Waiting for a real pre-order/i.test(s) && !done.has("order") && runId) {
    done.add("order");
    await sleep(5000); // the QR code and the threshold on screen
    const run = await (await ctx.request.get(`${BASE}/api/runs/${runId}`)).json();
    const url = run.shopifyProduct?.url;
    if (url) {
      mark("seg", { id: "shopify" });
      const shop = await ctx.newPage();
      await shop.goto(url, { waitUntil: "domcontentloaded" });
      if (await shop.locator('input[type="password"]').count()) {
        await shop.fill('input[type="password"]', "atelier");
        await Promise.all([shop.waitForNavigation({ timeout: 20000 }).catch(() => {}), shop.keyboard.press("Enter")]);
        await sleep(1200);
        await shop.goto(url, { waitUntil: "load" }).catch(async () => { await sleep(2000); await shop.goto(url, { waitUntil: "load" }); });
      }
      await record(shop);
      current = shop;
      await overlays(shop);
      await caption(shop, "The live Shopify pre-order - a test-gateway order of 5 units");
      await sleep(5500);
      await caption(shop, "");
      const prod = await shop.evaluate(async (u) => (await fetch(new URL(u).pathname + ".js")).json(), url);
      const v = prod.variants.find((x) => x.available) || prod.variants[0];
      await shop.goto(new URL(`/cart/${v.id}:5`, url).toString(), { waitUntil: "load" });
      await sleep(4000);
      const fill = async (sel, val) => { const l = shop.locator(sel).first(); if (await l.count()) await l.fill(val); };
      await fill('input[name="email"], #email', INBOX);
      await shop.locator('select[name="countryCode"]').first().selectOption("IT").catch(() => {});
      await fill('input[name="firstName"]', "Test");
      await fill('input[name="lastName"]', "Atelier");
      await fill('input[name="address1"]', "Via Roma 1");
      await fill('input[name="city"]', "Roma");
      await fill('input[name="postalCode"]', "00184");
      await shop.locator('select[name="zone"]').first().selectOption("RM").catch(() => {});
      await sleep(2500);
      const frames = shop.locator("iframe.card-fields-iframe:visible");
      for (let i = 0; i < Math.min(4, await frames.count()); i++) {
        const name = (await frames.nth(i).getAttribute("name")) || "";
        const val = /number/i.test(name) ? "1" : /expir/i.test(name) ? "1230" : /verification/i.test(name) ? "123" : "Test Atelier";
        await frames.nth(i).click();
        await shop.keyboard.type(val, { delay: 45 });
      }
      await sleep(1200);
      await shop.locator('button#checkout-pay-button, button:has-text("Pay now")').first().click();
      await shop.waitForURL(/thank[-_]you|orders\//, { timeout: 60000 }).catch(() => {});
      await sleep(5000);
      mark("action", { did: "shopify test order", url: shop.url().replace(/\?.*/, "") });
      await record(page);
      current = page;
      await shop.close();
      mark("seg", { id: "tour-after-order" });
    }
  }
  // the tour ends idle after its last beat
  if (!s.trim() && done.has("order")) {
    idleSince ??= Date.now();
    if (Date.now() - idleSince > 4000) break;
  } else idleSince = null;
}

// 5. end card
mark("seg", { id: "end" });
await card(page, `<div class="k">Atelier · AMD Developer Hackathon ACT III</div>
  <h1>Make only what&rsquo;s<br><em>already sold.</em></h1>
  <p>Live: atelier.netlayerlabs.com · Code: github.com/NetLayerLabs/Atelier</p>
  <div class="s">Recorded live, 17 October 2026, on the real services. Model waits are shortened in editing (marked on screen).<br>
  Supplier quotes are TEST documents written by the team; the order used Shopify's test gateway;<br>
  RFQs, the counter-offer and the purchase order went to the team's own inbox.</div>`, 9000);
stopBusy();
await stopRecording();
mark("done", { runId });
await browser.close();
