"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import type { Design } from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { CollectionStage, IdeationToggle } from "./Collection";
import {
  Badge,
  Button,
  Card,
  Chip,
  Eyebrow,
  Field,
  FileDrop,
  IconImage,
  Input,
  GarmentTag,
  IconArrowRight,
  IconCheck,
  IconRefresh,
  NotConnected,
  ProgressBar,
  Skeleton,
} from "./ds";
import { cx, EASE } from "./ds/tokens";
import { ErrorNotice, SmartImage } from "./ui";

/**
 * A concept / variation / look: the render on a card with its garment tag ("Look 01"), the garment type and its
 * lineage. Selecting it is the creative director's pick (ink ring + badge). The aria-label is what the guided
 * tour clicks, so it stays "Select concept No. <label>".
 */
export function DesignCard({
  design,
  label,
  index,
  selected,
  disabled,
  onSelect,
  compact,
}: {
  design: Design;
  label: string;
  index: number;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
  compact?: boolean;
}) {
  const parentLabel = useAtelier((s) => (design.parentDesignId ? s.labels[design.parentDesignId] : undefined));
  return (
    <motion.button
      type="button"
      layout="position"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.7, ease: EASE }}
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      aria-label={`Select concept No. ${label}`}
      className={cx(
        "group block w-full rounded-card border bg-surface p-2 text-left shadow-e1 transition-[border-color,box-shadow,transform] duration-300 ease-thread disabled:cursor-default sm:p-2.5",
        selected
          ? "border-accent ring-2 ring-accent"
          : "border-line enabled:hover:-translate-y-0.5 enabled:hover:border-line-bold enabled:hover:shadow-e2",
      )}
    >
      <div className="relative">
        <SmartImage
          src={design.imageUrl}
          alt={`Concept No. ${label}: ${design.garmentType}`}
          className="aspect-[3/4] rounded-panel"
          imgClassName="transition-transform duration-[1.4s] ease-thread group-hover:scale-[1.03]"
        />
        <AnimatePresence>
          {selected && (
            <motion.span
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="absolute top-2.5 left-2.5"
            >
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-accent pr-3 pl-2 text-micro font-medium text-on-accent shadow-e2">
                <IconCheck size={13} strokeWidth={2.6} />
                Selected
              </span>
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <div className={cx("flex min-w-0 flex-col gap-1.5 px-1.5", compact ? "pt-2.5 pb-1" : "pt-3 pb-1.5")}>
        <div className="flex min-w-0 items-center justify-between gap-2">
          <GarmentTag tone={selected ? "ink" : "default"}>
            {design.source === "designer_upload" ? "Sketch" : "Look"} {label}
          </GarmentTag>
          {!compact &&
            (design.source === "designer_upload" ? (
              <span className="text-micro text-fg-faint">Your design</span>
            ) : (
              <span className="font-mono text-micro text-fg-faint tabular" title="Diffusion seed">
                #{design.seed}
              </span>
            ))}
        </div>
        {!compact && (
          <span className="truncate text-small text-fg-muted">
            {design.sketchReading?.garmentName || design.garmentType}
          </span>
        )}
        {parentLabel && (
          <span className="truncate text-micro text-fg-faint">
            {design.directionId ? "Directed" : "Refined"} from {design.source === "designer_upload" ? "Sketch" : "Look"}{" "}
            {parentLabel}
          </span>
        )}
      </div>
    </motion.button>
  );
}

/** Concept-shaped placeholders (3:4 image + tag) while the diffusion model renders. */
export function SkeletonGrid({ count = 4, label }: { count?: number; label: string }) {
  return (
    <div aria-busy aria-label={label} className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.1 }}
          className="rounded-card border border-line bg-surface p-2 sm:p-2.5"
        >
          <Skeleton className="aspect-[3/4] w-full rounded-panel" />
          <div className="flex items-center justify-between px-1.5 pt-3 pb-1.5">
            <Skeleton rounded="sm" className="h-6 w-20" />
            <Skeleton rounded="sm" className="h-3 w-10" />
          </div>
        </motion.div>
      ))}
    </div>
  );
}

/** Chapter II: a toggle between four concepts of one garment and a whole collection (v2). */
export function IdeationStage() {
  const mode = useAtelier((s) => s.ideationMode);
  // Concepts vs collection only matters with a diffusion server; on the sketch path the toggle would mislead.
  const sketchLeads = useAtelier((s) => s.sketchOpen && s.generate.status === "idle" && s.collectionGen.status === "idle");
  return (
    <div>
      {!sketchLeads && (
        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <IdeationToggle />
          <p className="text-small text-fg-muted">
            {mode === "concepts"
              ? "Four variations of one garment."
              : "Different pieces sharing one palette, fabric story and name."}
          </p>
        </div>
      )}
      {mode === "concepts" ? <ConceptsStage /> : <CollectionStage />}
    </div>
  );
}

/**
 * The designer's own sketch, drawing or photo as the concept. The vision model (Gemma 4 on AMD) reads it - garment
 * type, silhouette, the details it can see - and that reading goes into the tech pack, so the factory gets what the
 * designer drew. No diffusion render involved.
 */
