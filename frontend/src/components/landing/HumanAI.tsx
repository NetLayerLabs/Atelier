"use client";

import { AnimatePresence, motion, useIsPresent } from "framer-motion";
import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Button,
  Card,
  Chip,
  cx,
  DUR,
  EASE,
  Em,
  Eyebrow,
  IconArrowDown,
  IconMessage,
  INSTANT,
  Label,
  Stitch,
  Swatch,
} from "@/components/ds";
import { useAtelier } from "@/lib/store";
import { RouteTag } from "../Inference";
import { scrollToId } from "../ui";
import { useReducedMotionSafe } from "./motion";
import {
  LandingSection,
  REVEAL_RISE,
  REVEAL_TYPESET,
  SectionHead,
  STAGGER,
  useArm,
  type ArmState,
} from "./primitives";

/** The calls only the creative director makes. */
const YOU_DECIDE = ["Which trend to chase", "Which concept to develop", "How it should change", "Whether it goes to production"];
const NUMERALS = ["I", "II", "III", "IV"];

/** What a read-back contains - described, not invented. */
const READ_BACK = [
  { title: "Prompt", body: "What is added to and removed from the image prompt for the next renders." },
  { title: "Palette", body: "The colourway before and after, when the direction re-colours the garment." },
  { title: "Silhouette & fabric", body: "Changes to proportion and construction, and any fabric swaps (shell first)." },
  { title: "Into the tech pack", body: "Concrete hints carried into the tech pack the agent writes after approval." },
];

/** Things you might say. Examples only: they appear once, never cycle and are never "typed". */
const EXAMPLES = ["darker", "cropped", "more utilitarian"];

/*
 * Choreography, in ms after a stage scrolls into view. The column is two stages (the calls, then the read-back) so
 * each part plays as you reach it; when both come into view together they read as one sequence of about 1.75 s:
 * the calls are set from behind their baselines (I to IV, each numeral a beat before its words), the seam sews at
 * +0.6 s, the read-back follows in a 2x2 cadence and the footnote last. The card follows the column the same way.
 */
const CALLS = { first: 60, step: 110, words: 60 } as const;
/** The read-back's lead when it comes into view together with the calls. */
const SEAM = 600;
/** After the seam: its label, the four items (plus CADENCE), the footnote. */
const READ = { label: 80, items: 160, note: 440 } as const;
/** 2x2: the first item, then the diagonal together, then the last. */
const CADENCE = [0, STAGGER.sibling, STAGGER.sibling, 2 * STAGGER.sibling];
/** The card's lead when it comes into view together with the column (side by side on wide screens). */
const CARD = 350;
/** After the card arrives: its line is typeset, the explainer fades in, the chips pop in, the button last. */
const HEARD = { line: 100, explainer: 300, chips: 420, chip: 70, button: 600 } as const;

// Hidden states apply only while a stage is armed (below the fold after hydration), so the server HTML, no-JS and
// reduced motion all show the final layout. An element plays at its stage's lead (--reveal-delay) plus its --beat.
const BEAT = "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+var(--beat,0ms))]";
/**
 * The mask a line is set into (only while armed or playing). Its negative insets leave room for descenders and side
 * bearings, so at rest it shaves nothing.
 */
const MASK =
  "in-data-[reveal=armed]:[clip-path:inset(-0.25em_-0.5em_-0.06em_-0.5em)] in-data-[reveal=shown]:[clip-path:inset(-0.25em_-0.5em_-0.06em_-0.5em)]";
const SET = "transition-[translate] duration-800 ease-thread in-data-[reveal=armed]:translate-y-[115%]";
/** The seam sews left to right. */
const SEW =
  "transition-[clip-path] duration-1000 ease-thread in-data-[reveal=armed]:[clip-path:inset(-0.5em_100%_-0.5em_0)] in-data-[reveal=shown]:[clip-path:inset(-0.5em_0_-0.5em_0)]";
const FADE = "transition-opacity duration-700 ease-thread in-data-[reveal=armed]:opacity-0";
const POP = "transition-[opacity,scale] duration-500 ease-thread in-data-[reveal=armed]:scale-[0.92] in-data-[reveal=armed]:opacity-0";
/** The card itself arrives like any landing card (a Reveal "rise"). */
const ARRIVE = "transition-[opacity,translate] duration-900 ease-thread in-data-[reveal=armed]:translate-y-[18px] in-data-[reveal=armed]:opacity-0";

const beat = (ms: number) => ({ "--beat": `${ms}ms` }) as CSSProperties;
const lead = (ms: number) => (ms ? ({ "--reveal-delay": `${ms}ms` } as CSSProperties) : undefined);

