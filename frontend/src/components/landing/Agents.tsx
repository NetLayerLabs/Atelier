"use client";

import { useMotionValueEvent, useScroll, useSpring } from "framer-motion";
import { useEffect, useRef, type CSSProperties, type RefObject } from "react";
import { Card, cx, Em, Label } from "@/components/ds";
import { SERVICE_SHORT } from "@/lib/health";
import { AGENTS } from "./data";
import { useReducedMotionSafe } from "./motion";
import { LandingSection, Reveal, SectionHead, ServiceMode, STAGGER, useArm } from "./primitives";

/*
 * Each row reads left to right as it scrolls in: who (with its services), what it takes, what it hands on, what it
 * runs on, STAGGER.sibling apart, on top of the rows' own 60 ms stagger (the stage Reveal's --reveal-delay). In row
 * 03 the guardrail hand-off lands last and an ink rule draws down its edge: the moment the agent stops and hands you
 * the call. Hidden states apply only while a row is armed, so the server HTML, no-JS and reduced motion show it all.
 */
const AFTER = "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)_+_var(--beat,0ms))]";
const RISE_IN =
  "transition-[opacity,translate] ease-thread in-data-[reveal=armed]:translate-y-2 in-data-[reveal=armed]:opacity-0";
const ENTER = cx(RISE_IN, AFTER, "duration-600");
/** The hand-off panel: it lands last, at HAND_OFF, and is in place by 0.9 s like the rest of the row. */
const LAND = cx(RISE_IN, AFTER, "duration-500");
const HAND_OFF = 400;
/** A child's own beat within its row, in ms (read by AFTER). */
const beat = (ms: number) => ({ "--beat": `${ms}ms` }) as CSSProperties;

