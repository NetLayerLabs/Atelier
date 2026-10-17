"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  createContext,
  useContext,
  useRef,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from "react";
import { C, Card, cx, DUR, EASE, Em, IconGrid, IconLayers, IconPulse, INSTANT, Label } from "@/components/ds";
import { useHealth } from "@/lib/health";
import { gemmaLabel } from "@/lib/models";
import { prefersReducedMotion } from "../ui";
import { useHealthBeat, useInViewPause, useReducedMotionSafe } from "./motion";
import { LandingSection, REVEAL_RISE, SectionHead, ServiceMode, STAGGER, useArm } from "./primitives";

/*
 * The diagram assembles along the request path, once, as it scrolls in: the studio rises, connector 1 draws (shaft,
 * then arrowhead), the black orchestrator rises, connector 2 draws, then the AMD models, Evolus and Shopify groups
 * cascade, their rows a beat apart. Each block is its own Stage. On wide screens they share one row, so they arm
 * together and these cues (ms) compose a single run of 1.6 s at most; on phones the blocks are stacked a screen
 * apart, so each one plays as it arrives and only the offsets inside a block apply.
 */
const RUN = { studio: 0, wire1: 250, orchestrator: 450, wire2: 650, groups: 850 } as const;
const GROUP_GAP = 90;
const ROW_GAP = 50;

/** When a block plays once its stage is shown: on phones and, when it differs, on wide screens. */
function cue(ms: number, lg = ms): CSSProperties {
  return { "--d": `${ms}ms`, "--d-lg": `${lg}ms` } as CSSProperties;
}

/** Holds a stage child back by its cue (see cue). Hidden states only ever apply while the stage is armed. */
const CUED = "in-data-[reveal=shown]:delay-(--d) lg:in-data-[reveal=shown]:delay-(--d-lg)";
const GROUP_RISE =
  "transition-[opacity,translate] duration-[550ms] ease-thread in-data-[reveal=armed]:translate-y-[8px] in-data-[reveal=armed]:opacity-0";
const ROW_RISE =
  "transition-[opacity,translate] duration-500 ease-thread in-data-[reveal=armed]:translate-y-[4px] in-data-[reveal=armed]:opacity-0";
const FADE = "transition-opacity duration-[600ms] ease-thread in-data-[reveal=armed]:opacity-0";
/** A connector stroke measured out from its start (pathLength 1: one dash covers it, offset 1 hides it). */
const DRAW =
  "[stroke-dasharray:1_2] transition-[stroke-dashoffset] ease-thread in-data-[reveal=armed]:[stroke-dashoffset:1]";

/**
 * <Reveal variant="stage">'s contract (useArm: never hidden in the server HTML, without JS or under reduced motion;
 * armed only below the fold after hydration) with a later cue: a block plays once it is a fifth of the way up the
 * screen, so a connector (7rem under the row's top on wide screens) is seen drawing instead of finishing below the
 * fold. A reader who stops with a block just peeking in is not left looking at a blank strip: it plays after 1.2 s
 * on screen. It only writes data-reveal; its children choreograph themselves and the wrapper never moves.
 */
function Stage({
  className,
  children,
  ...rest
}: { className?: string; children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null);
  const state = useArm(ref, { rootMargin: "0px 0px -22% 0px", safetyMs: 1200 });
  return (
    <div ref={ref} data-reveal={state} className={className} {...rest}>
      {children}
    </div>
  );
}

