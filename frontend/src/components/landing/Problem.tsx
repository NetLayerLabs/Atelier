"use client";

import { Card, Em, IconLayers, IconChart, IconDocument } from "@/components/ds";
import { currencySymbol } from "../Sheet";
import { PROBLEM_FIGURES } from "./data";
import { LandingSection, Reveal, SectionHead, Source } from "./primitives";

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
            <Reveal as="li" key={p.title} delay={i * 90}>
              <Card className="h-full" pad="lg">
                <div className="flex items-center justify-between">
                  <span className="text-[1.6rem] leading-none font-light tracking-[-0.03em] text-fg-faint tabular">{p.n}</span>
                  <span className="grid size-10 place-items-center rounded-full bg-paper-2 text-fg">
                    <Icon size={18} />
                  </span>
                </div>
                <h3 className="mt-8 text-display-m text-fg">{p.title}</h3>
                <p className="mt-3 text-body text-pretty text-fg-muted">{p.body}</p>
              </Card>
            </Reveal>
          );
        })}
      </ol>

      <Reveal className="mt-16 sm:mt-20">
        <dl className="grid gap-10 md:grid-cols-3 md:gap-0 md:divide-x md:divide-line">
          {PROBLEM_FIGURES.map((f) => (
            <div key={f.value} className="flex min-w-0 flex-col md:px-8 md:first:pl-0 md:last:pr-0">
              <dd className="order-1 flex items-baseline gap-2 text-fg">
                <span className="text-[clamp(2.4rem,4.4vw,3.6rem)] leading-none font-light tracking-[-0.045em] tabular">
                  {f.value}
                </span>
                {f.unit && <span className="text-small text-fg-muted">{f.unit}</span>}
              </dd>
              <dt className="order-2 mt-3 max-w-xs text-body text-pretty text-fg-muted">
                {f.label.replace("{USD}", usd)}
              </dt>
              <dd className="order-3 mt-4">
                <Source href={f.href}>{f.source}</Source>
              </dd>
            </div>
          ))}
        </dl>
      </Reveal>
    </LandingSection>
  );
}