export function Agents() {
  const listRef = useRef<HTMLOListElement>(null);
  useThread(listRef);

  return (
    <LandingSection id="landing-agents">
      <SectionHead
        id="landing-agents-title"
        index="03"
        kicker="The agents"
        title={
          <>
            After approval, <Em>five agents take over.</Em>
          </>
        }
        lede="They run in sequence on the approved design, each handing a typed artifact to the next. Quotes are read from real documents, pre-orders are real Shopify orders, and the PO goes out through Evolus. If a service is missing, that step stops with a setup hint - nothing is made up."
      />

      <Card pad="none" className="overflow-hidden">
        <div className="hidden grid-cols-12 gap-8 border-b border-line px-8 py-3.5 lg:grid">
          <Label className="col-span-3">Agent · backing service</Label>
          <Label className="col-span-4">Takes</Label>
          <Label className="col-span-5">Hands on</Label>
        </div>
        <ol ref={listRef} className="relative divide-y divide-line">
          {AGENTS.map((a, i) => {
            const last = i === AGENTS.length - 1;
            return (
              <Reveal
                as="li"
                variant="stage"
                key={a.n}
                delay={i * 60}
                className="relative grid gap-4 px-5 py-6 sm:px-8 sm:py-7 lg:grid-cols-12 lg:gap-8"
              >
                {/* The thread, in the row's left padding: a segment down to the next agent's node, or the threshold. */}
                {last ? (
                  <span
                    aria-hidden
                    className="absolute top-[calc(2.6rem-0.5px)] left-[calc(1rem-11px)] hidden h-px w-[23px] bg-[linear-gradient(90deg,var(--line-bold)_0_3px,transparent_3px_5px)] bg-size-[5px_1px] sm:block"
                  >
                    <span
                      data-thread-tick
                      className="absolute inset-0 bg-fg transition-[scale] duration-450 ease-thread data-[on=false]:scale-x-0"
                    />
                  </span>
                ) : (
                  <span
                    aria-hidden
                    className="absolute top-[2.6rem] bottom-[calc(-2.6rem-1px)] left-4 hidden w-px bg-line-strong sm:block"
                  >
                    <span data-thread-fill className="absolute inset-0 origin-top bg-fg" />
                  </span>
                )}
                <span
                  aria-hidden
                  data-thread-node
                  className="absolute top-[calc(2.6rem-3.5px)] left-[calc(1rem-3px)] hidden size-[7px] rounded-full border border-fg bg-fg transition-colors duration-300 ease-thread data-[on=false]:border-line-bold data-[on=false]:bg-surface sm:block"
                />

                <div className={cx("lg:col-span-3", ENTER)}>
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-small text-fg-faint tabular">{a.n}</span>
                    <h3 className="text-title text-fg">{a.name}</h3>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5 2xl:pl-8">
                    {a.services.map((s) => (
                      <ServiceMode key={s} name={s} label={SERVICE_SHORT[s] ?? s} className="max-w-none!" />
                    ))}
                  </div>
                </div>
                <div className={cx("lg:col-span-4", ENTER)} style={beat(STAGGER.sibling)}>
                  <Label as="p" className="lg:hidden">
                    Takes
                  </Label>
                  <p className="mt-1 text-body text-pretty text-fg-muted lg:mt-0">{a.input}</p>
                </div>
                <div className="lg:col-span-5">
                  <div className={ENTER} style={beat(2 * STAGGER.sibling)}>
                    <Label as="p" className="lg:hidden">
                      Hands on
                    </Label>
                    <p className="mt-1 text-body text-pretty text-fg lg:mt-0">{a.output}</p>
                  </div>
                  {a.note && (
                    <p
                      className={cx("relative mt-3 rounded-panel bg-paper-2 px-4 py-3 text-small text-pretty text-fg", LAND)}
                      style={beat(HAND_OFF)}
                    >
                      {/* drawn down the straight part of the edge (inside the panel's radius) as the panel lands */}
                      <span
                        aria-hidden
                        className={cx(
                          "absolute inset-y-5 left-0 w-[2px] origin-top bg-fg transition-[scale] duration-400 ease-thread in-data-[reveal=armed]:scale-y-0",
                          AFTER,
                        )}
                        style={beat(HAND_OFF + 100)}
                      />
                      <span className="font-medium text-fg">Guardrail hand-off. </span>
                      {a.note}
                    </p>
                  )}
                  <p
                    className={cx("mt-3 text-small text-pretty text-fg-faint", ENTER)}
                    style={beat(3 * STAGGER.sibling)}
                  >
                    <span className="text-fg-muted">Runs on · </span>
                    {a.engine}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </ol>
      </Card>
      <p className="mt-5 max-w-3xl text-micro text-pretty text-fg-faint">
        Badges show each agent&rsquo;s backing service right now, from <span className="font-mono">/api/health</span>.
        A failed step can be retried once its service is back.
      </p>
    </LandingSection>
  );
}

type Thread = {
  /** The list's height: the fill's tip sits at progress × height, between 70% and 55% down the viewport. */
  height: number;
  /** Each node's centre, from the top of the list. */
  ys: number[];
  nodes: HTMLElement[];
  fills: HTMLElement[];
  tick: HTMLElement | null;
};

function measureThread(list: HTMLOListElement): Thread | null {
  const nodes = Array.from(list.querySelectorAll<HTMLElement>("[data-thread-node]"));
  const rows = nodes.map((n) => n.offsetParent as HTMLElement | null);
  if (!nodes.length || rows.some((r) => !r)) return null; // hidden below sm: nothing to paint
  return {
    height: list.offsetHeight,
    ys: nodes.map((n, i) => rows[i]!.offsetTop + n.offsetTop + n.offsetHeight / 2),
    nodes,
    fills: Array.from(list.querySelectorAll<HTMLElement>("[data-thread-fill]")),
    tick: list.querySelector<HTMLElement>("[data-thread-tick]"),
  };
}

function setOn(el: HTMLElement, on: boolean) {
  const v = on ? "true" : "false";
  if (el.dataset.on !== v) el.dataset.on = v;
}

function paintThread(t: Thread, progress: number) {
  const tip = progress * t.height;
  const { ys } = t;
  t.fills.forEach((el, i) => {
    const s = Math.min(1, Math.max(0, (tip - ys[i]) / (ys[i + 1] - ys[i])));
    const transform = `scaleY(${s.toFixed(4)})`;
    if (el.style.transform !== transform) el.style.transform = transform;
  });
  t.nodes.forEach((el, i) => setOn(el, tip >= ys[i] - 0.5));
  if (t.tick) setOn(t.tick, tip >= ys[ys.length - 1] - 0.5);
}

/** Back to the server markup: the thread fully drawn, every node and the threshold in ink. */
function resetThread(list: HTMLOListElement) {
  list.querySelectorAll<HTMLElement>("[data-thread-fill]").forEach((el) => el.style.removeProperty("transform"));
  list.querySelectorAll<HTMLElement>("[data-thread-node], [data-thread-tick]").forEach((el) => delete el.dataset.on);
}

/**
 * The hand-off thread (sm and up). Bound to scroll only if the list was below the fold at hydration: an ink fill then
 * grows down the track through a critically damped spring (no overshoot), its tip near the reading line, and each
 * node, then the threshold at row 05, takes the ink as the tip reaches it. Painted from the spring through the DOM
 * (no React state per frame); node positions come from offsetTop, re-measured whenever a row resizes. It is not a
 * pipeline run: ink only, no checks, no digits. SSR, no JS, reduced motion or already on screen: fully drawn.
 */
function useThread(listRef: RefObject<HTMLOListElement | null>) {
  const reduce = useReducedMotionSafe();
  const bound = useArm(listRef) !== "static" && !reduce;
  const { scrollYProgress } = useScroll({ target: listRef, offset: ["start 70%", "end 55%"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 28 });
  const thread = useRef<Thread | null>(null);

  useMotionValueEvent(progress, "change", (p) => {
    if (thread.current) paintThread(thread.current, p);
  });

  useEffect(() => {
    const list = listRef.current;
    if (!bound || !list) return;
    const measure = () => {
      thread.current = measureThread(list);
      if (thread.current) paintThread(thread.current, progress.get());
    };
    measure();
    const ro = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(measure);
    ro?.observe(list);
    for (const row of Array.from(list.children)) ro?.observe(row);
    return () => {
      ro?.disconnect();
      thread.current = null;
      resetThread(list);
    };
  }, [bound, listRef, progress]);
}
