"use client";

// Guided tour: drives the REAL app against the REAL services.
//
// A small beat script uses the same store actions, buttons and backend calls a person would use, from mood board to
// purchase order. It never injects inputs and never sends anything: it does not press Approve (which emails the
// brand's real suppliers or their RFQ override inboxes) or Send on a counter-offer. At those beats it PAUSES, names
// every address the email would go to, and carries on once the presenter has pressed the button. The same goes for
// beats that need other people (a supplier's quote document, a real pre-order). Crossing the pre-order threshold
// sends the PO to the selected mill (the pipeline does that, not the tour); the tour says so, with the address,
// before it waits for pre-orders.
// When a service is not connected the tour shows that error (with its setup hint) and waits: fix it and press R to
// retry the beat, → to skip it, or Esc to drive by hand. Nothing here fakes a screen or a result.
//
// Controls (while running): Space pause/resume · → next beat · R retry · Esc exit · C captions. Shift+D starts / exits.
// URL: ?demo=1 auto-starts; &pace=1.5 stretches every hold (default 1.2); &captions=1 shows presenter captions.

import { useEffect, useRef } from "react";
import { create } from "zustand";
import { errorHint, errorMessage, getPresets, getRfqRecipients, negotiateDecision, type PipelineRun } from "./api";
import { useAtelier, type AsyncState } from "./store";
import { useVoice } from "./voice";
import { getWorkspaceStatus, type WorkspaceStatus } from "./workspace";

// --------------------------------------------------------------------------- config

/**
 * The tour's inputs: the knitwear mood board, the knits review dataset and one spoken-style direction. The presenter
 * sets the run size and presses Approve. Everything after approval comes from the real services and from real people
 * (mills, shoppers); the tour waits for them.
 */
export const DEMO_PRESET = "max-azria-fw2010";
export const DEMO_DIRECTION = "make it darker, cropped, more Margiela";
const DEMO_VOICE_SAMPLE = "knits";

const TICK_MS = 100;
/** Offset for the sticky header + chapter nav when scrolling a target into view. */
const SCROLL_OFFSET = 150;

// --------------------------------------------------------------------------- commands for components

/** Things the demo asks a component to do with its own local state (typed text, a BOM swap, a save). */
export type DemoCommand =
  | { id: number; type: "direct-text"; text: string }
  | { id: number; type: "swap-material"; index: number; material: string }
  | { id: number; type: "save-techpack" };

type DemoCommandInput =
  | { type: "direct-text"; text: string }
  | { type: "swap-material"; index: number; material: string }
  | { type: "save-techpack" };

// --------------------------------------------------------------------------- store

/** waiting = paused on a human input (a quote document, a pre-order, an email to send); blocked = an error. */
export type DemoStatus = "idle" | "running" | "paused" | "waiting" | "blocked" | "done";

interface DemoState {
  status: DemoStatus;
  beat: number;
  label: string;
  caption: string;
  captions: boolean;
  message?: string;
  /** CSS selector the spotlight ring follows. */
  spotlight?: string;
  command?: DemoCommand;
  start: () => void;
  stop: (message?: string) => void;
  togglePause: () => void;
  next: () => void;
  /** Retry the current beat after a blocking error (e.g. once the missing service is connected). */
  retry: () => void;
  toggleCaptions: () => void;
}

export const useDemo = create<DemoState>((set, get) => ({
  status: "idle",
  beat: 0,
  label: "",
  caption: "",
  captions: false,
  start: () => {
    if (get().status !== "idle" && get().status !== "done") return;
    engine?.abort();
    engine = new DemoEngine();
    void engine.run();
  },
  stop: (message) => {
    engine?.abort();
    engine = undefined;
    set({ status: "idle", spotlight: undefined, message, beat: 0, label: "", caption: "" });
    if (message) setTimeout(() => useDemo.getState().message === message && set({ message: undefined }), 6_000);
  },
  togglePause: () => {
    const s = get().status;
    if (s === "running") set({ status: "paused" });
    else if (s === "paused") set({ status: "running" });
  },
  next: () => engine?.skip(),
  retry: () => engine?.requestRetry(),
  toggleCaptions: () => set((s) => ({ captions: !s.captions })),
}));

