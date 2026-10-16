"use client";

// v2 - Inference stats: a slide-over Sheet (opened from the header) and inline per-step stats.
// Honesty rule (v5): only measured calls exist. A call to the local test double (`fake: true`) is labelled
// "FAKE upstream" in red; nothing is shown until there is at least one real call.

import { useCallback, useEffect } from "react";
import { create } from "zustand";
import {
  errorMessage,
  getTelemetry,
  type InferenceCall,
  type ServiceTelemetry,
  type TelemetryResponse,
} from "@/lib/api";
import { useUi } from "@/lib/ui";
import { EmptyState, Eyebrow, IconButton, IconPulse, IconRefresh, InlineAlert, Sheet, Stat } from "./ds";
import { cx } from "./ds/tokens";

// --------------------------------------------------------------------------- formatting

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** "google/gemma-4-26B-A4B-it" -> "gemma-4-26B-A4B-it" */
export function shortModel(model?: string): string {
  if (!model) return "model";
  const tail = model.split("/").pop() || model;
  return tail.length > 28 ? `${tail.slice(0, 27)}…` : tail;
}

/** "AMD Instinct MI300X" -> "MI300X" */
export function shortGpu(gpu?: string): string | undefined {
  if (!gpu) return undefined;
  const m = gpu.match(/\b(MI\d{3}[A-Z]?)\b/i);
  return m ? m[1].toUpperCase() : gpu;
}

