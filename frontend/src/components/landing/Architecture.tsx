"use client";

import type { ReactNode } from "react";
import { Card, cx, Em, IconGrid, IconLayers, IconPulse, Label } from "@/components/ds";
import { useHealth } from "@/lib/health";
import { gemmaLabel } from "@/lib/models";
import { LandingSection, Reveal, SectionHead, ServiceMode } from "./primitives";

export function Architecture() {
  return (
    <LandingSection id="landing-stack">
      <SectionHead
        id="landing-stack-title"
        index="05"
        kicker="Under the hood"
        title={
          <>
            Open models, an orchestrator <Em>and Evolus building blocks.</Em>
          </>
        }
        lede="Open models served with vLLM and a diffusion server on AMD hardware; a FastAPI orchestrator that owns the business loop; Evolus for the brain and the outside world; a real Shopify store. Model names and the GPU below are what this instance reports right now."
      />

      <Reveal>
        <div className="grid items-start gap-0 lg:grid-cols-[minmax(0,0.85fr)_auto_minmax(0,1fr)_auto_minmax(0,1.7fr)]">
          <Node
            eyebrow="The desk"
            title="Atelier studio"
            sub="Next.js · React"
            body="Mood boards, concepts, direction, approval, the tech pack editor, quote documents, the pre-order tracker and the forecast."
          />

          <Connector label="REST · JSON" />

          <Node
            accent
            eyebrow="The loop"
            title="Orchestrator"
            sub="FastAPI · Python 3.12"
            body="Owns the typed contract and the five-step pipeline, records which real path produced each result, scores quotes, runs the pre-order gate, forecasts the run, renders the tech pack PDF and measures every inference call."
          />

          <Connector label="OpenAI-compatible · Evolus · Shopify Admin" />

          <div className="flex flex-col gap-3">
            <Group title="AMD models" sub={<GpuLabel />}>
              <Service name="llm" fallback="LLM" role="Tech pack, direction, RFQs, supplier rationale" />
              <Service name="vision" fallback="Vision-language model" role="Reads the trend from the mood board" />
              <Service name="diffusion" fallback="Diffusion model" role="Concept and variation renders" />
            </Group>
            <Group title="Evolus" sub="Driven through the Evolus API">
              <Service name="evolus_agent" title="Agent · the brain" role="Runs on the AMD model, grounded in a knowledge library (brand book, supplier catalogue)" />
              <Service name="evolus_extractor" title="Document extractor" role="Reads the mills' quote documents, field by field" />
              <Service name="evolus_outreach" title="Outreach workflow" role="Sends RFQs and counter-offers; email quotes come back by webhook" />
              <Service name="evolus_po" title="PO workflow" role="Sends the purchase order to the mill" />
            </Group>
            <Group title="Shopify" sub="Admin API · dev store">
              <Service name="shopify" title="Pre-order store" role="The real product page and the orders that unlock production" />
            </Group>
          </div>
        </div>
      </Reveal>

      <Reveal className="mt-12 grid gap-3 sm:grid-cols-3 sm:gap-4">
        <Fact icon={<IconLayers size={18} />} title="Honest by default">
          A step whose service is not connected stops with the error and a setup hint, and can be retried. Quotes,
          orders and renders are never invented; a local test double is labelled FAKE in red.
        </Fact>
        <Fact icon={<IconPulse size={18} />} title="Measured">
          Every model call records model, host, GPU, latency and tokens per second; the Inference panel in the header
          shows them.
        </Fact>
        <Fact icon={<IconGrid size={18} />} title="One contract">
          Studio and orchestrator share a typed API contract; every result records which real path produced it.
        </Fact>
      </Reveal>
      <p className="mt-5 text-micro text-pretty text-fg-faint">
        Model names, GPU and badges show what this instance is actually calling, from{" "}
        <span className="font-mono">/api/health</span>; a service that is not connected names no model.
      </p>
    </LandingSection>
  );
}

function Node({
  eyebrow,
  title,
  sub,
  body,
  accent,
}: {
  eyebrow: string;
  title: string;
  sub: string;
  body: string;
  accent?: boolean;
}) {
  return (
    <Card pad="md" variant={accent ? "inverse" : "surface"} className="flex flex-col lg:sticky lg:top-28">
      <Label as="p">
        {eyebrow}
      </Label>
      <p className="mt-3 text-display-m text-fg">{title}</p>
      <p className="mt-1.5 font-mono text-micro text-fg-faint">{sub}</p>
      <p className="mt-5 text-small text-pretty text-fg-muted">{body}</p>
    </Card>
  );
}

/** The GPU as reported by /api/health (AMD_GPU_LABEL or the diffusion server's device) - never assumed. */
function GpuLabel() {
  const health = useHealth((s) => s.health);
  const gpu =
    health.kind === "ok"
      ? health.data.services.find((s) => s.gpu && s.status === "connected" && !s.fake)?.gpu
      : undefined;
  return <>{gpu ? `${gpu} · vLLM` : "GPU: not reported"}</>;
}

function Group({ title, sub, children }: { title: string; sub: ReactNode; children: ReactNode }) {
  return (
    <Card pad="none" className="px-5 pt-4 pb-1 sm:px-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-title text-fg">{title}</p>
        <p className="font-mono text-micro text-fg-faint">{sub}</p>
      </div>
      <ul className="mt-3 divide-y divide-line border-t border-line">{children}</ul>
    </Card>
  );
}

function Service({ name, title, fallback, role }: { name: string; title?: string; fallback?: string; role: string }) {
  const health = useHealth((s) => s.health);
  const svc = health.kind === "ok" ? health.data.services.find((s) => s.name === name) : undefined;
  // Model names only come from the health probe of a connected service; otherwise say so.
  const connected = svc?.status === "connected" && !!svc.model;
  const shown = title ?? (connected ? svc.model : (fallback ?? name));
  // v6: the family label is derived from the served id + GPU label, and only for a real (not fake) endpoint.
  const family = !title && connected ? gemmaLabel(svc.model, svc.gpu, svc.fake) : undefined;
  return (
    <li className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        {family && <p className="text-small font-medium text-accent">{family}</p>}
        <p className={cx("text-small break-words text-fg", !title && "font-mono")}>{shown}</p>
        <p className="mt-0.5 text-small text-pretty text-fg-muted">{role}</p>
      </div>
      <ServiceMode name={name} className="self-start" />
    </li>
  );
}

/** An ink connector: vertical when stacked, horizontal with an arrowhead on wide screens. */
function Connector({ label }: { label: string }) {
  return (
    <div aria-hidden className="flex items-center justify-center py-3 lg:sticky lg:top-28 lg:px-3 lg:py-0 lg:pt-28">
      <div className="flex flex-row items-center gap-3 lg:flex-col lg:gap-2.5">
        <svg className="h-10 w-3 lg:hidden" viewBox="0 0 12 40" fill="none">
          <path d="M6 0V38M1.5 33.5 6 38l4.5-4.5" stroke="var(--fg)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <svg className="hidden h-3 w-14 lg:block" viewBox="0 0 56 12" fill="none">
          <path d="M0 6H54M49.5 1.5 54 6l-4.5 4.5" stroke="var(--fg)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <Label className="max-w-[16rem] leading-tight lg:max-w-[7rem] lg:text-center">{label}</Label>
      </div>
    </div>
  );
}

function Fact({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card variant="muted" pad="md">
      <span className="grid size-10 place-items-center rounded-full bg-surface text-fg">{icon}</span>
      <p className="mt-5 text-title text-fg">{title}</p>
      <p className="mt-2 text-small text-pretty text-fg-muted">{children}</p>
    </Card>
  );
}