export function Architecture() {
  // The service badges' live dots loop (ds Badge): hold them still while the diagram is off-screen.
  const diagram = useRef<HTMLDivElement>(null);
  useInViewPause(diagram);

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
        lede="Open models on AMD GPUs (Gemma 4, through AMD Token Factory or our own vLLM server); a FastAPI orchestrator that owns the business loop; Evolus for the brain and the outside world; a real Shopify store. Model names and the GPU below are what this instance reports right now."
      />

      <div
        ref={diagram}
        className="grid items-start gap-0 lg:grid-cols-[minmax(0,0.85fr)_auto_minmax(0,1fr)_auto_minmax(0,1.7fr)]"
      >
        <Node
          at={RUN.studio}
          eyebrow="The desk"
          title="Atelier studio"
          sub="Next.js · React"
          body="Mood boards, concepts, direction, approval, the tech pack editor, quote documents, the pre-order tracker and the forecast."
        />

        <Connector at={RUN.wire1} label="REST · JSON" beat />

        <Node
          accent
          at={RUN.orchestrator}
          eyebrow="The loop"
          title="Orchestrator"
          sub="FastAPI · Python 3.12"
          body="Owns the typed contract and the five-step pipeline, records which real path produced each result, scores quotes, runs the pre-order gate, forecasts the run, renders the tech pack PDF and measures every inference call."
        />

        <Connector at={RUN.wire2} label="OpenAI-compatible · Evolus · Shopify Admin" />

        <Stage className="flex flex-col gap-3">
          <Group order={0} title="AMD models" sub={<GpuLabel />}>
            <IfConnected name="llm">
              <Service i={0} name="llm" fallback="LLM" role="Direct backup for the agent: tech pack, direction, RFQs" />
            </IfConnected>
            <Service i={1} name="vision" fallback="Vision-language model" role="Reads the trend from the mood board" />
            <IfConnected name="diffusion">
              <Service i={2} name="diffusion" fallback="Diffusion model" role="Concept and variation renders" />
            </IfConnected>
          </Group>
          <Group order={1} title="Evolus" sub="Driven through the Evolus API">
            <Service i={0} name="evolus_agent" title="Agent · the brain" role="Runs on the AMD model, grounded in a knowledge library (brand book, supplier catalogue)" />
            <Service i={1} name="evolus_extractor" title="Document extractor" role="Reads the mills' quote documents, field by field" />
            <Service i={2} name="evolus_outreach" title="Outreach workflow" role="Sends RFQs and counter-offers; email quotes come back by webhook" />
            <Service i={3} name="evolus_po" title="PO workflow" role="Sends the purchase order to the mill" />
          </Group>
          <Group order={2} title="Shopify" sub="Admin API · dev store">
            <Service i={0} name="shopify" title="Pre-order store" role="The real product page and the orders that unlock production" />
          </Group>
        </Stage>
      </div>

      <Stage className="mt-12 grid gap-3 sm:grid-cols-3 sm:gap-4">
        <Fact i={0} icon={<IconLayers size={18} />} title="Honest by default">
          A step whose service is not connected stops with the error and a setup hint, and can be retried. Quotes,
          orders and renders are never invented; a local test double is labelled FAKE in red.
        </Fact>
        <Fact i={1} icon={<IconPulse size={18} />} title="Measured">
          Every model call records model, host, GPU, latency and tokens per second; the Inference panel in the header
          shows them.
        </Fact>
        <Fact i={2} icon={<IconGrid size={18} />} title="One contract">
          Studio and orchestrator share a typed API contract; every result records which real path produced it.
        </Fact>
      </Stage>
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
  at,
}: {
  eyebrow: string;
  title: string;
  sub: string;
  body: string;
  accent?: boolean;
  /** Cue on wide screens (ms). */
  at: number;
}) {
  return (
    // The sticky wrapper only arms (a stage never moves); the card inside rises and leaves no transform behind.
    <Stage className="lg:sticky lg:top-28">
      <Card
        pad="md"
        variant={accent ? "inverse" : "surface"}
        className={cx("flex flex-col", REVEAL_RISE, CUED)}
        style={cue(0, at)}
      >
        <Label as="p">
          {eyebrow}
        </Label>
        <p className="mt-3 text-display-m text-fg">{title}</p>
        <p className="mt-1.5 font-mono text-micro text-fg-faint">{sub}</p>
        <p className="mt-5 text-small text-pretty text-fg-muted">{body}</p>
      </Card>
    </Stage>
  );
}

/**
 * A name read from /api/health, resolved in place: when it changes (the fallback becomes what this instance reports
 * on the first answer) the old one lifts out as the new one settles in. Polls that report the same name animate
 * nothing; the server HTML and the first paint never animate. `anchor`: the side the outgoing name holds to (the
 * one that stays put when the width changes).
 */