export function HumanAI() {
  // Only real output: the latest direction given in this session (none until you direct a concept in chapter III).
  const latest = useAtelier((s) => {
    const all = Object.values(s.directions);
    return all.length ? all.reduce((a, b) => (a.createdAt >= b.createdAt ? a : b)) : undefined;
  });

  const callsRef = useRef<HTMLDivElement>(null);
  const readRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const calls = useArm(callsRef);
  const read = useArm(readRef);
  const card = useArm(cardRef);
  const readLead = useLead(calls, read, SEAM);
  const cardLead = useLead(calls, card, CARD);

  return (
    <LandingSection id="landing-direction">
      <SectionHead
        id="landing-direction-title"
        index="04"
        kicker="Human + AI"
        title={
          <>
            Direct it the way <Em>you&rsquo;d brief a studio.</Em>
          </>
        }
        lede="No sliders, no prompt engineering. You say what you want; Atelier turns it into concrete changes, reads them back, and carries them all the way into the tech pack."
      />

      <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-5">
          <div ref={callsRef} data-reveal={calls}>
            <Label as="p" className={REVEAL_RISE}>
              You decide
            </Label>
            <ol className="mt-4 flex flex-col gap-2">
              {YOU_DECIDE.map((d, i) => {
                const t = CALLS.first + i * CALLS.step;
                return (
                  <li key={d} className="flex items-baseline gap-4 text-[clamp(1.3rem,2vw,1.7rem)] leading-snug font-light tracking-[-0.025em] text-fg">
                    <SetLine beat={t} className="w-7 shrink-0 text-[0.8em] text-fg-faint tabular">
                      {NUMERALS[i]}
                    </SetLine>
                    <SetLine beat={t + CALLS.words} className="min-w-0">
                      {d}
                    </SetLine>
                  </li>
                );
              })}
            </ol>
          </div>

          <div ref={readRef} data-reveal={read} style={lead(readLead)}>
            <div className={cx("my-9", SEW, BEAT)}>
              <Stitch label="Agent → you" />
            </div>

            <div style={beat(READ.label)} className={cx(REVEAL_RISE, BEAT)}>
              <Label as="p">Atelier reads back</Label>
            </div>
            <dl className="mt-4 grid gap-x-6 gap-y-5 sm:grid-cols-2">
              {READ_BACK.map((r, i) => (
                <div key={r.title} style={beat(READ.items + CADENCE[i])} className={cx(REVEAL_RISE, BEAT)}>
                  <dt className="text-small font-medium text-fg">{r.title}</dt>
                  <dd className="mt-1 text-small text-pretty text-fg-muted">{r.body}</dd>
                </div>
              ))}
            </dl>
            <p style={beat(READ.note)} className={cx("mt-8 text-micro text-pretty text-fg-faint", REVEAL_RISE, BEAT)}>
              The brain (an Evolus agent on the AMD model) interprets the instruction and carries it into the tech
              pack. With a diffusion server connected it also renders four directed variations; without one, your own
              sketch stays the design. If the brain is not connected, chapter III says so instead of showing a result.
            </p>
          </div>
        </div>

        <div ref={cardRef} data-reveal={card} style={lead(cardLead)} className="lg:col-span-7">
          <Card pad="lg" className={cx("flex h-full flex-col", ARRIVE, BEAT)}>
            {/* Both faces share one grid cell, so a real read-back crossfades over the empty state in place. */}
            <div className="grid flex-1 grid-cols-[minmax(0,1fr)]">
              <AnimatePresence initial={false}>
                {latest ? (
                  <Face key={latest.id}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <Eyebrow>Atelier heard · your latest direction</Eyebrow>
                      <RouteTag route={latest.generatedBy} />
                    </div>
                    <p className="mt-5 text-[clamp(1.4rem,2.4vw,1.9rem)] leading-snug font-light tracking-[-0.02em] text-fg">
                      &ldquo;{latest.instruction}&rdquo;
                    </p>
                    <p className="mt-3 text-body text-pretty text-fg-muted">{latest.interpretation}</p>
                    <div className="mt-7 grid gap-7 border-t border-line pt-7 md:grid-cols-2">
                      {latest.paletteShift && (
                        <Group title={`Palette · ${latest.paletteShift.note}`}>
                          <div className="flex flex-col gap-2.5">
                            <SwatchRow label="Before" colors={latest.paletteShift.before} />
                            <SwatchRow label="After" colors={latest.paletteShift.after} />
                          </div>
                        </Group>
                      )}
                      {latest.silhouetteChanges.length > 0 && (
                        <Group title="Silhouette">
                          <div className="flex flex-wrap gap-1.5">
                            {latest.silhouetteChanges.map((s) => (
                              <Chip key={s}>{s}</Chip>
                            ))}
                          </div>
                        </Group>
                      )}
                      {(latest.promptAdditions.length > 0 || latest.promptRemovals.length > 0) && (
                        <Group title="Prompt">
                          <div className="flex flex-wrap gap-1.5">
                            {latest.promptAdditions.map((p) => (
                              <Chip key={`+${p}`} variant="ink">
                                + {p}
                              </Chip>
                            ))}
                            {latest.promptRemovals.map((p) => (
                              <Chip key={`-${p}`} variant="soft" className="text-fg-faint line-through">
                                {p}
                              </Chip>
                            ))}
                          </div>
                        </Group>
                      )}
                      {latest.techPackHints.length > 0 && (
                        <Group title="Into the tech pack">
                          <ul className="flex flex-col gap-2 text-small text-fg">
                            {latest.techPackHints.map((h) => (
                              <li key={h} className="flex gap-3">
                                <span aria-hidden className="mt-[0.7em] h-px w-3 shrink-0 bg-fg" />
                                {h}
                              </li>
                            ))}
                          </ul>
                        </Group>
                      )}
                    </div>
                  </Face>
                ) : (
                  <Face key="empty" className="flex flex-col justify-between gap-10">
                    <div>
                      <Eyebrow tone="faint">Atelier heard</Eyebrow>
                      <div className="mt-8 flex items-start gap-4">
                        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-paper-2 text-fg-muted">
                          <IconMessage size={20} />
                        </span>
                        <p style={beat(HEARD.line)} className={cx("text-display-m text-fg", REVEAL_TYPESET, BEAT)}>
                          Your read-back appears here once you direct a concept.
                        </p>
                      </div>
                      <p
                        style={beat(HEARD.explainer)}
                        className={cx("mt-6 max-w-lg text-body text-pretty text-fg-muted", FADE, BEAT)}
                      >
                        Pick a concept in chapter III and say what you want - &ldquo;darker&rdquo;,
                        &ldquo;cropped&rdquo;, &ldquo;more utilitarian&rdquo; - typed or spoken. What shows here is the
                        model&rsquo;s real answer; nothing is pre-recorded.
                      </p>
                      <div className="mt-6 flex flex-wrap gap-1.5" aria-hidden>
                        {EXAMPLES.map((w, i) => (
                          <span key={w} style={beat(HEARD.chips + i * HEARD.chip)} className={cx("inline-flex", POP, BEAT)}>
                            <Chip variant="soft">&ldquo;{w}&rdquo;</Chip>
                          </span>
                        ))}
                      </div>
                    </div>
                    <div style={beat(HEARD.button)} className={cx("self-start", REVEAL_RISE, BEAT)}>
                      <Button
                        variant="secondary"
                        onClick={() => scrollToId("chapter-trend")}
                        trailing={<IconArrowDown size={15} />}
                      >
                        Start in the studio
                      </Button>
                    </div>
                  </Face>
                )}
              </AnimatePresence>
            </div>
          </Card>
        </div>
      </div>
    </LandingSection>
  );
}