/** Subscribe a component to demo commands (setState inside a subscription, not during render). */
export function useDemoCommand(onCommand: (c: DemoCommand) => void) {
  const ref = useRef(onCommand);
  useEffect(() => {
    ref.current = onCommand;
  });
  useEffect(
    () =>
      useDemo.subscribe((s, prev) => {
        if (s.command && s.command !== prev.command) ref.current(s.command);
      }),
    [],
  );
}

// --------------------------------------------------------------------------- engine

class DemoAbort extends Error {}

export function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Multiplier on every reading hold (the waits for real people and services are not scaled). */
const DEFAULT_PACE = 1.2;

function pace(): number {
  if (typeof window === "undefined") return DEFAULT_PACE;
  const raw = new URLSearchParams(window.location.search).get("pace");
  const p = raw === null ? NaN : Number(raw);
  return Number.isFinite(p) && p >= 0.2 && p <= 5 ? p : DEFAULT_PACE;
}

function el<T extends Element = HTMLElement>(selector: string): T | null {
  return document.querySelector<T>(selector);
}

interface Beat {
  id: string;
  label: string;
  caption: string;
  /** Wall-clock budget for the beat's waits on real state, before it counts as failed. */
  run: (d: DemoEngine) => Promise<void>;
}

let engine: DemoEngine | undefined;
let commandId = 0;

export class DemoEngine {
  private aborted = false;
  private skipRequested = false;
  private retryRequested = false;
  private session = -1;
  private openedInference = false;
  readonly pace = pace();
  readonly reduce = reducedMotion();

  abort() {
    this.aborted = true;
    useDemo.setState({ spotlight: undefined });
    if (this.openedInference) closeInference();
  }

  skip() {
    this.skipRequested = true;
  }

  requestRetry() {
    this.retryRequested = true;
  }

  /**
   * Pause on a human input: show `prompt`, spotlight `selector`, and carry on once `probe` sees the real data.
   * Never times out; → skips, Esc exits. `fail` surfaces a real error (e.g. the run stopped) instead of waiting.
   */
  async awaitHuman<T>(
    prompt: string,
    probe: () => T | undefined | null | false,
    { selector, fail }: { selector?: string; fail?: () => string | undefined } = {},
  ): Promise<T | undefined> {
    const ready = probe();
    if (ready) return ready;
    useDemo.setState({ status: "waiting", message: prompt });
    if (selector) this.spotlight(selector);
    this.skipRequested = false;
    try {
      const v = await this.waitFor(() => probe() || (this.skipRequested ? ("skip" as const) : false), {
        timeout: Number.POSITIVE_INFINITY,
        fail,
      });
      return v === "skip" ? undefined : (v as T);
    } finally {
      this.skipRequested = false;
      this.spotlight(undefined);
      if (useDemo.getState().status === "waiting") useDemo.setState({ status: "running", message: undefined });
    }
  }

  private check() {
    if (this.aborted || engine !== this) throw new DemoAbort();
    if (this.session >= 0 && useAtelier.getState().session !== this.session) {
      // Someone pressed "Start over" (or picked another trend) mid-demo: hand the app back.
      throw new DemoAbort("session");
    }
  }

  private get paused() {
    const s = useDemo.getState().status;
    return s === "paused" || s === "blocked";
  }

  /** Pause-aware sleep. `skippable` holds end early on → (next beat). */
  async hold(ms: number, { skippable = true, scaled = true }: { skippable?: boolean; scaled?: boolean } = {}) {
    let left = scaled ? ms * this.pace : ms;
    while (left > 0) {
      this.check();
      if (skippable && this.skipRequested) {
        this.skipRequested = false;
        return;
      }
      await new Promise((r) => setTimeout(r, TICK_MS));
      if (!this.paused) left -= TICK_MS;
    }
    this.check();
  }

  /** Wait on real state. Throws on timeout or when `fail` reports an error (e.g. a request came back 5xx). */
  async waitFor<T>(
    probe: () => T | undefined | null | false,
    { timeout = 30_000, fail, what = "the backend" }: { timeout?: number; fail?: () => string | undefined; what?: string } = {},
  ): Promise<T> {
    let left = timeout;
    for (;;) {
      this.check();
      const v = probe();
      if (v) return v;
      const err = fail?.();
      if (err) throw new Error(err);
      if (left <= 0) throw new Error(`Timed out waiting for ${what}.`);
      await new Promise((r) => setTimeout(r, TICK_MS));
      if (!this.paused) left -= TICK_MS;
    }
  }

