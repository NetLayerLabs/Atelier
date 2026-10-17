"use client";

import { Card, cx, Em, IconLayers, IconChart, IconDocument } from "@/components/ds";
import { currencySymbol } from "../Sheet";
import { PROBLEM_FIGURES } from "./data";
import { LandingSection, Reveal, REVEAL_RISE, REVEAL_TYPESET, SectionHead, Source } from "./primitives";

const PROBLEMS = [
  {
    n: "i",
    icon: IconLayers,
    title: "The lag",
    body: "A trend is spotted on a runway or a feed. The garment reaches the shelf after sketches, tech packs, mill emails and sample rounds - by then the moment may have moved on.",
  },
  {
    n: "ii",
    icon: IconChart,
    title: "The guess",
    body: "Buy quantities are committed before a single customer has said yes. Too few and the line sells out; too many and it ends in markdowns, or worse.",
  },
  {
    n: "iii",
    icon: IconDocument,
    title: "The paperwork",
    body: "Taste is the scarce part, yet most hours go to specs, costings, RFQs and supplier comparisons: structured, repetitive work that is easy to get wrong.",
  },
];

/*
 * Each card and each cited figure is a stage (Reveal variant="stage"): the block arrives, then its parts set in
 * reading order, offset from --reveal-delay. From md the three sit in one row and play left to right (cards 90 ms
 * apart, figures STAGGER.figure = 120 ms); stacked on phones, each plays as it scrolls in, without waiting. Hidden
 * states apply only while a block is armed (useArm), so the server HTML, no-JS and reduced motion show it whole.
 */
const CARD_DELAY = ["", "md:[--reveal-delay:90ms]", "md:[--reveal-delay:180ms]"];
const FIGURE_DELAY = ["", "md:[--reveal-delay:120ms]", "md:[--reveal-delay:240ms]"];

/**
 * The hairline between two figures from md (where divide-x drew it, same pixel), as a pseudo-element so the <dl>
 * keeps only dt/dd: it drops from the top while its figure sets.
 */
const FIGURE_RULE =
  "md:before:absolute md:before:inset-y-0 md:before:-left-px md:before:w-px md:before:origin-top md:before:bg-line md:before:transition-[scale] md:before:duration-1000 md:before:ease-thread md:data-[reveal=armed]:before:scale-y-0 md:data-[reveal=shown]:before:delay-[var(--reveal-delay,0ms)]";

export function Problem() {
  const usd = currencySymbol("USD");
  return (
    <LandingSection id="landing-problem">
      <SectionHead
        id="landing-problem-title"
        index="01"
        kicker="The problem"
        title={
          <>
            Fashion bets months ahead, <Em>then lives with the leftovers.</Em>
          </>
        }
        lede="The industry commits to production on a forecast, long before demand is known. Atelier inverts the order: design fast, sell first, make what has sold."
      />

      <ol className="grid gap-3 md:grid-cols-3 md:gap-4">
        {PROBLEMS.map((p, i) => {
          const Icon = p.icon;
          return (
            <Reveal as="li" key={p.title} variant="stage" className={CARD_DELAY[i]}>
              {/* the card arrives; its numeral, title and body set 60 ms apart, and the icon well comes last */}
              <Card
                className="h-full transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-4 in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[var(--reveal-delay,0ms)]"
                pad="lg"
              >
                <div className="flex items-center justify-between">
                  <span
                    className={cx(
                      "text-[1.6rem] leading-none font-light tracking-[-0.03em] text-fg-faint tabular",
                      REVEAL_RISE,
                      "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+100ms)]",
                    )}
                  >
                    {p.n}
                  </span>
                  <span className="grid size-10 place-items-center rounded-full bg-paper-2 text-fg transition-opacity duration-600 ease-thread in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+340ms)]">
                    <Icon size={18} />
                  </span>
                </div>
                <h3
                  className={cx(
                    "mt-8 text-display-m text-fg",
                    REVEAL_TYPESET,
                    "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+160ms)]",
                  )}
                >
                  {p.title}
                </h3>
                <p
                  className={cx(
                    "mt-3 text-body text-pretty text-fg-muted",
                    REVEAL_RISE,
                    "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+220ms)]",
                  )}
                >
                  {p.body}
                </p>
              </Card>
            </Reveal>
          );
        })}
      </ol>

      <dl className="mt-16 grid gap-10 sm:mt-20 md:grid-cols-3 md:gap-0">
        {PROBLEM_FIGURES.map((f, i) => (
          <Reveal
            key={f.value}
            variant="stage"
            className={cx(
              "relative flex min-w-0 flex-col md:px-8 md:first:pl-0 md:last:pr-0",
              FIGURE_DELAY[i],
              i > 0 && FIGURE_RULE,
            )}
          >
            {/* the figure rises from behind its own baseline: the mask's edge sits .1em under the line, past any
                descender, and the negative margin gives that room back so the layout is unchanged. No count-up. */}
            <dd className="order-1 -mb-[.1em] pb-[.1em] text-[clamp(2.4rem,4.4vw,3.6rem)] leading-none text-fg in-data-[reveal=armed]:[clip-path:inset(-1em_-1em_0_-1em)] in-data-[reveal=shown]:[clip-path:inset(-1em_-1em_0_-1em)]">
              <span className="flex items-baseline gap-2 transition-[translate] duration-800 ease-thread in-data-[reveal=armed]:translate-y-[110%] in-data-[reveal=shown]:delay-[var(--reveal-delay,0ms)]">
                <span className="font-light tracking-[-0.045em] tabular">{f.value}</span>
                {f.unit && <span className="text-small text-fg-muted">{f.unit}</span>}
              </span>
            </dd>
            {/* the claim follows its figure, and the citation lands with it */}
            <dt
              className={cx(
                "order-2 mt-3 max-w-xs text-body text-pretty text-fg-muted",
                REVEAL_RISE,
                "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+150ms)]",
              )}
            >
              {f.label.replace("{USD}", usd)}
            </dt>
            <dd
              className={cx("order-3 mt-4", REVEAL_RISE, "in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+250ms)]")}
            >
              <Source href={f.href}>{f.source}</Source>
            </dd>
          </Reveal>
        ))}
      </dl>
    </LandingSection>
  );
}