/**
 * How long a stage holds back once it plays: `wait` ms when it comes into view in the same moment as `before` (the
 * two then read as one sequence), nothing when it arrives later on its own (it plays as you reach it).
 */
function useLead(before: ArmState, self: ArmState, wait: number): number {
  const [seen, setSeen] = useState({ before, self, lead: 0 });
  if (seen.before === before && seen.self === self) return seen.lead;
  // Adjusted while rendering (React's "information from previous renders" pattern): the lead must land in the same
  // commit as the stage turning "shown", or its CSS transitions would already have started without it.
  const flipped = self === "shown" && seen.self !== "shown";
  const together = before === "shown" && seen.before !== "shown";
  const next = flipped ? (together ? wait : 0) : seen.lead;
  setSeen({ before, self, lead: next });
  return next;
}

/**
 * One line set from behind its baseline. The mask exists only while its stage is armed or playing, so the server
 * HTML, no-JS and reduced motion never clip a glyph.
 */
function SetLine({ children, beat: ms, className }: { children: ReactNode; beat: number; className?: string }) {
  return (
    <span className={cx("block", MASK, className)}>
      <span style={beat(ms)} className={cx("block", SET, BEAT)}>
        {children}
      </span>
    </span>
  );
}

/**
 * One face of the "Atelier heard" card. A new face only ever comes from a real direction in the store: the old face
 * clears first and the new one fades in a beat later, so two headlines never sit on top of each other (opacity only;
 * instant under reduced motion). The face on its way out is inert and hidden from assistive tech.
 */
function Face({ children, className }: { children: ReactNode; className?: string }) {
  const present = useIsPresent();
  const reduce = useReducedMotionSafe();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: reduce ? INSTANT : { duration: DUR.sheet, ease: EASE, delay: DUR.micro } }}
      exit={{ opacity: 0, transition: reduce ? INSTANT : { duration: DUR.ui, ease: EASE } }}
      inert={!present}
      aria-hidden={present ? undefined : true}
      className={cx("col-start-1 row-start-1 min-w-0", className)}
    >
      {children}
    </motion.div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <Label as="p" className="mb-3">
        {title}
      </Label>
      {children}
    </div>
  );
}

function SwatchRow({ label, colors }: { label: string; colors: string[] }) {
  return (
    <div className="flex items-center gap-3">
      <Label className="w-12">{label}</Label>
      <span className="flex gap-1.5">
        {colors.map((c, i) => (
          <Swatch key={`${c}-${i}`} color={c} size="sm" />
        ))}
      </span>
    </div>
  );
}
