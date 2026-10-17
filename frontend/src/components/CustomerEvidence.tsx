"use client";

import { Badge, Disclosure, GlyphText, ProgressBar } from "@/components/ds";
import type { CustomerEvidence as Evidence } from "@/lib/api";
import { Quote } from "./CustomerVoice";

/** v3: the tech pack's "Customer evidence" section: applied changes with their counts and real quotes. */
export function CustomerEvidence({ items }: { items?: Evidence[] }) {
  if (!items || items.length === 0) return null;
  const sources = Array.from(new Set(items.map((e) => e.source)));
  return (
    <section aria-labelledby="tp-evidence" data-demo="customer-evidence">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <p id="tp-evidence" className="text-small text-fg-muted">
          <span className="font-medium text-fg">
            {items.length} change{items.length > 1 ? "s" : ""} applied
          </span>{" "}
          from what customers said
        </p>
        <p className="text-micro text-fg-faint">{sources.join(" · ")}</p>
      </div>
      <ol className="flex flex-col gap-3">
        {items.map((e) => {
          const key = `${e.datasetId}:${e.changeId}`;
          return (
            <li key={key}>
              <Disclosure
                title={
                  <>
                    <span className="block">{e.title}</span>
                    <span className="mt-0.5 block text-small font-normal text-fg-muted">
                      {e.techPackChange.split(/ [-\u2014] /)[0]}
                    </span>
                  </>
                }
                meta={
                  <span className="text-right font-mono text-small text-fg tabular">
                    {e.count} <span className="text-fg-faint">of {e.base}</span>
                  </span>
                }
              >
                <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_14rem]">
                  <div className="min-w-0">
                    {e.instruction && (
                      <div className="mb-4 rounded-panel bg-accent-soft p-4">
                        <p className="text-small leading-relaxed text-fg">
                          <GlyphText text={e.instruction} />
                        </p>
                        {e.instructionBy && (
                          <p className="mt-1 font-mono text-micro text-fg-faint">drafted by {e.instructionBy}</p>
                        )}
                      </div>
                    )}
                    <ul className="flex flex-col gap-3">
                      {e.quotes.map((q) => (
                        <li key={q.recordId}>
                          <Quote quote={q} compact />
                        </li>
                      ))}
                    </ul>
                    {e.quotes.length === 0 && (
                      <p className="text-small text-fg-faint">No quotes kept for this change.</p>
                    )}
                  </div>
                  <div className="flex flex-col gap-3 self-start rounded-panel bg-paper-2/70 p-4">
                    <ProgressBar
                      value={e.base > 0 ? e.count / e.base : null}
                      label="Share of records"
                      detail={`${e.share.toFixed(1)}%`}
                      tone="accent"
                    />
                    <p className="text-micro text-fg-muted">
                      {e.count} of {e.base} {e.garmentClass ? `${e.garmentClass} ` : ""}records mention it.
                    </p>
                    <Badge tone="neutral">{e.area}</Badge>
                  </div>
                </div>
              </Disclosure>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
