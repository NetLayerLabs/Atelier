"use client";

import { useScroll, useSpring, useTransform } from "framer-motion";
import { useCallback, useEffect, useRef } from "react";
import {
  Button,
  C,
  Card,
  cx,
  EASE,
  Em,
  Eyebrow,
  IconArrowDown,
  IconChart,
  IconPlay,
  IconRuler,
  IconScissors,
  IconStore,
  Label,
  NEEDLE_SPRING,
  TapeMeasure,
} from "@/components/ds";
import { useDemo } from "@/lib/demo";
import { scrollToId } from "../ui";
import { DEV_TIME, PREORDER_PROOF } from "./data";
import { useReducedMotionSafe } from "./motion";
import { LandingSection, Reveal, REVEAL_RISE, REVEAL_TYPESET, SectionHead, Source, useArm } from "./primitives";

const VALUE = [
  {
    icon: IconStore,
    k: "Sell first, then make",
    body: "Every approved design goes live as a real pre-order. The purchase order is drafted only once orders clear the threshold, and every order sharpens an explained forecast of how many to make.",
  },
  {
    icon: IconChart,
    k: "Margin before a cut",
    body: "The tech pack arrives costed. Swap a material and unit cost, margin and break-even update on the spot; save it and open quotes are re-scored against your guardrails - the mills’ prices stay as quoted.",
  },
  {
    icon: IconScissors,
    k: "Mills compete",
    body: "Your suppliers get the same brief at once. Their quote documents are read field by field and scored on price, MOQ fit and lead time; the recommendation shows its reasoning, and you can overrule it.",
  },
  {
    icon: IconRuler,
    k: "Taste stays human",
    body: "You make the four calls that matter: the trend, the concept, the direction and the approval. The agents do the rest.",
  },
];

/*
 * Each card is a stage (Reveal variant "stage"): once it scrolls in, its parts play their beats, offset by
 * --reveal-delay. Hidden states apply only while armed, so the server HTML, no-JS and reduced motion show every
 * word in place. One easing throughout (ease-thread).
 */
/** A card arriving: it fades in and rises 16px. */
const ARRIVE =
  "transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-4 in-data-[reveal=armed]:opacity-0";
/** A beat that only fades in (an <Em> is inline: it is never transformed). */
const FADE = "transition-opacity duration-700 ease-thread in-data-[reveal=armed]:opacity-0";

/** The value cards rise on a diagonal across the 2 x 2 grid: 0, 90, 90, 180 ms (one by one on phones). */
const CARD_DELAY = ["", "sm:[--reveal-delay:90ms]", "sm:[--reveal-delay:90ms]", "sm:[--reveal-delay:180ms]"];