  async scrollTo(selector: string, { block = "start" }: { block?: "start" | "center" } = {}) {
    const target = el(selector);
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const top =
      block === "center"
        ? rect.top + window.scrollY - Math.max(SCROLL_OFFSET, (window.innerHeight - rect.height) / 2)
        : rect.top + window.scrollY - SCROLL_OFFSET;
    window.scrollTo({ top: Math.max(0, top), behavior: this.reduce ? "auto" : "smooth" });
    await this.hold(this.reduce ? 50 : 900, { skippable: false, scaled: false });
  }

  spotlight(selector?: string) {
    useDemo.setState({ spotlight: selector });
  }

  command(c: DemoCommandInput) {
    commandId += 1;
    useDemo.setState({ command: { ...c, id: commandId } as DemoCommand });
  }

  /** Click a real button when it's there and enabled; otherwise use the store action behind it. */
  async click(selector: string, fallback?: () => unknown) {
    const b = el<HTMLButtonElement>(selector);
    if (b && !b.disabled) b.click();
    else if (fallback) await fallback();
    else throw new Error("A control the demo needs is not on screen.");
  }

  async type(text: string) {
    if (this.reduce) {
      this.command({ type: "direct-text", text });
      return;
    }
    for (let i = 1; i <= text.length; i++) {
      this.command({ type: "direct-text", text: text.slice(0, i) });
      const ch = text[i - 1];
      await this.hold(ch === "," ? 260 : ch === " " ? 90 : 55, { skippable: false, scaled: false });
    }
  }

  openInference() {
    const b = el<HTMLButtonElement>('button[title="Inference stats"]');
    if (!b) return;
    b.click();
    this.openedInference = true;
  }

  closeInference() {
    if (!this.openedInference) return;
    closeInference();
    this.openedInference = false;
  }

  bindSession() {
    this.session = useAtelier.getState().session;
  }

  async run() {
    const set = useDemo.setState;
    set({ status: "running", message: undefined, beat: 0, command: undefined });
    try {
      for (let i = 0; i < BEATS.length; i++) {
        const beat = BEATS[i];
        set({ beat: i, label: beat.label, caption: beat.caption });
        this.skipRequested = false;
        for (let attempt = 1; ; attempt++) {
          try {
            await beat.run(this);
            break;
          } catch (err) {
            if (err instanceof DemoAbort) throw err;
            this.spotlight(undefined);
            if (attempt < 2) {
              await this.hold(900, { skippable: false, scaled: false });
              continue;
            }
            // Honest failure: show the real error (with the setup hint when a service is not connected) and wait.
            // R retries the beat (e.g. after connecting the service), → skips it, Esc takes over by hand.
            const why = err instanceof Error ? err.message : String(err);
            set({
              status: "blocked",
              message: `${beat.label} stopped: ${why} Press R to retry, → to skip, or Esc to drive by hand.`,
            });
            this.skipRequested = false;
            this.retryRequested = false;
            await this.waitFor(
              () => this.skipRequested || this.retryRequested || useDemo.getState().status !== "blocked",
              { timeout: Number.POSITIVE_INFINITY },
            );
            const again = this.retryRequested;
            this.skipRequested = false;
            this.retryRequested = false;
            set({ status: "running", message: undefined });
            if (again) {
              attempt = 0;
              continue;
            }
            break;
          }
        }
      }
      set({ status: "done", label: "Finished", caption: BEATS[BEATS.length - 1].caption });
    } catch (err) {
      if (!(err instanceof DemoAbort)) throw err;
      if (engine === this) {
        engine = undefined;
        useDemo.getState().stop(err.message === "session" ? "Demo stopped - the session was reset." : undefined);
      }
    }
  }
}

function closeInference() {
  // The panel closes on Escape; the demo's own key handler ignores synthetic (untrusted) events.
  if (el('[aria-label="Inference statistics"]')) {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  }
}

// --------------------------------------------------------------------------- beats

