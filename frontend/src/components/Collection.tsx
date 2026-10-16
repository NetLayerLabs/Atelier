"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { useAtelier, type IdeationMode } from "@/lib/store";
import { DesignCard } from "./Designs";
import {
  Button,
  Card,
  Em,
  Eyebrow,
  IconArrowRight,
  IconRefresh,
  Label,
  NotConnected,
  ProgressBar,
  Segmented,
  Skeleton,
  SkeletonText,
  SwatchStrip,
} from "./ds";
import { EASE } from "./ds/tokens";
import { RouteTag } from "./Inference";
import { ErrorNotice } from "./ui";

const SIZES = [3, 4, 5];
const isHex = (c: string) => /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(c.trim());

export function IdeationToggle() {
  const mode = useAtelier((s) => s.ideationMode);
  const setMode = useAtelier((s) => s.setIdeationMode);
  return (
    <Segmented<IdeationMode>
      label="Ideation mode"
      value={mode}
      onChange={setMode}
      options={[
        { value: "concepts", label: "Four concepts", title: "Four variations of one garment" },
        { value: "collection", label: "Collection", title: "A coherent capsule of different pieces" },
      ]}
    />
  );
}

function SizePicker({ size, onChange, disabled }: { size: number; onChange: (n: number) => void; disabled?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <Label>Looks</Label>
      <Segmented<string>
        label="Number of looks"
        size="sm"
        value={String(size)}
        onChange={(v) => onChange(Number(v))}
        options={SIZES.map((n) => ({ value: String(n), label: n, disabled }))}
      />
    </div>
  );
}

export function CollectionStage() {
  const gen = useAtelier((s) => s.collectionGen);
  const rounds = useAtelier((s) => s.rounds);
  const collections = useAtelier((s) => s.collections);
  const designs = useAtelier((s) => s.designs);
  const labels = useAtelier((s) => s.labels);
  const selectedId = useAtelier((s) => s.selectedId);
  const trend = useAtelier((s) => s.trend);
  const locked = useAtelier((s) => !!s.runId || s.approve.status === "loading");
  const select = useAtelier((s) => s.select);
  const runCollection = useAtelier((s) => s.runCollection);
  const [size, setSize] = useState(gen.size ?? 4);

  const latest = rounds.filter((r) => r.kind === "collection").at(-1);
  const col = latest?.collectionId ? collections[latest.collectionId] : undefined;

  if (gen.status === "loading") {
    const n = gen.size ?? size;
    return (
      <div aria-busy aria-label="Composing collection" className="flex flex-col gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between" aria-live="polite">
          <Eyebrow tone="accent" live>
            Composing a {n}-look collection - shared palette, fabrics and story…
          </Eyebrow>
          <ProgressBar value={null} tone="accent" size="sm" className="sm:max-w-xs" />
        </div>
        <Card pad="lg">
          <Skeleton rounded="sm" className="h-10 w-1/2 max-w-md" />
          <SkeletonText lines={2} className="mt-5 max-w-2xl" />
          <Skeleton rounded="sm" className="mt-6 h-9 w-full" />
        </Card>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]">
          {Array.from({ length: n }, (_, i) => (
            <div key={i} className="rounded-card border border-line bg-surface p-2.5">
              <Skeleton className="aspect-[3/4] w-full" />
              <Skeleton rounded="sm" className="mt-3 h-5 w-1/2" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const palette = col && trend && trend.id === col.trendId ? trend.colorPalette.filter(isHex) : [];

  return (
    <div className="flex flex-col gap-6">
      {gen.status === "error" &&
        (gen.hint ? (
          <NotConnected
            service="Brain and diffusion model"
            hint={gen.hint}
            onRetry={() => runCollection(gen.size ?? size)}
          >
            {gen.error ?? "A collection needs the brain to plan it and the diffusion model to render it."}
          </NotConnected>
        ) : (
          <ErrorNotice title="Collection failed" message={gen.error} onRetry={() => runCollection(gen.size ?? size)} />
        ))}
      {!col ? (
        <Card pad="lg" className="flex flex-col gap-8">
          <div>
            <Eyebrow>Collection mode</Eyebrow>
            <p className="mt-4 max-w-3xl text-display-m text-fg">
              One trend, a whole capsule - <Em>different pieces</Em> that share a palette, a fabric story and a name.
            </p>
          </div>
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <SizePicker size={size} onChange={setSize} disabled={locked} />
            <Button
              onClick={() => runCollection(size)}
              disabled={locked}
              size="lg"
              trailing={<IconArrowRight size={16} />}
              trailingBadge
            >
              Compose the collection
            </Button>
          </div>
        </Card>
      ) : (
        <>
          {/* Lookbook cover */}
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EASE }}>
            <Card pad="lg" className="overflow-hidden">
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
                <div className="min-w-0">
                  <Eyebrow>
                    Lookbook <span className="text-fg-faint">·</span> {col.designs.length} looks
                  </Eyebrow>
                  <h3 className="mt-4 text-display-l text-fg">{col.name}</h3>
                  {col.generatedBy && (
                    <p className="mt-3 flex items-center gap-1.5 text-micro text-fg-faint">
                      planned by <RouteTag route={col.generatedBy} />
                    </p>
                  )}
                </div>
                <p className="self-end text-body-l text-fg-muted">{col.story}</p>
              </div>
              {palette.length > 0 && (
                <div className="mt-8">
                  <div className="mb-2.5 flex items-baseline justify-between gap-3">
                    <Label>Shared palette</Label>
                    <span className="font-mono text-micro text-fg-faint uppercase">{palette.join(" · ")}</span>
                  </div>
                  <SwatchStrip colors={palette.map((c) => ({ color: c, name: c.toUpperCase() }))} height={36} />
                </div>
              )}
            </Card>
          </motion.div>

          {/* Looks: two up on phones, one row on desktop */}
          <ol
            className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-[repeat(var(--looks),minmax(0,1fr))]"
            style={{ ["--looks" as string]: col.looks.length }}
          >
            {col.looks.map((look, i) => {
              const d = designs[look.designId];
              if (!d) return null;
              return (
                <li key={look.designId} className="flex min-w-0 flex-col">
                  <DesignCard
                    design={d}
                    label={labels[d.id]}
                    index={i}
                    selected={selectedId === d.id}
                    disabled={locked}
                    onSelect={() => select(d.id)}
                  />
                  <div className="px-2 pt-3">
                    <p className="text-small font-medium text-fg">{look.title}</p>
                    <p className="mt-1 text-small text-fg-muted">{look.caption}</p>
                  </div>
                </li>
              );
            })}
          </ol>

          <div className="flex flex-col-reverse items-start justify-between gap-4 sm:flex-row sm:items-center">
            <p className="text-small text-fg-muted">
              {selectedId && designs[selectedId]?.collectionId === col.id
                ? "Look selected - direct it or approve it below."
                : "Each look is a full design: select one to direct it or send it to production."}
            </p>
            {!locked && (
              <div className="flex flex-wrap items-center gap-3">
                <SizePicker size={size} onChange={setSize} />
                <Button variant="secondary" size="sm" icon={<IconRefresh size={14} />} onClick={() => runCollection(size)}>
                  Recompose
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
