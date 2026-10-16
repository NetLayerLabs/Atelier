"use client";

import { Card, Em, Label } from "@/components/ds";
import { SERVICE_SHORT } from "@/lib/health";
import { AGENTS } from "./data";
import { LandingSection, Reveal, SectionHead, ServiceMode } from "./primitives";

export function Agents() {
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
        <ol className="divide-y divide-line">
          {AGENTS.map((a, i) => (
            <Reveal
              as="li"
              key={a.n}
              delay={i * 60}
              className="grid gap-4 px-5 py-6 sm:px-8 sm:py-7 lg:grid-cols-12 lg:gap-8"
            >
              <div className="lg:col-span-3">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-small text-fg-faint tabular">{a.n}</span>
                  <h3 className="text-title text-fg">{a.name}</h3>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 lg:pl-8">
                  {a.services.map((s) => (
                    <ServiceMode key={s} name={s} label={SERVICE_SHORT[s] ?? s} />
                  ))}
                </div>
              </div>
              <div className="lg:col-span-4">
                <Label as="p" className="lg:hidden">
                  Takes
                </Label>
                <p className="mt-1 text-body text-pretty text-fg-muted lg:mt-0">{a.input}</p>
              </div>
              <div className="lg:col-span-5">
                <Label as="p" className="lg:hidden">
                  Hands on
                </Label>
                <p className="mt-1 text-body text-pretty text-fg lg:mt-0">{a.output}</p>
                {a.note && (
                  <p className="mt-3 rounded-panel bg-paper-2 px-4 py-3 text-small text-pretty text-fg">
                    <span className="font-medium text-fg">Guardrail hand-off. </span>
                    {a.note}
                  </p>
                )}
                <p className="mt-3 text-small text-pretty text-fg-faint">
                  <span className="text-fg-muted">Runs on · </span>
                  {a.engine}
                </p>
              </div>
            </Reveal>
          ))}
        </ol>
      </Card>
      <p className="mt-5 max-w-3xl text-micro text-pretty text-fg-faint">
        Badges show each agent&rsquo;s backing service right now, from <span className="font-mono">/api/health</span>.
        A failed step can be retried once its service is back.
      </p>
    </LandingSection>
  );
}