const atelier = () => useAtelier.getState();
const currentRun = (): PipelineRun | undefined => atelier().run;
const step = (key: string) => currentRun()?.steps.find((s) => s.key === key);
const stepDone = (key: string) => step(key)?.status === "done";

/**
 * v5: approving emails the brand's real suppliers, so the backend refuses (409) until the Brand workspace is set
 * up. The tour pauses here and points to /workspace; this polls the real status while it waits.
 */
let wsStatus: WorkspaceStatus | null = null;
let wsPolledAt = 0;
function workspaceReady(): WorkspaceStatus | null {
  const now = Date.now();
  if (now - wsPolledAt > 2_000) {
    wsPolledAt = now;
    getWorkspaceStatus()
      .then((st) => {
        wsStatus = st;
      })
      .catch(() => undefined);
  }
  return wsStatus?.ready ? wsStatus : null;
}
/** "<error> - Setup: <hint>" for a failed async state (a 503 carries the hint), else undefined. */
const failed = (s: AsyncState) =>
  s.status === "error" ? `${s.error ?? "Request failed."}${s.hint ? ` - Setup: ${s.hint}` : ""}` : undefined;

const runFailed = () => {
  const r = currentRun();
  const s = r?.steps.find((x) => x.status === "error");
  if (r?.status !== "failed" && !s) return undefined;
  const msg = s?.error ?? "The pipeline reported an error.";
  return `${msg}${s?.hint ? ` - Setup: ${s.hint}` : ""}${s?.retryable ? " (the run can be retried from the Production chapter)" : ""}`;
};

/** "This will email 3 suppliers: A → a@x (RFQ override inbox), …" for the presenter's confirmation. */
async function rfqRecipientsLine(designId?: string): Promise<string> {
  if (!designId) return "Approving emails your real suppliers (or their RFQ override inboxes).";
  try {
    const { recipients, sends } = await getRfqRecipients(designId);
    if (!recipients.length) return "Approving drafts RFQs, but the supplier directory is empty.";
    const list = recipients
      .map((r) => `${r.supplierName} → ${r.toEmail}${r.override ? " (RFQ override inbox)" : ""}`)
      .join("; ");
    const n = recipients.length;
    return sends
      ? `This will email ${n} supplier${n === 1 ? "" : "s"}: ${list}.`
      : `This drafts RFQs for ${n} supplier${n === 1 ? "" : "s"} (${list}); Evolus outreach is not connected, so nothing is sent.`;
  } catch (err) {
    return `Approving emails your real suppliers (or their RFQ override inboxes) - the list could not be loaded: ${errorMessage(err)}.`;
  }
}

/** The PO goes out automatically once the threshold is crossed: say to whom before waiting for pre-orders. */
function poRecipientLine(): string {
  const r = currentRun();
  const name = r?.recommendation?.selectedSupplierName ?? r?.recommendation?.supplierName;
  const email = r?.supplierEmails?.find((e) => e.supplierName === name)?.toEmail;
  if (!name) return "";
  return ` When the threshold is crossed, Atelier drafts the purchase order and sends it to ${name}${email ? ` (${email})` : ""} through Evolus.`;
}

const decisionOpen = () => {
  const d = currentRun()?.decision;
  return !!d && d.status !== "resolved";
};