function SketchUpload() {
  const upload = useAtelier((s) => s.upload);
  const runUpload = useAtelier((s) => s.runUpload);
  const rounds = useAtelier((s) => s.rounds);
  const designs = useAtelier((s) => s.designs);
  const labels = useAtelier((s) => s.labels);
  const selectedId = useAtelier((s) => s.selectedId);
  const locked = useAtelier((s) => !!s.runId || s.approve.status === "loading");
  const select = useAtelier((s) => s.select);
  const [file, setFile] = useState<File>();
  const [note, setNote] = useState("");
  const busy = upload.status === "loading";
  const ids = rounds.filter((r) => r.kind === "upload").flatMap((r) => r.designIds);
  const picked = selectedId && ids.includes(selectedId) ? designs[selectedId] : undefined;

  return (
    <Card pad="lg" className="flex flex-col gap-6" data-demo="sketch-upload">
      <div className="flex flex-col gap-2">
        <Eyebrow>Your own design</Eyebrow>
        <p className="text-display-m text-fg">Start from your sketch.</p>
        <p className="max-w-2xl text-body text-fg-muted">
          Upload a drawing or a photo of your design. Gemma 4 on AMD reads what you drew and writes it into the tech
          pack, so the factory makes your design, not a guess.
        </p>
      </div>
      {!locked && (
        <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
          <FileDrop
            accept="image/png,image/jpeg,image/webp"
            onFiles={(f) => setFile(f[0])}
            busy={busy}
            icon={<IconImage size={20} />}
            title={file ? file.name : "Drop your sketch or photo"}
            hint="PNG, JPEG or WebP · up to 12 MB"
            aria-label="Upload your sketch"
          />
          <div className="flex flex-col gap-4">
            <Field label="Note for the tech pack" optional hint="e.g. 'shorter sleeves, gold thread on the collar'">
              <Input value={note} maxLength={600} onChange={(e) => setNote(e.target.value)} disabled={busy} />
            </Field>
            <Button
              onClick={() => file && runUpload(file, note)}
              disabled={!file || busy}
              loading={busy}
              trailing={<IconArrowRight size={16} />}
              trailingBadge
            >
              {busy ? "Gemma 4 is reading your sketch…" : "Read my sketch"}
            </Button>
          </div>
        </div>
      )}
      {upload.status === "error" &&
        (upload.hint ? (
          <NotConnected service="Vision model" hint={upload.hint}>
            {upload.error ?? "Sketches are read only by a live vision model, and none answered."}
          </NotConnected>
        ) : (
          <ErrorNotice title="Could not read the sketch" message={upload.error} />
        ))}
      {ids.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          {ids.map((id, i) => (
            <DesignCard
              key={id}
              design={designs[id]}
              label={labels[id]}
              index={i}
              selected={selectedId === id}
              disabled={locked}
              onSelect={() => select(id)}
            />
          ))}
        </div>
      )}
      {picked?.sketchReading && (
        <div className="rounded-panel border border-line bg-paper-2 p-4">
          <p className="text-micro text-fg-faint">
            What {picked.sketchReading.model ?? "the vision model"} read in Sketch {labels[picked.id]}
          </p>
          <p className="mt-2 text-body text-fg">{picked.sketchReading.description}</p>
          {picked.sketchReading.details.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {picked.sketchReading.details.map((d) => (
                <Chip key={d}>{d}</Chip>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function ConceptsStage() {
  const generate = useAtelier((s) => s.generate);
  const rounds = useAtelier((s) => s.rounds);
  const designs = useAtelier((s) => s.designs);
  const labels = useAtelier((s) => s.labels);
  const selectedId = useAtelier((s) => s.selectedId);
  const locked = useAtelier((s) => !!s.runId || s.approve.status === "loading");
  const select = useAtelier((s) => s.select);
  const runGenerate = useAtelier((s) => s.runGenerate);

  const genRounds = rounds.filter((r) => r.kind === "generate");
  const latest = genRounds[genRounds.length - 1];
  const sketchFirst = useAtelier((s) => s.sketchOpen) && !latest; // "Start from my sketch": the upload leads

  return (
    <div className="flex flex-col gap-6">
      {sketchFirst && <SketchUpload />}
      {generate.status === "idle" && !latest && (
        <Card pad="lg" className="flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Eyebrow>Concepts</Eyebrow>
            <p className="mt-3 text-display-m text-fg">Four takes on one garment, from the same signal.</p>
          </div>
          <Button onClick={runGenerate} disabled={locked} size="lg" trailing={<IconArrowRight size={16} />} trailingBadge>
            Generate four concepts
          </Button>
        </Card>
      )}
      {generate.status === "loading" && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between" aria-live="polite">
            <Eyebrow tone="accent" live>
              Rendering four concepts on the diffusion model…
            </Eyebrow>
            <ProgressBar value={null} tone="accent" size="sm" className="sm:max-w-xs" />
          </div>
          <SkeletonGrid label="Generating concepts" />
        </div>
      )}
      {generate.status === "error" &&
        (generate.hint ? (
          <NotConnected service="Diffusion model" hint={generate.hint} onRetry={runGenerate}>
            {generate.error ?? "Concepts are rendered only by a live diffusion model, and none answered."}
          </NotConnected>
        ) : (
          <ErrorNotice title="Concept generation failed" message={generate.error} onRetry={runGenerate} />
        ))}
      {generate.status !== "loading" && latest && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            {latest.designIds.map((id, i) => (
              <DesignCard
                key={id}
                design={designs[id]}
                label={labels[id]}
                index={i}
                selected={selectedId === id}
                disabled={locked}
                onSelect={() => select(id)}
              />
            ))}
          </div>
          <div className="flex flex-col-reverse items-start justify-between gap-3 sm:flex-row sm:items-center">
            <p className="flex items-center gap-2 text-small text-fg-muted">
              {selectedId && latest.designIds.includes(selectedId) ? (
                <>
                  <Badge tone="accent">Look {labels[selectedId]}</Badge> selected - continue to the vibe check below.
                </>
              ) : (
                "Select the concept that speaks to you."
              )}
            </p>
            {!locked && (
              <Button variant="secondary" size="sm" icon={<IconRefresh size={14} />} onClick={runGenerate}>
                Generate four more
              </Button>
            )}
          </div>
        </>
      )}
      {!sketchFirst && <SketchUpload />}
    </div>
  );
}
