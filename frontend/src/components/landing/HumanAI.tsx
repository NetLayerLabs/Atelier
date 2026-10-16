"use client";

import type { ReactNode } from "react";
import { Button, Card, Chip, Em, Eyebrow, IconArrowDown, IconMessage, Label, Stitch, Swatch } from "@/components/ds";
import { useAtelier } from "@/lib/store";
import { RouteTag } from "../Inference";
import { scrollToId } from "../ui";
import { LandingSection, Reveal, SectionHead } from "./primitives";

/** The calls only the creative director makes. */
const YOU_DECIDE = ["Which trend to chase", "Which concept to develop", "How it should change", "Whether it goes to production"];

/** What a read-back contains - described, not invented. */
const READ_BACK = [
  { title: "Prompt", body: "What is added to and removed from the image prompt for the next renders." },
  { title: "Palette", body: "The colourway before and after, when the direction re-colours the garment." },
  { title: "Silhouette & fabric", body: "Changes to proportion and construction, and any fabric swaps (shell first)." },
  { title: "Into the tech pack", body: "Concrete hints carried into the tech pack the agent writes after approval." },
];

export function HumanAI() {
  // Only real output: the latest direction given in this session (none until you direct a concept in chapter III).
  const latest = useAtelier((s) => {
    const all = Object.values(s.directions);
    return all.length ? all.reduce((a, b) => (a.createdAt >= b.createdAt ? a : b)) : undefined;
  });

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
        <Reveal className="lg:col-span-5">
          <Label as="p">You decide</Label>
          <ol className="mt-4 flex flex-col gap-2">
            {YOU_DECIDE.map((d, i) => (
              <li key={d} className="flex items-baseline gap-4 text-[clamp(1.3rem,2vw,1.7rem)] leading-snug font-light tracking-[-0.025em] text-fg">
                <span className="w-7 shrink-0 text-[0.8em] text-fg-faint tabular">{["I", "II", "III", "IV"][i]}</span>
                {d}
              </li>
            ))}
          </ol>

          <Stitch label="Agent → you" className="my-9" />

          <Label as="p">Atelier reads back</Label>
          <dl className="mt-4 grid gap-x-6 gap-y-5 sm:grid-cols-2">
            {READ_BACK.map((r) => (
              <div key={r.title}>
                <dt className="text-small font-medium text-fg">{r.title}</dt>
                <dd className="mt-1 text-small text-pretty text-fg-muted">{r.body}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-8 text-micro text-pretty text-fg-faint">
            The brain (an Evolus agent or AMD vLLM) interprets the instruction; the diffusion model renders four
            directed variations. If either is not connected, chapter III says so instead of showing a result.
          </p>
        </Reveal>

        <Reveal delay={100} className="lg:col-span-7">
          <Card pad="lg" className="flex h-full flex-col">
            {latest ? (
              <>
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
              </>
            ) : (
              <div className="flex h-full flex-col justify-between gap-10">
                <div>
                  <Eyebrow tone="faint">Atelier heard</Eyebrow>
                  <div className="mt-8 flex items-start gap-4">
                    <span className="grid size-12 shrink-0 place-items-center rounded-full bg-paper-2 text-fg-muted">
                      <IconMessage size={20} />
                    </span>
                    <p className="text-display-m text-fg">Your read-back appears here once you direct a concept.</p>
                  </div>
                  <p className="mt-6 max-w-lg text-body text-pretty text-fg-muted">
                    Pick a concept in chapter III and say what you want - &ldquo;darker&rdquo;,
                    &ldquo;cropped&rdquo;, &ldquo;more utilitarian&rdquo; - typed or spoken. What shows here is the
                    model&rsquo;s real answer; nothing is pre-recorded.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-1.5" aria-hidden>
                    {["darker", "cropped", "more utilitarian"].map((w) => (
                      <Chip key={w} variant="soft">
                        &ldquo;{w}&rdquo;
                      </Chip>
                    ))}
                  </div>
                </div>
                <Button
                  variant="secondary"
                  onClick={() => scrollToId("chapter-trend")}
                  trailing={<IconArrowDown size={15} />}
                  className="self-start"
                >
                  Start in the studio
                </Button>
              </div>
            )}
          </Card>
        </Reveal>
      </div>
    </LandingSection>
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
