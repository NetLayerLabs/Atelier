"use client";

import { useRef } from "react";
import { Card, cx, Em, IconEye, IconHanger, IconNeedle, IconSpool, IconTag, Label, Stitch } from "@/components/ds";
import { CHAPTERS } from "./data";
import { LandingSection, Reveal, SectionHead, useArm } from "./primitives";

const ICONS = [IconEye, IconHanger, IconNeedle, IconSpool];

/*
 * Each card is a stage: it arrives, its numeral disc fills with ink from the centre (+150 ms), then the hand-off
 * plays in reading order - the "Atelier" seam sews itself (+250), the agent's part follows (+500) and what it leaves
 * behind is tagged (+650), all within 1.4 s. The beats are offset from --reveal-delay, which staggers the cards of
 * one row I to IV by 120 ms (STAGGER.figure): four across on xl, pairs from sm, one by one as you scroll on phones.
 * Hidden states apply only while a card is armed (useArm), so the server HTML, no-JS and reduced motion show it whole.
 */
const CARD_DELAY = [
  "",
  "sm:[--reveal-delay:120ms]",
  "xl:[--reveal-delay:240ms]",
  "sm:[--reveal-delay:120ms] xl:[--reveal-delay:360ms]",
];

export function HowItWorks() {
  const row = useRef<HTMLOListElement>(null);
  const seam = useArm(row);

  return (
    <LandingSection id="landing-how">
      <SectionHead
        id="landing-how-title"
        index="02"
        kicker="How it works"
        title={
          <>
            Four chapters. <Em>One creative director.</Em>
          </>
        }
        lede="The studio below runs as four chapters on one page. In each, you make a call and the agent does the work around it, leaving something concrete behind."
      />

      <ol ref={row} className="relative grid gap-3 sm:grid-cols-2 sm:gap-4 xl:grid-cols-4">
        {/* the seam that joins the chapters on wide screens, level with the numerals (card border + padding +
            half a disc). It sews across from I to IV as the row arrives, starting once the first cards have
            landed (240 ms) so it never shows through a card that is still fading in. */}
        <span
          aria-hidden
          className={cx(
            "ds-stitch absolute top-[calc(2.875rem+0.5px)] right-[12%] left-[12%] hidden xl:block",
            seam === "armed" && "[clip-path:inset(0_100%_0_0)]",
            seam === "shown" && "[clip-path:inset(0)] transition-[clip-path] delay-240 duration-1400 ease-thread",
          )}
        />
        {CHAPTERS.map((c, i) => {
          const Icon = ICONS[i];
          return (
            <Reveal as="li" key={c.numeral} variant="stage" className={cx("relative", CARD_DELAY[i])}>
              <Card
                pad="md"
                className="flex h-full flex-col transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-4 in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[var(--reveal-delay,0ms)]"
              >
                <div className="flex items-center justify-between">
                  {/* armed, the numeral is an empty ring; ink fills it from the centre (the fill ends just past the
                      disc's edge, so at rest the edge is the disc's own, as before) */}
                  <span className="relative size-11">
                    <span aria-hidden className="absolute inset-0 rounded-full border border-line-bold" />
                    <span className="absolute inset-0 grid place-items-center rounded-full bg-inverse text-small font-medium text-on-inverse transition-[clip-path] duration-600 ease-thread in-data-[reveal=armed]:[clip-path:circle(0%_at_50%_50%)] in-data-[reveal=shown]:[clip-path:circle(calc(50%+2px)_at_50%_50%)] in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+150ms)]">
                      {c.numeral}
                    </span>
                  </span>
                  <span className="grid size-10 place-items-center rounded-full bg-paper-2 text-fg-muted">
                    <Icon size={18} />
                  </span>
                </div>
                <h3 className="mt-6 text-title text-fg">{c.title}</h3>
                <Label as="p" className="mt-1">
                  {c.kicker}
                </Label>

                <div className="mt-5">
                  <Label as="p">You</Label>
                  <p className="mt-1.5 text-body text-pretty text-fg">{c.human}</p>
                </div>
                {/* the hand-off: the seam sews itself left to right; its name surfaces as the thread reaches it
                    instead of being wiped letter by letter */}
                <div className="my-5 transition-[clip-path] duration-900 ease-thread in-data-[reveal=armed]:[clip-path:inset(0_100%_0_0)] in-data-[reveal=shown]:[clip-path:inset(0)] in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+250ms)]">
                  <Stitch
                    label={
                      <span className="transition-opacity duration-600 ease-thread in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+300ms)]">
                        Atelier
                      </span>
                    }
                  />
                </div>
                <p className="text-small text-pretty text-fg-muted transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-2 in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+500ms)]">
                  {c.agent}
                </p>

                <div aria-hidden className="min-h-6 flex-1" />
                {/* what it leaves behind: the hairline draws left to right as the tag swings onto its eyelet (the
                    padding keeps the 1px the old top border took, so the finished card is unchanged) */}
                <p className="relative flex items-start gap-2 pt-[calc(1rem+1px)] text-small text-fg">
                  <span
                    aria-hidden
                    className="absolute inset-x-0 top-0 h-px origin-left bg-line transition-[scale] duration-700 ease-thread in-data-[reveal=armed]:scale-x-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+650ms)]"
                  />
                  <IconTag
                    size={15}
                    className="mt-0.5 shrink-0 origin-[33%_33%] text-fg-faint transition-[opacity,rotate] duration-700 ease-thread in-data-[reveal=armed]:-rotate-18 in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+650ms)]"
                  />
                  <span className="transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-2 in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[calc(var(--reveal-delay,0ms)+650ms)]">
                    <span className="sr-only">Leaves behind: </span>
                    {c.artifact}
                  </span>
                </p>
              </Card>
            </Reveal>
          );
        })}
      </ol>
    </LandingSection>
  );
}