function Resolve({ value, anchor = "left" }: { value?: string; anchor?: "left" | "right" }) {
  const reduce = useReducedMotionSafe();
  return (
    <span className="relative block">
      <AnimatePresence initial={false} mode="popLayout" anchorX={anchor}>
        {value !== undefined && (
          <motion.span
            key={value}
            className="block"
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -3 }}
            transition={reduce ? INSTANT : { duration: DUR.ui, ease: EASE }}
          >
            {value}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/** The GPU as reported by /api/health (AMD_GPU_LABEL or the diffusion server's device) - never assumed, never
 * embellished: the serving stack is whatever the label says. */
function GpuLabel() {
  const health = useHealth((s) => s.health);
  const gpu =
    health.kind === "ok"
      ? health.data.services.find((s) => s.gpu && s.status === "connected" && !s.fake)?.gpu
      : undefined;
  // It sits at the right end of its group's header row.
  return <Resolve value={gpu ?? "GPU: not reported"} anchor="right" />;
}

/** A group's cues (ms, phones / wide screens): its rows enter with the card, a beat apart. */
const GroupCue = createContext({ ms: 0, lg: 0 });

function Group({ title, sub, order, children }: { title: string; sub: ReactNode; order: number; children: ReactNode }) {
  const ms = order * GROUP_GAP;
  const lg = RUN.groups + ms;
  return (
    <Card pad="none" className={cx("px-5 pt-4 pb-1 sm:px-6", GROUP_RISE, CUED)} style={cue(ms, lg)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-title text-fg">{title}</p>
        <p className="font-mono text-micro text-fg-faint">{sub}</p>
      </div>
      <ul className="mt-3 divide-y divide-line border-t border-line">
        <GroupCue.Provider value={{ ms, lg }}>{children}</GroupCue.Provider>
      </ul>
    </Card>
  );
}

/** Optional parts (the direct vLLM backup, the diffusion server) are listed only while they are connected. */
function IfConnected({ name, children }: { name: string; children: ReactNode }) {
  const health = useHealth((s) => s.health);
  const svc = health.kind === "ok" ? health.data.services.find((s) => s.name === name) : undefined;
  return svc?.status === "connected" ? <>{children}</> : null;
}

function Service({
  name,
  title,
  fallback,
  role,
  i,
}: {
  name: string;
  title?: string;
  fallback?: string;
  role: string;
  /** Row index in its group, for the cascade. */
  i: number;
}) {
  const group = useContext(GroupCue);
  const health = useHealth((s) => s.health);
  const svc = health.kind === "ok" ? health.data.services.find((s) => s.name === name) : undefined;
  // Model names only come from the health probe of a connected service; otherwise say so.
  const connected = svc?.status === "connected" && !!svc.model;
  const shown = title ?? (connected ? svc.model : (fallback ?? name));
  // v6: the family label is derived from the served id + GPU label, and only for a real (not fake) endpoint.
  const family = !title && connected ? gemmaLabel(svc.model, svc.gpu, svc.fake) : undefined;
  const row = i * ROW_GAP; // with its card, then a beat apart: Evolus' fourth row lands at 1.59 s
  return (
    <li
      className={cx(
        "flex flex-col gap-2 py-3.5 sm:flex-row sm:items-start sm:justify-between sm:gap-4",
        ROW_RISE,
        CUED,
      )}
      style={cue(group.ms + row, group.lg + row)}
    >
      <div className="min-w-0">
        {!title && (
          <p className="text-small font-medium text-accent">
            <Resolve value={family} />
          </p>
        )}
        <p className={cx("text-small break-words text-fg", !title && "font-mono")}>
          <Resolve value={shown} />
        </p>
        <p className="mt-0.5 text-small text-pretty text-fg-muted">{role}</p>
      </div>
      <ServiceMode name={name} className="self-start" />
    </li>
  );
}

/**
 * An ink connector: vertical when stacked (drawn downward), horizontal with an arrowhead on wide screens. It is
 * measured out from its start when it scrolls in: the shaft, then the arrowhead opening at the tip, then its label.
 * With `beat`, an ink bead runs along it each time the studio's real health check returns (see Heartbeat).
 */
function Connector({
  label,
  at,
  beat,
}: {
  label: string;
  /** Cue on wide screens (ms). */
  at: number;
  beat?: boolean;
}) {
  const wire = useRef<HTMLDivElement>(null);
  return (
    <Stage
      aria-hidden
      className="flex items-center justify-center py-3 lg:sticky lg:top-28 lg:px-3 lg:py-0 lg:pt-28"
    >
      <div
        ref={wire}
        title={beat ? "Pulses each time the studio's health check returns" : undefined}
        className="flex flex-row items-center gap-3 lg:flex-col lg:gap-2.5"
      >
        <svg className="h-10 w-3 lg:hidden" viewBox="0 0 12 40" fill="none">
          <Wire at={at} shaft="M6 0V38" head={["M6 38 1.5 33.5", "M6 38 10.5 33.5"]} />
          {beat && <circle data-bead="0 28" cx="6" cy="2" r="2" fill={C.fg} opacity="0" />}
        </svg>
        <svg className="hidden h-3 w-14 lg:block" viewBox="0 0 56 12" fill="none">
          <Wire at={at} shaft="M0 6H54" head={["M54 6 49.5 1.5", "M54 6 49.5 10.5"]} />
          {beat && <circle data-bead="44 0" cx="2" cy="6" r="2" fill={C.fg} opacity="0" />}
        </svg>
        <div className={cx("max-w-[16rem] lg:max-w-[7rem] lg:text-center", FADE, CUED)} style={cue(100, at + 100)}>
          <Label as="p" className="leading-tight">
            {label}
          </Label>
        </div>
      </div>
      {beat && <Heartbeat wire={wire} />}
    </Stage>
  );
}

/** One connector's strokes: the shaft is drawn from its start, then the arrowhead's two barbs open from the tip. */
function Wire({ shaft, head, at }: { shaft: string; head: string[]; at: number }) {
  return (
    <g stroke={C.fg} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d={shaft} pathLength={1} className={cx(DRAW, "duration-500", CUED)} style={cue(0, at)} />
      {head.map((d) => (
        <path key={d} d={d} pathLength={1} className={cx(DRAW, "duration-[250ms]", CUED)} style={cue(280, at + 280)} />
      ))}
    </g>
  );
}

const THREAD = `cubic-bezier(${EASE.join(", ")})`;

/**
 * The diagram's one honest heartbeat: each real GET /api/health answer (kind "ok") sends one ink bead from the studio
 * to the orchestrator along connector 1, in about 0.6 s. Only while the connector is on screen and drawn, the tab is
 * visible and motion is not reduced; it follows the header's shared poll and never runs a timer of its own.
 * Connector 2 never pulses: the backend caches its probes of the upstream services, so a bead there would overstate.
 */
function Heartbeat({ wire }: { wire: RefObject<HTMLDivElement | null> }) {
  useInViewPause(wire);
  useHealthBeat(() => {
    const el = wire.current;
    if (!el || prefersReducedMotion() || el.hasAttribute("data-paused") || el.closest('[data-reveal="armed"]')) return;
    el.querySelectorAll<SVGCircleElement>("circle[data-bead]").forEach((bead) => {
      if (!bead.getClientRects().length) return; // the other breakpoint's connector (display: none)
      // Thrown like a shuttle: visible from the studio at once, settling (and fading) into the arrowhead.
      const [x, y] = (bead.dataset.bead ?? "0 0").split(" ");
      bead.animate({ transform: ["translate(0, 0)", `translate(${x}px, ${y}px)`] }, { duration: 600, easing: THREAD });
      bead.animate({ opacity: [0, 1, 1, 0], offset: [0, 0.06, 0.45, 1] }, { duration: 600 });
    });
  });
  return null;
}

function Fact({ icon, title, i, children }: { icon: ReactNode; title: string; i: number; children: ReactNode }) {
  return (
    <Card variant="muted" pad="md" className={cx(REVEAL_RISE, CUED)} style={cue(i * STAGGER.sibling)}>
      <span className="grid size-10 place-items-center rounded-full bg-surface text-fg">{icon}</span>
      <p className="mt-5 text-title text-fg">{title}</p>
      <p className="mt-2 text-small text-pretty text-fg-muted">{children}</p>
    </Card>
  );
}