export function Value() {
  return (
    <LandingSection id="landing-value">
      <SectionHead
        id="landing-value-title"
        index="06"
        kicker="Business value"
        title={
          <>
            Less guessing, <Em>less dead stock.</Em>
          </>
        }
        lede="For brands that sell direct and want to test more ideas without carrying more inventory."
      />

      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        {VALUE.map((v, i) => {
          const Icon = v.icon;
          return (
            <Reveal key={v.k} variant="stage" className={CARD_DELAY[i]}>
              <Card pad="lg" className={cx("h-full", ARRIVE, "in-data-[reveal=shown]:delay-[var(--reveal-delay,0ms)]")}>
                <div className="flex items-start justify-between gap-4">
                  <h3
                    className={cx(
                      "text-display-m text-fg",
                      REVEAL_TYPESET,
                      "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+150ms)]",
                    )}
                  >
                    {v.k}
                  </h3>
                  <span
                    className={cx(
                      "grid size-10 shrink-0 place-items-center rounded-full bg-paper-2 text-fg",
                      FADE,
                      "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+450ms)]",
                    )}
                  >
                    <Icon size={18} />
                  </span>
                </div>
                <p className="mt-4 max-w-lg text-body text-pretty text-fg-muted">{v.body}</p>
              </Card>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-4 grid gap-3 sm:gap-4 lg:grid-cols-12">
        {/* The statement is set, then the tape unrolls from its case and uncovers both markers; the note lands last. */}
        <Reveal variant="stage" className="lg:col-span-8">
          <Card pad="lg" className={cx("h-full", ARRIVE)}>
            <Eyebrow>Where the time goes · design &amp; development</Eyebrow>
            <p className={cx("mt-4 max-w-2xl text-display-m text-fg", REVEAL_TYPESET, "in-data-[reveal=shown]:delay-[150ms]")}>
              11 to 24 weeks before a style is ready to make.{" "}
              <span className={cx(FADE, "in-data-[reveal=shown]:delay-[450ms]")}>
                <Em>
                  Atelier: <span className="whitespace-nowrap">1 min 54 s</span> from approval to RFQs sent.
                </Em>
              </span>
            </p>
            <div className="mt-8 transition-[clip-path] duration-1400 ease-thread in-data-[reveal=armed]:[clip-path:inset(0_100%_0_0)] in-data-[reveal=shown]:[clip-path:inset(-24px)] in-data-[reveal=shown]:delay-[250ms]">
              <TapeMeasure
                label="Design and development time in weeks"
                min={0}
                max={28}
                majorStep={4}
                value={null}
                format={(n) => `${n} wk`}
                tickFormat={(n) => String(n)}
                markers={[
                  { value: 11, label: "Vertical · 11 wks" },
                  { value: 24, label: "Hybrid · 24 wks" },
                ]}
              />
            </div>
            <div className="mt-6 flex flex-col gap-2 border-t border-line pt-5 sm:flex-row sm:items-start sm:justify-between sm:gap-8">
              <p className={cx("max-w-lg text-small text-pretty text-fg-muted", REVEAL_RISE, "in-data-[reveal=shown]:delay-[700ms]")}>
                No pointer on the tape, because the scopes differ: the tape is the industry&rsquo;s design-and-development
                time, sampling included. Atelier&rsquo;s <span className="whitespace-nowrap">1 min 54 s</span> was
                measured on one live run <span className="whitespace-nowrap">(17 Oct 2026)</span>: a costed tech pack
                written by the Evolus agent on Gemma 4 (AMD Token Factory), then RFQs sent through the Evolus workflow.
                Sampling, production and shipping still take as long as the mill needs.
              </p>
              <Source
                href={DEV_TIME.href}
                className={cx("shrink-0 sm:max-w-[14rem]", REVEAL_RISE, "in-data-[reveal=shown]:delay-[780ms]")}
              >
                {DEV_TIME.source}
              </Source>
            </div>
          </Card>
        </Reveal>

        {/* The figure rises from behind its baseline (a bound, never counted up), then its sentence, then the sources. */}
        <Reveal variant="stage" className="lg:col-span-4 lg:[--reveal-delay:90ms]">
          <Card pad="lg" className={cx("flex h-full flex-col", ARRIVE, "in-data-[reveal=shown]:delay-[var(--reveal-delay,0ms)]")}>
            <Eyebrow>Selling first already works</Eyebrow>
            <p className="mt-6 flex items-baseline gap-2 text-fg in-data-[reveal=armed]:[clip-path:inset(-0.5em_-0.5em_0_-0.5em)] in-data-[reveal=shown]:[clip-path:inset(-0.5em_-0.5em_0_-0.5em)]">
              <span className="text-[clamp(2.8rem,5vw,4rem)] leading-none font-light tracking-[-0.045em] tabular transition-[translate] duration-900 ease-thread in-data-[reveal=armed]:translate-y-full in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+150ms)]">
                &gt;90%
              </span>
            </p>
            <p
              className={cx(
                "mt-3 text-body text-pretty text-fg-muted",
                REVEAL_RISE,
                "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+450ms)]",
              )}
            >
              of Stòffa&rsquo;s revenue is paid before production. Prabal Gurung and Antonio Berardi take 20–25% of
              revenue as pre-order or made-to-order.
            </p>
            <div aria-hidden className="min-h-6 flex-1" />
            <div className="flex flex-col gap-1">
              {PREORDER_PROOF.map((s, i) => (
                <Source
                  key={s.href}
                  href={s.href}
                  className={cx(
                    REVEAL_RISE,
                    i === 0
                      ? "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+600ms)]"
                      : "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+680ms)]",
                  )}
                >
                  {s.source}
                </Source>
              ))}
            </div>
          </Card>
        </Reveal>
      </div>
    </LandingSection>
  );
}

/*
 * The closing gauge: the Atelier mark, completed by scroll. A number-free arc with 41 tape ticks; the logo's one
 * tick rides it from 0 to 12 o'clock as the sheet scrolls in, inking the arc behind it, and clicks into place on
 * arrival - for a beat the arc, its tick and the headline beneath are the mark. Scroll back and it falls away.
 * The server HTML (so no-JS), reduced motion and a sheet already on screen at load all show it settled on the mark.
 * Drawn in a 240 x 108 box: a 160° arc like the logo's, `t` running 0 (left end) → 0.5 (12 o'clock) → 1.
 */
const GW = 240;
const GH = 108;
const GX = 120;
const GY = 119;
const GR = 104;
const SWEEP = 160;
/** 12 o'clock: where the tick locks and the gauge reads as the mark. */
const MARK = 0.5;
/** It clicks when it reaches the mark and can click again only once it has fallen back below UNLOCK. */
const LOCK = MARK - 0.004;
const UNLOCK = MARK - 0.05;
const EASE_CSS = `cubic-bezier(${EASE.join(", ")})`;

function gaugeAt(r: number, t: number) {
  const a = ((t - MARK) * SWEEP * Math.PI) / 180;
  // Rounded so server and client render identical attribute strings.
  return [Math.round((GX + r * Math.sin(a)) * 100) / 100, Math.round((GY - r * Math.cos(a)) * 100) / 100] as const;
}

/** The ink trail: the arc from the left end up to the tick (at most 80°, so the small-arc flag always applies). */
function trailPath(t: number) {
  const [x0, y0] = gaugeAt(GR, 0);
  const [x, y] = gaugeAt(GR, Math.max(0.002, t));
  return `M ${x0} ${y0} A ${GR} ${GR} 0 0 1 ${x} ${y}`;
}

function tickTransform(t: number) {
  return `rotate(${Math.round((t - MARK) * SWEEP * 100) / 100} ${GX} ${GY})`;
}

const GAUGE_ARC = `M ${gaugeAt(GR, 0).join(" ")} A ${GR} ${GR} 0 0 1 ${gaugeAt(GR, 1).join(" ")}`;

// A tailor's tape bent along the arc: 40 divisions, a long tick every 10, a mid tick every 5.
const GAUGE_TICKS = Array.from({ length: 41 }, (_, i) => {
  const major = i % 10 === 0;
  const mid = i % 5 === 0;
  const [x1, y1] = gaugeAt(GR + 4, i / 40);
  const [x2, y2] = gaugeAt(GR + (major ? 12 : mid ? 9 : 7), i / 40);
  return { i, x1, y1, x2, y2, stroke: major ? C.tickMajor : mid ? C.tick : C.tickFaint };
});

function CtaGauge({ live, onLock }: { live: boolean; onLock: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const tickRef = useRef<SVGGElement>(null);
  const trailRef = useRef<SVGPathElement>(null);
  const ringRef = useRef<SVGCircleElement>(null);
  const reduce = useReducedMotionSafe();

  const { scrollYProgress } = useScroll({ target: box, offset: ["start end", "center 40%"] });
  const target = useTransform(scrollYProgress, [0, 1], [0, MARK]);
  const t = useSpring(target, {
    stiffness: NEEDLE_SPRING.stiffness,
    damping: NEEDLE_SPRING.damping,
    mass: NEEDLE_SPRING.mass,
    restDelta: 0.0005,
  });

  // Paint the tick and its trail straight from the spring (no React render per frame).
  useEffect(() => {
    const paint = (v: number) => {
      const p = Math.min(MARK, Math.max(0, v));
      tickRef.current?.setAttribute("transform", tickTransform(p));
      trailRef.current?.setAttribute("d", trailPath(p));
    };
    if (!live || reduce) {
      paint(MARK);
      return;
    }
    let locked = t.get() >= LOCK;
    const step = (v: number) => {
      paint(v);
      if (!locked && v >= LOCK) {
        locked = true;
        ringRef.current?.animate(
          [
            { opacity: 0.9, transform: "scale(0.3)" },
            { opacity: 0, transform: "scale(1.5)" },
          ],
          { duration: 600, easing: EASE_CSS },
        );
        onLock();
      } else if (locked && v < UNLOCK) {
        locked = false;
      }
    };
    step(t.get());
    return t.on("change", step);
  }, [live, reduce, t, onLock]);

  return (
    <div ref={box} aria-hidden className="mx-auto w-[11rem] sm:w-[13rem]">
      <svg viewBox={`0 0 ${GW} ${GH}`} fill="none" className="block h-auto w-full overflow-visible">
        <path d={GAUGE_ARC} stroke={C.tick} strokeWidth={1} />
        {GAUGE_TICKS.map((k) => (
          <line key={k.i} x1={k.x1} y1={k.y1} x2={k.x2} y2={k.y2} stroke={k.stroke} strokeWidth={1} />
        ))}
        <path ref={trailRef} d={trailPath(MARK)} stroke={C.fg} strokeWidth={1.75} />
        {/* the logo's tick: it crosses the arc, longer inside than out */}
        <g ref={tickRef} transform={tickTransform(MARK)}>
          <line x1={GX} y1={GY - GR + 15} x2={GX} y2={GY - GR - 12} stroke={C.fg} strokeWidth={2} />
        </g>
        {/* the click on arrival */}
        <circle
          ref={ringRef}
          cx={GX}
          cy={GY - GR}
          r={9}
          stroke={C.fg}
          strokeWidth={1.25}
          opacity={0}
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
        />
      </svg>
    </div>
  );
}

/*
 * Signature close: the black sheet opens like an aperture (its clip widens past its edges so the shadow is never
 * cut), the gauge completes the mark as you scroll, then the label, the headline, the lede and the buttons settle
 * in turn (the buttons themselves never move; their wrapper does). The first time the tick locks on the mark, the
 * arrow in "Launch studio" dips once - this way down.
 */
export function ClosingCta() {
  const startDemo = useDemo((s) => s.start);
  const demoOn = useDemo((s) => s.status !== "idle");
  const stage = useRef<HTMLDivElement>(null);
  const state = useArm(stage);
  const arrow = useRef<HTMLSpanElement>(null);
  const dipped = useRef(false);

  const onLock = useCallback(() => {
    if (dipped.current) return;
    dipped.current = true;
    arrow.current?.animate(
      [
        { transform: "translateY(0)", easing: EASE_CSS },
        { transform: "translateY(3px)", offset: 0.35, easing: EASE_CSS },
        { transform: "translateY(0)" },
      ],
      { duration: 700 },
    );
  }, []);

  return (
    <section aria-labelledby="landing-cta-title" className="relative py-16 text-center sm:py-24">
      <div ref={stage} data-reveal={state}>
        <div className="ds-inverse rounded-sheet px-6 pt-12 pb-20 shadow-e3 transition-[clip-path] duration-1200 ease-thread in-data-[reveal=armed]:[clip-path:inset(12%_8%_round_28px)] in-data-[reveal=shown]:[clip-path:inset(-64px_round_28px)] sm:px-10 sm:pt-16 sm:pb-28">
          <CtaGauge live={state !== "static"} onLock={onLock} />
          <Label as="p" className={cx("mt-6", FADE, "in-data-[reveal=shown]:delay-[300ms]")}>
            The studio is below · chapters I–IV
          </Label>
          <h2
            id="landing-cta-title"
            className={cx(
              "mx-auto mt-6 max-w-4xl text-display-l text-balance text-fg",
              REVEAL_TYPESET,
              // The title, then its <Em> 300ms later (LANDING_SEQ).
              "in-data-[reveal=shown]:delay-[400ms] in-data-[reveal=shown]:[&_em]:delay-[700ms]",
            )}
          >
            Take the chair. <Em accent>Pick a mood board.</Em>
          </h2>
          <p
            className={cx(
              "mx-auto mt-6 max-w-xl text-body-l text-pretty text-fg-muted",
              REVEAL_RISE,
              "in-data-[reveal=shown]:delay-[550ms]",
            )}
          >
            Everything from here on is the working product, running against the backend shown in the header.
          </p>
          <div
            className={cx(
              "mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row",
              REVEAL_RISE,
              "in-data-[reveal=shown]:delay-[650ms]",
            )}
          >
            <Button
              size="lg"
              onClick={() => scrollToId("chapter-trend")}
              trailing={
                <span ref={arrow} className="block">
                  <IconArrowDown size={16} />
                </span>
              }
              trailingBadge
              className="w-full justify-between sm:w-auto sm:min-w-60"
            >
              Launch studio
            </Button>
            <Button
              size="lg"
              variant="secondary"
              onClick={() => startDemo()}
              disabled={demoOn}
              icon={<IconPlay size={14} />}
              className="w-full sm:w-auto"
            >
              {demoOn ? "Tour running" : "Take the tour"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