function secs(ms?: number): string | undefined {
  if (ms == null) return undefined;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${nf0.format(ms)}ms`;
}

const SERVICE_NAME: Record<string, string> = {
  llm: "LLM",
  vision: "Vision",
  diffusion: "Diffusion",
  evolus: "Evolus",
};

const PURPOSE_NAME: Record<string, string> = {
  techpack: "tech pack",
  rfq_emails: "RFQ drafts",
  trend_analysis: "trend read",
  design_render: "concept render",
  supplier_outreach: "outreach run",
  shopify_preorder: "pre-order run",
  supplier_rationale: "supplier rationale",
  creative_direction: "creative direction",
  quote_extraction: "quote extraction",
  rfq_polish: "RFQ polish (AI Tool)",
};

const ROUTE_LABEL: Record<string, string> = {
  "evolus-agent → AMD vLLM": "Evolus agent → AMD vLLM",
  "direct vLLM": "Direct vLLM",
  "evolus-extractor": "Evolus extractor",
  "evolus-ai-tool": "Evolus AI Tool",
  "amd-llm": "AMD LLM read",
  "amd-vlm": "AMD VLM read",
  "pdf-text-rules": "Local PDF parser",
};

/** v3: which real path produced a result. */
export function RouteTag({ route, className }: { route?: string; className?: string }) {
  if (!route) return null;
  const evolus = route.startsWith("evolus");
  return (
    <span
      title={evolus ? "Went through Evolus (the agent's own model runs on AMD)" : route}
      className={cx(
        "inline-flex h-5 shrink-0 items-center rounded-full px-2 font-mono text-[0.62rem] tracking-[0.04em]",
        evolus ? "bg-accent-soft text-accent" : "bg-ok-soft text-ok",
        className,
      )}
    >
      {ROUTE_LABEL[route] ?? route}
    </span>
  );
}

/** The compact one-liner, e.g. "gemma-4-26B-A4B-it · MI300X · 1,666 tok · 412 tok/s · 4.0s". */
export function callSummary(c: InferenceCall): string {
  const parts: string[] = [];
  if (c.service === "evolus") parts.push(c.model ?? "Evolus workflow");
  else parts.push(shortModel(c.model));
  const gpu = shortGpu(c.gpu);
  if (gpu && c.service !== "evolus") parts.push(gpu);
  if (!c.ok) {
    parts.push(`failed after ${secs(c.latencyMs)}`);
    return parts.join(" · ");
  }
  if (c.completionTokens != null) parts.push(`${nf0.format(c.completionTokens)} tok`);
  if (c.tokensPerSec != null) parts.push(`${nf0.format(c.tokensPerSec)} tok/s`);
  if (c.ttftMs != null) parts.push(`TTFT ${secs(c.ttftMs)}`);
  if (c.imagesPerSec != null) parts.push(`${nf1.format(c.imagesPerSec)} img/s`);
  parts.push(secs(c.latencyMs) ?? "");
  return parts.filter(Boolean).join(" · ");
}

// --------------------------------------------------------------------------- tags

/** "Measured" for a real call; red "FAKE upstream" for a call to the local test double. */
export function TruthTag({ fake, className }: { fake: boolean; className?: string }) {
  return (
    <span
      title={
        fake
          ? "FAKE UPSTREAM - not real: this call went to the local test double, not a real service."
          : "Measured on a real upstream call."
      }
      className={cx(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 font-mono text-[0.62rem] tracking-[0.04em]",
        fake ? "border border-bad bg-bad-soft font-semibold text-bad" : "bg-ok-soft text-ok",
        className,
      )}
    >
      {fake ? "FAKE upstream" : "Measured"}
    </span>
  );
}

// --------------------------------------------------------------------------- inline (pipeline steps)

/**
 * Per-step stats under a pipeline step card (latest three calls; failures stay visible so errors are explained).
 * The tags sit on their own line and the numbers wrap under them on a phone; side by side from `sm`. Renders
 * nothing when the step made no calls.
 */
export function StepTelemetry({ calls, className }: { calls?: InferenceCall[]; className?: string }) {
  if (!calls || calls.length === 0) return null;
  return (
    <ul className={cx("flex flex-col gap-2 border-t border-line pt-3", className)} aria-label="Inference for this step">
      {calls.slice(-3).map((c) => (
        <li key={c.id} className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
          <span className="flex shrink-0 flex-wrap gap-1.5">
            <TruthTag fake={c.fake} />
            <RouteTag route={c.route} />
          </span>
          <span
            className={cx("min-w-0 font-mono text-[0.7rem] leading-5 break-words", c.ok ? "text-fg-muted" : "text-bad")}
          >
            <span className="text-fg-faint">{PURPOSE_NAME[c.purpose] ?? c.purpose.replace(/_/g, " ")} · </span>
            {callSummary(c)}
          </span>
        </li>
      ))}
    </ul>
  );
}

// --------------------------------------------------------------------------- header button + panel

const POLL_OPEN_MS = 2_000;
const POLL_CLOSED_MS = 8_000;

/** Telemetry poller shared by the header control and the Menu (faster while the panel is open). */
export const useTelemetry = create<{ data?: TelemetryResponse; error?: string }>(() => ({}));

function useTelemetryPoller(open: boolean) {
  const load = useCallback(async () => {
    try {
      useTelemetry.setState({ data: await getTelemetry(40), error: undefined });
    } catch (err) {
      useTelemetry.setState({ error: errorMessage(err) });
    }
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await load();
      if (alive) timer = setTimeout(tick, open ? POLL_OPEN_MS : POLL_CLOSED_MS);
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [load, open]);
  return load;
}

/** The latest real (measured, not fake) model call, for the header's tok/s readout. */
export function lastRealCall(data?: TelemetryResponse): InferenceCall | undefined {
  return data?.calls.filter((c) => !c.fake).find((c) => c.service !== "evolus" && c.ok);
}

/**
 * Header control: a pill with the live tok/s of the last real call. Hidden until at least one real call exists
 * (the Menu can still open the panel). Also hosts the Inference panel (a Sheet), whoever opens it.
 */
export function InferenceButton() {
  const open = useUi((s) => s.inferenceOpen);
  const setOpen = useUi((s) => s.setInferenceOpen);
  const load = useTelemetryPoller(open);
  const data = useTelemetry((s) => s.data);
  const error = useTelemetry((s) => s.error);

  const realCalls = data?.calls.filter((c) => !c.fake) ?? [];
  const last = lastRealCall(data);
  return (
    <>
      {realCalls.length > 0 && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={open}
          title="Inference stats: measured per call"
          className="hidden h-10 items-center gap-2 rounded-full bg-paper-2 py-1 pr-1 pl-1 text-small text-fg transition-colors hover:bg-surface hover:shadow-e1 sm:inline-flex sm:pr-3.5"
        >
          <span className="relative grid size-8 place-items-center rounded-full bg-inverse text-on-inverse">
            <IconPulse size={15} />
            <span aria-hidden className={cx("absolute -top-0.5 -right-0.5 size-2.5 rounded-full border-2 border-paper-2", last ? "ds-live bg-ok" : "bg-fg-faint")} />
          </span>
          <span className="hidden font-mono text-micro tabular md:inline">
            {last?.tokensPerSec != null ? `${nf0.format(last.tokensPerSec)} tok/s` : "Inference"}
          </span>
        </button>
      )}
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        ariaLabel="Inference statistics"
        eyebrow={<Eyebrow tone={realCalls.length ? "ok" : "faint"} live={realCalls.length > 0}>Inference · measured per call</Eyebrow>}
        title={data?.gpuLabel ?? "Measured calls"}
        description={
          data?.gpuLabel
            ? "GPU label from AMD_GPU_LABEL. Numbers below are measured per call."
            : "AMD_GPU_LABEL is not set, so no hardware is claimed. Numbers below are measured per call."
        }
        headerActions={
          <IconButton label="Refresh" variant="ghost" onClick={() => void load()}>
            <IconRefresh size={16} />
          </IconButton>
        }
      >
        <InferenceBody data={data} error={error} />
      </Sheet>
    </>
  );
}

function InferenceBody({ data, error }: { data?: TelemetryResponse; error?: string }) {
  const services = data?.services ?? [];
  const calls = data?.calls ?? [];
  const fakeServices = new Set(calls.filter((c) => c.fake).map((c) => c.service));

  return (
    <div className="flex flex-col gap-8">
      {fakeServices.size > 0 && (
        <InlineAlert tone="bad" title="FAKE UPSTREAM - not real">
          Calls marked FAKE went to the local test double, not a real model. Their numbers say nothing about real
          hardware.
        </InlineAlert>
      )}
      {error && (
        <InlineAlert tone="bad" title="Couldn’t load telemetry">
          {error}
        </InlineAlert>
      )}
      {services.length === 0 && !error && (
        <EmptyState compact icon={<IconPulse size={18} />} title="No calls yet">
          Read a trend or generate concepts and the measured calls will show up here.
        </EmptyState>
      )}

      {services.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {services.map((s) => (
            <ServiceCard key={s.service} s={s} fake={fakeServices.has(s.service)} />
          ))}
        </ul>
      )}

      {calls.length > 0 && (
        <section>
          <Eyebrow className="mb-3">Recent calls</Eyebrow>
          <ol className="divide-y divide-line border-y border-line">
            {calls.map((c) => (
              <li key={c.id} className="flex flex-col gap-1.5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
                  <p className="min-w-0 truncate text-small font-medium text-fg">
                    {SERVICE_NAME[c.service] ?? c.service}
                    <span className="font-normal text-fg-muted"> · {PURPOSE_NAME[c.purpose] ?? c.purpose}</span>
                  </p>
                  <div className="flex shrink-0 items-center gap-2">
                    <time className="font-mono text-micro text-fg-faint" dateTime={c.startedAt}>
                      {new Date(c.startedAt).toLocaleTimeString([], { hour12: false })}
                    </time>
                    <RouteTag route={c.route} />
                    <TruthTag fake={c.fake} />
                  </div>
                </div>
                <p className={cx("font-mono text-micro break-words", c.ok ? "text-fg-muted" : "text-bad")}>
                  {callSummary(c)}
                  {c.endpointHost && <span className="text-fg-faint"> · {c.endpointHost}</span>}
                </p>
                {(c.error || c.detail) && <p className="font-mono text-micro break-words text-fg-faint">{c.error ?? c.detail}</p>}
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline justify-between gap-3 text-micro">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="font-mono text-fg tabular">{value}</dd>
    </div>
  );
}

function ServiceCard({ s, fake }: { s: ServiceTelemetry; fake: boolean }) {
  const headline =
    s.avgTokensPerSec != null
      ? `${nf0.format(s.avgTokensPerSec)}`
      : s.avgImagesPerSec != null
        ? nf1.format(s.avgImagesPerSec)
        : s.avgLatencyMs != null
          ? secs(s.avgLatencyMs)
          : "-";
  const unit = s.avgTokensPerSec != null ? "tok/s avg" : s.avgImagesPerSec != null ? "img/s avg" : "avg latency";
  return (
    <li className={cx("flex flex-col gap-4 rounded-panel border bg-surface p-4", fake ? "border-bad" : "border-line")}>
      <div className="flex items-center justify-between gap-2">
        <Eyebrow tone={fake ? "bad" : "ok"}>{SERVICE_NAME[s.service] ?? s.service}</Eyebrow>
        <TruthTag fake={fake} />
      </div>
      <Stat
        size="sm"
        value={headline}
        unit={unit}
        label={
          <span className="block truncate font-mono text-micro" title={s.lastModel}>
            {s.service === "evolus" ? s.lastModel : shortModel(s.lastModel)}
            {s.gpu && s.service !== "evolus" && <span className="text-fg-faint"> · {shortGpu(s.gpu)}</span>}
          </span>
        }
      />
      <dl className="flex flex-col gap-1 border-t border-line pt-3">
        <StatRow label="Calls" value={`${s.calls}${s.errors ? ` · ${s.errors} failed` : ""}`} />
        <StatRow label="Latency avg / p95" value={s.avgLatencyMs != null ? `${secs(s.avgLatencyMs)} / ${secs(s.p95LatencyMs)}` : undefined} />
        <StatRow label="Time to first token" value={secs(s.avgTtftMs)} />
        <StatRow label="Peak tok/s" value={s.peakTokensPerSec != null ? nf0.format(s.peakTokensPerSec) : undefined} />
        <StatRow
          label="Tokens in / out"
          value={s.promptTokens || s.completionTokens ? `${nf0.format(s.promptTokens)} / ${nf0.format(s.completionTokens)}` : undefined}
        />
        <StatRow label="Images" value={s.images ? nf0.format(s.images) : undefined} />
      </dl>
    </li>
  );
}