const BEATS: Beat[] = [
  {
    id: "open",
    label: "Opening",
    caption: "Atelier: from a trend signal to a storefront, with a creative director in the chair.",
    run: async (d) => {
      if (atelier().analyze.status !== "idle") atelier().reset();
      window.scrollTo({ top: 0, behavior: "auto" });
      await d.waitFor(() => el('[data-demo^="preset-"]'), { timeout: 20_000, what: "the mood boards" });
      // Open on the landing hero, then hand off into the studio (chapter I) below it.
      await d.hold(3_000);
      await d.scrollTo("#chapter-trend");
      await d.hold(800);
    },
  },
  {
    id: "board",
    label: "Mood board",
    caption: "Start from a mood board - the agent reads the trend from the images.",
    run: async (d) => {
      const sel = `[data-demo="preset-${DEMO_PRESET}"]`;
      const target = el(sel) ? sel : '[data-demo^="preset-"]';
      await d.scrollTo(target, { block: "center" });
      d.spotlight(target);
      await d.hold(2_000);
      d.spotlight(undefined);
      await d.click(target, async () => {
        const p = (await getPresets()).find((x) => x.id === DEMO_PRESET);
        return atelier().runAnalyze({ kind: "preset", preset: DEMO_PRESET }, p ? [p.thumbnailUrl] : []);
      });
      d.bindSession();
      await d.waitFor(() => atelier().analyze.status === "done", {
        timeout: 120_000,
        fail: () => failed(atelier().analyze),
        what: "the trend analysis",
      });
    },
  },
  {
    id: "trend",
    label: "Trend read",
    caption: "The vision model names the trend, its silhouettes, palette, fabrics and commercial viability.",
    run: async (d) => {
      await d.scrollTo("#chapter-trend");
      await d.hold(6_000);
    },
  },
  {
    id: "voice",
    label: "Customer voice",
    caption: "What customers already said: reviews counted and quoted, turned into tech pack changes.",
    run: async (d) => {
      await d.waitFor(() => el('[data-demo="voice"]'), { what: "the customer voice panel" });
      const v = useVoice.getState();
      if (v.status !== "done" || v.input?.kind !== "sample" || v.input.key !== DEMO_VOICE_SAMPLE) {
        const sample = `[data-demo="voice-sample-${DEMO_VOICE_SAMPLE}"]`;
        await d.waitFor(() => el(sample), { timeout: 15_000, what: "the sample datasets" });
        await d.scrollTo(sample, { block: "center" });
        d.spotlight(sample);
        await d.hold(1_200, { skippable: false });
        d.spotlight(undefined);
        await d.click(sample, () =>
          useVoice.getState().analyse({ kind: "sample", key: DEMO_VOICE_SAMPLE, title: "Sample: Knits & sweaters" }),
        );
        await d.waitFor(() => useVoice.getState().status === "done", {
          timeout: 60_000,
          fail: () => useVoice.getState().error,
          what: "the customer voice analysis",
        });
      }
      await d.scrollTo('[data-demo="voice"]');
      await d.hold(3_500);
      const trendId = atelier().trend?.id;
      const applied = () => {
        const a = useVoice.getState().apply;
        return a.status === "done" && a.trendId === trendId;
      };
      if (!applied() && useVoice.getState().selected.length > 0) {
        d.spotlight('[data-demo="voice-apply"]');
        await d.hold(1_200, { skippable: false });
        await d.click('[data-demo="voice-apply"]', () => useVoice.getState().applyTo(trendId));
        await d.waitFor(applied, { timeout: 20_000, what: "the customer evidence" });
        d.spotlight(undefined);
      }
      await d.hold(2_500);
    },
  },
  {
    id: "concepts",
    label: "Concepts",
    caption: "Four garment concepts, rendered from the trend on the diffusion model.",
    run: async (d) => {
      const a = atelier();
      if (a.generate.status !== "done" && a.generate.status !== "loading") {
        await d.click('[data-demo="generate"]', () => atelier().runGenerate());
      }
      await d.waitFor(() => atelier().generate.status === "done", {
        timeout: 180_000,
        fail: () => failed(atelier().generate),
        what: "the concepts",
      });
      await d.scrollTo("#chapter-ideation");
      await d.hold(5_000);
    },
  },
  {
    id: "pick",
    label: "Pick a concept",
    caption: "The human keeps the taste: pick the concept that speaks to you.",
    run: async (d) => {
      const round = atelier().rounds.filter((r) => r.kind === "generate").at(-1);
      const id = round?.designIds[0];
      if (!id) throw new Error("No concepts to pick from.");
      const sel = `button[aria-label="Select concept No. ${atelier().labels[id]}"]`;
      d.spotlight(sel);
      await d.hold(1_600);
      d.spotlight(undefined);
      atelier().select(id);
      await d.waitFor(() => el('[data-demo="direction"]'), { what: "the vibe check" });
      await d.scrollTo("#chapter-vibe");
      await d.hold(2_000);
    },
  },
  {
    id: "direct",
    label: "Creative direction",
    caption: "Direct it the way you'd brief a studio - typed here, or spoken.",
    run: async (d) => {
      await d.scrollTo('[data-demo="direction"]', { block: "center" });
      const parent = atelier().selectedId;
      const already = atelier().rounds.some((r) => r.kind === "direct" && r.parentDesignId === parent);
      if (!already) {
        if (atelier().direct.status !== "loading") {
          await d.type(DEMO_DIRECTION);
          await d.hold(600, { skippable: false });
          // React re-renders the input before the Direct button enables; give it a frame.
          await d.hold(120, { skippable: false, scaled: false });
          await d.click('[data-demo="direct-submit"]', () => atelier().runDirect(DEMO_DIRECTION));
        }
        await d.waitFor(() => atelier().direct.status === "done", {
          timeout: 180_000,
          fail: () => failed(atelier().direct),
          what: "the creative direction",
        });
      }
    },
  },
  {
    id: "heard",
    label: "Atelier heard…",
    caption: "Atelier reads the direction back: palette, silhouette, references - and what goes into the tech pack.",
    run: async (d) => {
      await d.waitFor(() => el('[data-demo="heard"]'), { what: "the direction card" });
      await d.scrollTo('[data-demo="heard"]');
      await d.hold(7_000);
    },
  },
  {
    id: "variation",
    label: "Pick a variation",
    caption: "Four directed variations. Choose the strongest one.",
    run: async (d) => {
      const round = atelier().rounds.filter((r) => r.kind === "direct").at(-1);
      const id = round?.designIds[0];
      if (!id) throw new Error("No variations to pick from.");
      const sel = `button[aria-label="Select concept No. ${atelier().labels[id]}"]`;
      await d.scrollTo(sel, { block: "center" });
      d.spotlight(sel);
      await d.hold(2_000);
      d.spotlight(undefined);
      atelier().select(id);
      await d.scrollTo("#chapter-vibe");
      await d.hold(3_000);
    },
  },
  {
    id: "approve",
    label: "Approve",
    caption: "Approve for production - from here, the agents take over.",
    run: async (d) => {
      if (!atelier().runId) {
        await d.scrollTo('[data-demo="approve"]', { block: "center" });
        wsStatus = await getWorkspaceStatus().catch(() => null);
        wsPolledAt = Date.now();
        if (wsStatus && !wsStatus.ready) {
          await d.awaitHuman(
            `Set up the Brand workspace first: approving emails your real suppliers. Open Brand workspace ` +
              `(/workspace) and add ${wsStatus.missing.join("; ")}. The tour continues once it is ready.`,
            workspaceReady,
            { selector: '[data-demo="workspace-gate"]' },
          );
        }
        // Approving emails the brand's REAL suppliers. The tour never presses Approve: it names every address the
        // RFQs would go to and waits for the presenter to press it.
        const who = await rfqRecipientsLine(atelier().selectedId);
        await d.awaitHuman(
          `${who} Press Approve when you're ready - the tour never sends for you.`,
          () => atelier().runId || atelier().approve.status === "loading",
          { selector: '[data-demo="approve-button"]', fail: () => failed(atelier().approve) },
        );
      }
      await d.waitFor(() => atelier().runId, {
        timeout: 30_000,
        fail: () => failed(atelier().approve),
        what: "the approval",
      });
    },
  },
  {
    id: "pipeline",
    label: "Agent pipeline",
    caption: "Five agents in sequence, inside your brand guardrails: tech pack, outreach, quotes, pre-order, demand.",
    run: async (d) => {
      await d.waitFor(() => currentRun(), { what: "the pipeline" });
      await d.scrollTo("#chapter-production");
      await d.hold(3_500);
      await d.waitFor(() => stepDone("techpack") && currentRun()?.techPack, {
        timeout: 120_000,
        fail: runFailed,
        what: "the tech pack",
      });
      await d.hold(1_200);
    },
  },
  {
    id: "techpack",
    label: "Tech pack",
    caption: "The tech pack carries the direction and the customer evidence, with live costing.",
    run: async (d) => {
      await d.waitFor(() => el('[data-demo="techpack"]'), { what: "the tech pack" });
      await d.scrollTo('[data-demo="techpack"]');
      await d.hold(6_000);
    },
  },
  {
    id: "outreach",
    label: "RFQs",
    caption: "RFQs go out to the mills in each mill's own language, with the English alongside.",
    run: async (d) => {
      await d.waitFor(() => currentRun()?.supplierEmails?.length && el('[data-demo="outreach"]'), {
        timeout: 120_000,
        fail: runFailed,
        what: "supplier outreach",
      });
      const it = '[data-demo="rfq-it"]';
      const target = el(it) ? it : '[data-demo^="rfq-"]';
      const header = el<HTMLButtonElement>(`${target} > button`);
      if (header && header.getAttribute("aria-expanded") !== "true") header.click();
      await d.hold(500, { skippable: false, scaled: false });
      await d.scrollTo(target);
      d.spotlight(target);
      await d.hold(5_000);
      const toggle = el<HTMLButtonElement>(`${target} [data-demo="show-english"]`);
      if (toggle) {
        d.spotlight(`${target} [data-demo="show-english"]`);
        await d.hold(1_000, { skippable: false });
        toggle.click();
        d.spotlight(target);
        await d.hold(4_000);
      }
      d.spotlight(undefined);
    },
  },
  {
    id: "quotes",
    label: "Quotes",
    caption:
      "Mills reply with their quote documents; each is extracted field by field and the agent scores and recommends.",
    run: async (d) => {
      await d.waitFor(() => el('[data-demo="quotes"]'), { timeout: 120_000, fail: runFailed, what: "the quotes" });
      await d.scrollTo('[data-demo="quotes"]');
      await d.waitFor(() => currentRun()?.quoteRound, { timeout: 120_000, fail: runFailed, what: "the RFQ round" });
      // Real quotes come from real mills: wait for them (upload a document, or it arrives by email).
      await d.awaitHuman(
        "Waiting for a supplier quote - upload one in the Quotes panel or email it. (Press “Stop waiting & recommend” once the quotes you need are in.)",
        () => currentRun()?.recommendation && currentRun()?.guardrailReport,
        { selector: '[data-demo="quote-upload"]', fail: runFailed },
      );
      await d.waitFor(() => currentRun()?.recommendation && currentRun()?.guardrailReport, {
        timeout: 120_000,
        fail: runFailed,
        what: "the recommendation",
      });
      await d.hold(800, { skippable: false });
      await d.scrollTo('[data-demo="quotes"]');
      if (el('[data-demo="guardrail-breach"]')) d.spotlight('[data-demo="guardrail-breach"]');
      await d.hold(4_500);
      d.spotlight(undefined);
    },
  },
  {
    id: "handoff",
    label: "Hand-off",
    caption: "If the pick breaks a brand guardrail, the agent stops and asks a person - with the numbers and the options.",
    run: async (d) => {
      await d.waitFor(() => currentRun()?.decision || currentRun()?.guardrailReport?.selectedOk, {
        timeout: 30_000,
        fail: runFailed,
        what: "the guardrail check",
      });
      if (!decisionOpen()) return; // inside every guardrail: nothing to hand off
      await d.waitFor(() => el('[data-demo="decision"]'), { what: "the hand-off" });
      await d.scrollTo('[data-demo="decision"]');
      d.spotlight('[data-demo="decision"]');
      await d.hold(7_000);
      d.spotlight(undefined);
    },
  },
  {
    id: "negotiate",
    label: "Negotiate",
    caption: "Negotiate: a counter-offer in the mill's language at the price that meets the guardrails - the maths shown, English alongside.",
    run: async (d) => {
      const r = currentRun();
      if (!r || !decisionOpen()) return;
      if (!r.decision?.counterOffer) {
        d.spotlight('[data-demo="decision-negotiate"]');
        await d.hold(1_400, { skippable: false });
        // Same call as the button, made here so a 503 (no brain connected) surfaces with its setup hint.
        try {
          atelier().updateRun(await negotiateDecision(r.id));
        } catch (err) {
          const hint = errorHint(err);
          throw new Error(`${errorMessage(err)}${hint ? ` - Setup: ${hint}` : ""}`);
        }
        await d.waitFor(() => currentRun()?.decision?.counterOffer, { timeout: 60_000, what: "the counter-offer" });
        d.spotlight(undefined);
      }
      await d.waitFor(() => el('[data-demo="counter-offer"]'), { what: "the counter-offer" });
      await d.scrollTo('[data-demo="counter-offer"]');
      d.spotlight('[data-demo="counter-local"]');
      await d.hold(5_000);
      d.spotlight('[data-demo="counter-math"]');
      await d.hold(4_000);
      if (currentRun()?.decision?.counterOffer?.status === "draft") {
        // Sending emails a real mill: that is the creative director's call, not the tour's.
        const co = currentRun()?.decision?.counterOffer;
        await d.awaitHuman(
          `Review the counter-offer and press Send when you're ready - it emails ${co?.supplierName ?? "the mill"}` +
            `${co?.toEmail ? ` at ${co.toEmail}` : ""} for real. The tour never sends for you.`,
          () => currentRun()?.decision?.status === "negotiating" || !decisionOpen(),
          { selector: '[data-demo="counter-send"]', fail: runFailed },
        );
      }
      d.spotlight(undefined);
      await d.hold(1_500);
    },
  },
  {
    id: "revised",
    label: "Revised quote",
    caption: "The mill answers with a revised quote; if it passes the guardrails, the agent carries on.",
    run: async (d) => {
      const r = currentRun();
      const dec = r?.decision;
      if (!r || !dec || dec.status !== "negotiating") return;
      await d.scrollTo('[data-demo="quotes"]');
      await d.awaitHuman(
        `Waiting for ${dec.supplierName}'s revised quote - upload it in the Quotes panel, or it arrives by email.`,
        () => !decisionOpen(),
        { selector: '[data-demo="quote-upload"]', fail: runFailed },
      );
      await d.scrollTo('[data-demo="quotes"]');
      await d.hold(3_500);
      if (el('[data-demo="audit"]')) {
        await d.scrollTo('[data-demo="audit"]', { block: "center" });
        d.spotlight('[data-demo="audit"]');
        await d.hold(3_500);
        d.spotlight(undefined);
      }
    },
  },
  {
    id: "demand",
    label: "Pre-order demand",
    caption: "A real Shopify pre-order validates demand first: scan the code and pre-order - real orders must clear the threshold.",
    run: async (d) => {
      await d.waitFor(() => currentRun()?.shopifyProduct && el('[data-demo="storefront"]'), {
        timeout: 120_000,
        fail: runFailed,
        what: "the pre-order",
      });
      await d.scrollTo('[data-demo="storefront"]', { block: "center" });
      d.spotlight('[data-demo="storefront"]');
      await d.hold(3_000);
      d.spotlight(undefined);
      await d.waitFor(() => currentRun()?.demand && el('[data-demo="demand"]'), {
        timeout: 120_000,
        fail: runFailed,
        what: "the demand window",
      });
      await d.scrollTo('[data-demo="demand"]');
      await d.hold(4_000);
      // Real orders arrive in real time: wait for real people to pre-order.
      await d.awaitHuman(
        "Waiting for a real pre-order - scan the QR code and order. The tour carries on once the threshold is reached." +
          poRecipientLine(),
        () => currentRun()?.demand?.purchaseOrder || currentRun()?.demand?.status === "expired",
        { selector: '[data-demo="preorder-qr"]', fail: runFailed },
      );
    },
  },
  {
    id: "po",
    label: "Purchase order",
    caption: "Demand validated - a numbered PO is drafted at the agreed price and sent to the mill through Evolus.",
    run: async (d) => {
      await d.waitFor(() => el('[data-demo="po"]') ?? el('[data-demo="demand"]'), { what: "the PO" });
      await d.scrollTo(el('[data-demo="po"]') ? '[data-demo="po"]' : '[data-demo="demand"]', { block: "center" });
      d.spotlight('[data-demo="po"]');
      await d.hold(6_000);
      d.spotlight(undefined);
    },
  },
  {
    id: "inference",
    label: "Inference",
    caption: "Every model call, measured: model, host, GPU, latency and tokens per second.",
    run: async (d) => {
      d.openInference();
      await d.hold(6_000);
      d.closeInference();
      await d.hold(600, { skippable: false, scaled: false });
    },
  },
  {
    id: "close",
    label: "Tech pack PDF",
    caption: "A factory-ready tech pack PDF and a purchase order - from signal to storefront.",

    run: async (d) => {
      await d.scrollTo('[data-demo="techpack"]');
      d.spotlight('[data-demo="pdf"]');
      await d.hold(4_000);
    },
  },
];

export const DEMO_BEATS = BEATS.map((b) => ({ id: b.id, label: b.label, caption: b.caption }));
