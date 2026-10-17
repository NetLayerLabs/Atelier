"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import type { TrendAnalysis } from "@/lib/api";
import { Card, Chip, Disclosure, Eyebrow, GarmentTag, Label, Ring, StatusDot, Swatch, SwatchStrip } from "./ds";
import { EASE, RISE } from "./ds/tokens";
import { CreditLine } from "./TrendStage";
import { SmartImage } from "./ui";

function viabilityLabel(score: number) {
  if (score >= 80) return "Strong commercial signal";
  if (score >= 60) return "Promising";
  if (score >= 40) return "Niche appeal";
  return "Speculative";
}

const isHex = (c: string) => /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(c.trim());

const stagger = { show: { transition: { staggerChildren: 0.08 } } };

export function TrendAnalysisView({ trend }: { trend: TrendAnalysis }) {
  const raw = trend.commercialViabilityScore;
  const hasScore = typeof raw === "number" && Number.isFinite(raw);
  const score = hasScore ? Math.max(0, Math.min(100, Math.round(raw))) : null;
  const palette = trend.colorPalette.filter(isHex);

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]"
    >
      {/* The read itself */}
      <motion.div variants={RISE} className="min-w-0">
        <Card pad="lg" className="h-full overflow-hidden">
                    <div className="relative">
            <Eyebrow tone="accent">
              Trend identified <span className="text-fg-faint">·</span> {trend.garmentType}
            </Eyebrow>
            <h3 className="mt-5 text-display-m text-balance text-fg sm:text-display-l">{trend.trendName}</h3>
            <p className="mt-5 max-w-2xl text-body-l text-pretty text-fg-muted">{trend.summary}</p>
            <AnalyzedByLine trend={trend} />
          </div>

          {palette.length > 0 && (
            <div className="relative mt-10">
              <div className="mb-3 flex items-baseline justify-between gap-3">
                <Label>Palette</Label>
                <span className="text-micro text-fg-faint">{palette.length} colours, read from the images</span>
              </div>
              <SwatchStrip colors={palette.map((c) => ({ color: c, name: c.toUpperCase() }))} height={44} />
              <ul className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-6">
                {palette.map((hex, i) => (
                  <motion.li
                    key={`${hex}-${i}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.06, duration: 0.6, ease: EASE }}
                  >
                    <Swatch color={hex} code={hex} />
                  </motion.li>
                ))}
              </ul>
            </div>
          )}

          {trend.sourceImageUrls.length > 0 && (
            <div className="relative mt-10">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
                <Label>What the model read · {trend.sourceImageUrls.length} references</Label>
                {trend.sourceImages?.some((im) => im.aiGenerated) && <Chip>AI-generated inspiration</Chip>}
              </div>
              <ul className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {trend.sourceImageUrls.slice(0, 6).map((u, i) => (
                  <li key={`${u}-${i}`}>
                    <SmartImage src={u} alt={`Reference ${i + 1}`} className="aspect-[3/4] rounded-[12px]" />
                  </li>
                ))}
              </ul>
              {trend.sourceImages && trend.sourceImages.length > 0 && (
                <Disclosure variant="row" className="mt-2 border-b-0" title={<span className="text-small">Image credits</span>}>
                  <ul className="flex flex-col gap-1.5">
                    {trend.sourceImages.map((im) => (
                      <CreditLine key={im.url} image={im} />
                    ))}
                  </ul>
                </Disclosure>
              )}
            </div>
          )}
        </Card>
      </motion.div>

      {/* Instruments + tags */}
      <div className="flex min-w-0 flex-col gap-4">
        {score != null && (
          <motion.div variants={RISE}>
            <Card pad="md" className="flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left lg:flex-col lg:text-center">
              <Ring
                value={score / 100}
                label="Commercial viability"
                display={score}
                caption="out of 100"
                size={148}
              />
              <div className="min-w-0">
                <Eyebrow>Commercial viability</Eyebrow>
                <p className="mt-2 text-title text-fg">{viabilityLabel(score)}</p>
                <p className="mt-1 text-micro text-fg-faint">The vision model&rsquo;s own score for this read, 1–100.</p>
              </div>
            </Card>
          </motion.div>
        )}

        <motion.div variants={RISE} className="flex-1">
          <Card pad="md" className="flex h-full flex-col gap-6">
            <TagGroup label="Core silhouettes" items={trend.coreSilhouettes}>
              {(s) => <GarmentTag>{s}</GarmentTag>}
            </TagGroup>
            <TagGroup label="Key fabrics" items={trend.keyFabrics}>
              {(s) => <Chip>{s}</Chip>}
            </TagGroup>
          </Card>
        </motion.div>
      </div>
    </motion.div>
  );
}

/** "Analysed by <model> on <host>" - straight from the vision call's telemetry. */
function AnalyzedByLine({ trend }: { trend: TrendAnalysis }) {
  const by = trend.analyzedBy;
  if (!by?.model && !by?.endpointHost) return null;
  const secs = by.latencyMs ? ` · ${(by.latencyMs / 1000).toFixed(1)}s` : "";
  return (
    <p className="mt-6 inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-full bg-paper-2 px-3 py-1.5 font-mono text-micro text-fg-muted">
      <StatusDot tone="ok" size={6} />
      <span className="min-w-0 break-words">
        Analysed by <span className="text-fg">{by.model ?? "the vision model"}</span>
        {by.endpointHost && (
          <>
            {" "}
            on <span className="text-fg">{by.endpointHost}</span>
          </>
        )}
        {by.gpu && <> · {by.gpu}</>}
        {secs}
        {by.imagesAnalyzed != null && by.imagesSubmitted != null && by.imagesSubmitted > by.imagesAnalyzed && (
          <>
            {" "}
            · read the first {by.imagesAnalyzed} of {by.imagesSubmitted} images (max {by.imagesAnalyzed} per prompt)
          </>
        )}
      </span>
    </p>
  );
}

function TagGroup({ label, items, children }: { label: string; items: string[]; children: (s: string) => ReactNode }) {
  if (!items.length) return null;
  return (
    <div>
      <Label>{label}</Label>
      <ul className="mt-3 flex flex-wrap gap-2">
        {items.map((s, i) => (
          <motion.li
            key={`${s}-${i}`}
            className="max-w-full"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 + i * 0.06, duration: 0.5, ease: EASE }}
          >
            {children(s)}
          </motion.li>
        ))}
      </ul>
    </div>
  );
}
