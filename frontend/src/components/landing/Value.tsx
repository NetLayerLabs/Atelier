"use client";

import {
  Button,
  Card,
  Em,
  Eyebrow,
  IconArrowDown,
  IconChart,
  IconPlay,
  IconRuler,
  IconScissors,
  IconStore,
  Label,
  TapeMeasure,
} from "@/components/ds";
import { useDemo } from "@/lib/demo";
import { scrollToId } from "../ui";
import { DEV_TIME, PREORDER_PROOF } from "./data";
import { LandingSection, Reveal, SectionHead, Source } from "./primitives";

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
            <Reveal key={v.k} delay={(i % 2) * 90}>
              <Card pad="lg" className="h-full">
                <div className="flex items-start justify-between gap-4">
                  <h3 className="text-display-m text-fg">{v.k}</h3>
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-paper-2 text-fg">
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
        <Reveal className="lg:col-span-8">
          <Card pad="lg" className="h-full">
            <Eyebrow>Where the time goes · design &amp; development</Eyebrow>
            <p className="mt-4 max-w-2xl text-display-m text-fg">
              11 to 24 weeks before a style is ready to make. <Em>Atelier&rsquo;s own figure: to be measured.</Em>
            </p>
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
              className="mt-8"
            />
            <div className="mt-6 flex flex-col gap-2 border-t border-line pt-5 sm:flex-row sm:items-start sm:justify-between sm:gap-8">
              <p className="max-w-lg text-small text-pretty text-fg-muted">
                No pointer on the tape: Atelier&rsquo;s time from approval to tech pack and RFQs has not been measured on
                real runs yet, so no figure is claimed. Sampling, production and shipping still take as long as the mill
                needs.
              </p>
              <Source href={DEV_TIME.href} className="shrink-0 sm:max-w-[14rem]">
                {DEV_TIME.source}
              </Source>
            </div>
          </Card>
        </Reveal>

        <Reveal delay={90} className="lg:col-span-4">
          <Card pad="lg" className="flex h-full flex-col">
            <Eyebrow>Selling first already works</Eyebrow>
            <p className="mt-6 flex items-baseline gap-2 text-fg">
              <span className="text-[clamp(2.8rem,5vw,4rem)] leading-none font-light tracking-[-0.045em] tabular">&gt;90%</span>
            </p>
            <p className="mt-3 text-body text-pretty text-fg-muted">
              of Stòffa&rsquo;s revenue is paid before production. Prabal Gurung and Antonio Berardi take 20–25% of
              revenue as pre-order or made-to-order.
            </p>
            <div aria-hidden className="min-h-6 flex-1" />
            <div className="flex flex-col gap-1">
              {PREORDER_PROOF.map((s) => (
                <Source key={s.href} href={s.href}>
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

export function ClosingCta() {
  const startDemo = useDemo((s) => s.start);
  const demoOn = useDemo((s) => s.status !== "idle");
  return (
    <section aria-labelledby="landing-cta-title" className="relative py-16 text-center sm:py-24">
      <Reveal className="ds-inverse rounded-sheet px-6 py-20 shadow-e3 sm:px-10 sm:py-28">
        <Label as="p">The studio is below · chapters I–IV</Label>
        <h2 id="landing-cta-title" className="mx-auto mt-6 max-w-4xl text-display-l text-balance text-fg">
          Take the chair. <Em accent>Pick a mood board.</Em>
        </h2>
        <p className="mx-auto mt-6 max-w-xl text-body-l text-pretty text-fg-muted">
          Everything from here on is the working product, running against the backend shown in the header.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button
            size="lg"
            onClick={() => scrollToId("chapter-trend")}
            trailing={<IconArrowDown size={16} />}
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
      </Reveal>
    </section>
  );
}
