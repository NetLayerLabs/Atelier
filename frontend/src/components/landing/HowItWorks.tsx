"use client";

import { Card, Em, IconEye, IconHanger, IconNeedle, IconSpool, IconTag, Label, Stitch } from "@/components/ds";
import { CHAPTERS } from "./data";
import { LandingSection, Reveal, SectionHead } from "./primitives";

const ICONS = [IconEye, IconHanger, IconNeedle, IconSpool];

export function HowItWorks() {
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

      <ol className="relative grid gap-3 sm:grid-cols-2 sm:gap-4 xl:grid-cols-4">
        {/* the seam that joins the chapters on wide screens */}
        <span aria-hidden className="ds-stitch absolute top-[3.1rem] right-[12%] left-[12%] hidden xl:block" />
        {CHAPTERS.map((c, i) => {
          const Icon = ICONS[i];
          return (
            <Reveal as="li" key={c.numeral} delay={i * 80} className="relative">
              <Card className="flex h-full flex-col" pad="md">
                <div className="flex items-center justify-between">
                  <span className="grid size-11 place-items-center rounded-full bg-inverse text-small font-medium text-on-inverse">
                    {c.numeral}
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
                <Stitch label="Atelier" className="my-5" />
                <p className="text-small text-pretty text-fg-muted">{c.agent}</p>

                <div aria-hidden className="min-h-6 flex-1" />
                <p className="flex items-start gap-2 border-t border-line pt-4 text-small text-fg">
                  <IconTag size={15} className="mt-0.5 shrink-0 text-fg-faint" />
                  <span>
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
