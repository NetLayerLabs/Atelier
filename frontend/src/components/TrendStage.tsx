"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  errorMessage,
  getPresets,
  isVisionNotConnected,
  type AnalyzeInput,
  type SourceImage,
  type TrendPreset,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import {
  Button,
  Card,
  Chip,
  Disclosure,
  EmptyState,
  Eyebrow,
  Field,
  FileDrop,
  IconArrowUpRight,
  IconClose,
  IconImage,
  IconSpark,
  InlineAlert,
  Label,
  NotConnected,
  ProgressBar,
  Skeleton,
  SkeletonText,
  Tabs,
  Textarea,
} from "./ds";
import { cx, EASE } from "./ds/tokens";
import { ErrorNotice, SmartImage } from "./ui";

type Tab = "presets" | "upload" | "urls";
const MAX_IMAGES = 6;

export function TrendInput() {
  const [tab, setTab] = useState<Tab>("presets");
  const runAnalyze = useAtelier((s) => s.runAnalyze);
  const busy = useAtelier((s) => s.analyze.status === "loading");

  return (
    <Tabs<Tab>
      label="Trend source"
      value={tab}
      onChange={setTab}
      panelClassName="pt-8"
      items={[
        {
          value: "presets",
          label: "Mood boards",
          content: (
            <PresetPicker disabled={busy} onPick={(p) => runAnalyze({ kind: "preset", preset: p.id }, boardUrls(p), !!p.aiGenerated)} />
          ),
        },
        {
          value: "upload",
          label: "Upload",
          content: <UploadPicker disabled={busy} onSubmit={(files) => runAnalyze({ kind: "files", files })} />,
        },
        {
          value: "urls",
          label: "Image URLs",
          content: <UrlPicker disabled={busy} onSubmit={(imageUrls) => runAnalyze({ kind: "urls", imageUrls })} />,
        },
      ]}
    />
  );
}

function PresetPicker({ onPick, disabled }: { onPick: (p: TrendPreset) => void; disabled: boolean }) {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; presets: TrendPreset[] }
  >({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ok", presets: await getPresets() });
    } catch (err) {
      setState({ kind: "error", message: errorMessage(err) });
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getPresets()
      .then((presets) => alive && setState({ kind: "ok", presets }))
      .catch((err) => alive && setState({ kind: "error", message: errorMessage(err) }));
    return () => {
      alive = false;
    };
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy aria-label="Loading mood boards">
        {[0, 1, 2].map((i) => (
          <Card key={i} pad="sm" className={cx(i === 2 && "hidden lg:block")}>
            <Skeleton rounded="md" className="aspect-[5/4] w-full" />
            <Skeleton rounded="sm" className="mt-4 h-3 w-1/3" />
            <Skeleton rounded="sm" className="mt-2 h-5 w-2/3" />
          </Card>
        ))}
      </div>
    );
  }
  if (state.kind === "error") {
    return <ErrorNotice title="Couldn't load mood boards" message={state.message} onRetry={load} />;
  }
  if (state.presets.length === 0) {
    return (
      <EmptyState icon={<IconImage size={20} />} title="No mood boards on this backend">
        Upload your own images or paste image links instead.
      </EmptyState>
    );
  }
  return (
    <div>
      <p className="mb-6 max-w-2xl text-body text-fg-muted">
        Our pilot brand&rsquo;s own AI-generated inspiration boards, and real, openly licensed photographs. Picking a
        board sends its images to the vision model, which reads the trend live. Nothing is pre-written.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {state.presets.map((p, i) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08, duration: 0.7, ease: EASE }}
          >
            <Card pad="none" interactive={!disabled} className="group flex h-full flex-col">
              <button
                type="button"
                data-demo={`preset-${p.id}`}
                disabled={disabled}
                onClick={() => onPick(p)}
                aria-label={`Read the mood board “${p.name}”`}
                className="block w-full rounded-card p-3 text-left disabled:cursor-wait disabled:opacity-60"
              >
                <div className="relative">
                  <BoardCollage preset={p} />
                  <span className="absolute right-3 bottom-3 inline-flex h-9 translate-y-1 items-center gap-2 rounded-full bg-surface pr-1 pl-3.5 text-small font-medium text-fg opacity-0 shadow-e2 transition-[opacity,transform] duration-300 ease-thread group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100">
                    Read this board
                    <span aria-hidden className="grid size-7 place-items-center rounded-full bg-inverse text-on-inverse">
                      <IconArrowUpRight size={14} />
                    </span>
                  </span>
                </div>
                <div className="px-2 pt-4 pb-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Label>
                      Board {String(i + 1).padStart(2, "0")} · {boardUrls(p).length}{" "}
                      {p.aiGenerated ? "images" : "photos"}
                    </Label>
                    {p.aiGenerated && <Chip>AI-generated inspiration</Chip>}
                  </div>
                  <p className="mt-1.5 text-title text-fg">{p.name}</p>
                </div>
              </button>
              {p.credit && (
                <p className="mt-auto px-5 pb-4 text-micro text-fg-faint">
                  {p.images?.[0]?.sourceUrl ? (
                    <a
                      href={p.images[0].sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="underline decoration-line-strong underline-offset-2 hover:text-fg"
                    >
                      {p.credit}
                    </a>
                  ) : (
                    p.credit
                  )}
                </p>
              )}
            </Card>
          </motion.div>
        ))}
      </div>
      <ImageCredits presets={state.presets} />
    </div>
  );
}

/** Every image URL of a board (falls back to the single thumbnail for older backends). */
function boardUrls(p: TrendPreset): string[] {
  return p.images?.length ? p.images.map((im) => im.url) : [p.thumbnailUrl];
}

const ZOOM = "transition-transform duration-[1.2s] ease-thread group-hover:scale-[1.04]";

function BoardCollage({ preset }: { preset: TrendPreset }) {
  const urls = boardUrls(preset);
  if (urls.length < 3) {
    return <SmartImage src={urls[0]} alt="" className="aspect-[5/4] rounded-panel" imgClassName={ZOOM} />;
  }
  // Lead photo on the left, the rest stacked on the right; 8px gutters like pinned prints.
  const [lead, ...rest] = urls.slice(0, 4);
  return (
    <div className="relative aspect-[5/4]">
      {/* Absolute so the photos' intrinsic sizes can't stretch the card: every board is the same tile. */}
      <div className="absolute inset-0 grid grid-cols-[3fr_2fr] gap-2">
        <SmartImage src={lead} alt="" className="h-full min-h-0 rounded-panel" imgClassName={ZOOM} />
        <div className="grid min-h-0 gap-2" style={{ gridTemplateRows: `repeat(${rest.length}, minmax(0, 1fr))` }}>
          {rest.map((u) => (
            <SmartImage key={u} src={u} alt="" className="h-full min-h-0 rounded-[12px]" imgClassName={ZOOM} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ImageCredits({ presets }: { presets: TrendPreset[] }) {
  const boards = presets.filter((p) => p.images?.length);
  if (!boards.length) return null;
  return (
    <Disclosure
      className="mt-8"
      variant="card"
      title={<span className="text-small font-medium">Image credits</span>}
      meta={<span className="text-micro text-fg-faint">{boards.reduce((n, b) => n + (b.images?.length ?? 0), 0)} images</span>}
    >
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {boards.map((p) => (
          <div key={p.id}>
            <p className="text-small font-medium text-fg">{p.name}</p>
            <ul className="mt-2 flex flex-col gap-1.5">
              {(p.images ?? []).map((im) => (
                <CreditLine key={im.url} image={im} />
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-6 text-micro text-fg-faint">
        UGO SARTORIA boards are the pilot brand&rsquo;s own AI-generated inspiration, not photographs. Photos are
        downscaled and re-encoded; nothing else is changed. Garments and logos shown belong to their owners.
        Full list with sources: backend/static/moodboards/ATTRIBUTION.md.
      </p>
    </Disclosure>
  );
}

export function CreditLine({ image }: { image: SourceImage }) {
  return (
    <li className="text-micro text-fg-faint">
      {image.aiGenerated ? (
        <>
          <span className="text-fg-muted">{image.title}</span> · {image.creator} · {image.license}
        </>
      ) : (
        <>
      <a href={image.sourceUrl} target="_blank" rel="noreferrer" className="text-fg-muted hover:text-fg hover:underline">
        {image.title}
      </a>{" "}
      · {image.creator} ·{" "}
      <a href={image.licenseUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-fg">
        {image.license}
      </a>
        </>
      )}
    </li>
  );
}

function UploadPicker({ onSubmit, disabled }: { onSubmit: (files: File[]) => void; disabled: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState<string>();
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const add = (list: File[]) => {
    const images = list.filter((f) => f.type.startsWith("image/"));
    const rejected = list.length - images.length;
    const merged = [...files, ...images];
    setFiles(merged.slice(0, MAX_IMAGES));
    setNote(
      merged.length > MAX_IMAGES
        ? `Up to ${MAX_IMAGES} images - kept the first ${MAX_IMAGES}.`
        : rejected
          ? `${rejected} file${rejected > 1 ? "s were" : " was"} not an image and skipped.`
          : undefined,
    );
  };

  return (
    <div className="flex flex-col gap-5">
      <FileDrop
        onFiles={add}
        accept="image/*"
        multiple
        disabled={disabled}
        title="Drop your mood board"
        hint={`1–${MAX_IMAGES} images · runway, street, archive, texture · or click to choose`}
        icon={<IconImage size={18} />}
        className="min-h-56"
      />
      {note && <InlineAlert tone="warn" title={note} />}
      {files.length > 0 && (
        <Card pad="sm">
          <div className="mb-3 flex items-center justify-between gap-3 px-1">
            <Label>
              {files.length} of {MAX_IMAGES} images
            </Label>
            <Button variant="ghost" size="sm" onClick={() => setFiles([])}>
              Clear
            </Button>
          </div>
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="relative">
                <SmartImage src={previews[i]} alt={f.name} className="aspect-square rounded-[12px]" />
                <button
                  type="button"
                  onClick={() => setFiles(files.filter((_, j) => j !== i))}
                  aria-label={`Remove ${f.name}`}
                  className="absolute top-1.5 right-1.5 grid size-8 place-items-center rounded-full bg-surface/90 text-fg shadow-e1 backdrop-blur hover:text-bad"
                >
                  <IconClose size={13} strokeWidth={2.2} />
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex justify-end">
            <Button
              className="w-full sm:w-auto"
              onClick={() => onSubmit(files)}
              disabled={disabled}
              icon={<IconSpark size={15} />}
            >
              Analyse {files.length} image{files.length > 1 ? "s" : ""}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function UrlPicker({ onSubmit, disabled }: { onSubmit: (urls: string[]) => void; disabled: boolean }) {
  const [text, setText] = useState("");
  const urls = text
    .split(/[\s,]+/)
    .map((u) => u.trim())
    .filter(Boolean);
  const invalid = urls.filter((u) => !/^https?:\/\/\S+$/i.test(u));
  const tooMany = urls.length > MAX_IMAGES;
  const valid = urls.length > 0 && invalid.length === 0 && !tooMany;
  const error = invalid.length > 0 ? `Not a valid http(s) URL: ${invalid[0]}` : tooMany ? `Up to ${MAX_IMAGES} images, please.` : undefined;

  return (
    <Card pad="md" className="max-w-3xl">
      <Field
        id="trend-urls"
        label="Image links"
        hint={`One image URL per line, up to ${MAX_IMAGES}. Atelier fetches them and sends them to the vision model.`}
        error={error}
      >
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder={"https://…/runway-look-01.jpg\nhttps://…/street-style.png"}
          className="font-mono text-small"
        />
      </Field>
      <div className="mt-5 flex justify-end">
        <Button className="w-full sm:w-auto" disabled={!valid || disabled} onClick={() => onSubmit(urls)} icon={<IconSpark size={15} />}>
          Analyse {urls.length || ""} image{urls.length === 1 ? "" : "s"}
        </Button>
      </div>
    </Card>
  );
}

const NO_PREVIEWS: string[] = [];

export function Analysing({
  input,
  previewUrls = NO_PREVIEWS,
  aiGenerated = false,
}: {
  input?: AnalyzeInput;
  previewUrls?: string[];
  aiGenerated?: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  const previews = useMemo(() => {
    if (previewUrls.length || !input) return previewUrls;
    if (input.kind === "urls") return input.imageUrls;
    if (input.kind === "files") return input.files.map((f) => URL.createObjectURL(f));
    return [];
  }, [input, previewUrls]);
  useEffect(() => () => previews.forEach((u) => u.startsWith("blob:") && URL.revokeObjectURL(u)), [previews]);

  const n =
    input?.kind === "files" ? input.files.length : input?.kind === "urls" ? input.imageUrls.length : previews.length;
  const what = n > 0 ? `${n} image${n === 1 ? "" : "s"}` : "the images";

  return (
    <div className="flex flex-col gap-4" aria-live="polite" aria-busy>
      <Card pad="sm" className="grid grid-cols-1 items-center gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-10">
        <div className="relative aspect-[5/4] overflow-hidden rounded-panel">
          {previews.length > 0 ? (
            <div className={cx("grid h-full gap-2", previews.length > 1 ? "grid-cols-2" : "grid-cols-1")}>
              {previews.slice(0, 4).map((u) => (
                <SmartImage key={u} src={u} alt="" className="h-full rounded-[12px]" imgClassName="opacity-70" />
              ))}
            </div>
          ) : (
            <Skeleton rounded="md" className="h-full w-full" />
          )}
          <div className="scanline" />
        </div>
        <div className="px-2 pb-4 md:py-6 md:pr-8">
          <div className="flex flex-wrap items-center gap-2">
            <Eyebrow tone="accent" live>
              Analysing · live
            </Eyebrow>
            {aiGenerated && <Chip>AI-generated inspiration</Chip>}
          </div>
          <p className="mt-4 text-display-m text-balance text-fg">The vision model is reading {what}…</p>
          <ProgressBar value={null} tone="accent" className="mt-8 max-w-md" />
          <p className="mt-6 max-w-md text-body text-fg-muted">
            Atelier sent {what} to the vision model and is waiting for its answer: a trend name, silhouettes, palette,
            fabrics and a viability score. Nothing is pre-written.
          </p>
          <p className="mt-3 font-mono text-micro text-fg-faint tabular" aria-live="off">
            {elapsed}s elapsed
          </p>
        </div>
      </Card>
      {/* The shape of the read that is on its way. */}
      <div aria-hidden className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Card pad="lg">
          <Skeleton rounded="sm" className="h-3 w-40" />
          <Skeleton rounded="sm" className="mt-5 h-10 w-3/4" />
          <SkeletonText lines={3} className="mt-5 max-w-xl" />
          <Skeleton rounded="sm" className="mt-8 h-10 w-full" />
        </Card>
        <Card pad="lg" className="flex items-center justify-center">
          <Skeleton rounded="full" className="size-36" />
        </Card>
      </div>
    </div>
  );
}

/** Error state for a failed analysis: says plainly when no vision model is connected (v5: with the 503's hint). */
export function AnalysisError({ message, hint, onRetry }: { message?: string; hint?: string; onRetry: () => void }) {
  if (isVisionNotConnected(message)) {
    return (
      <NotConnected
        service="Vision model"
        hint={hint ?? "Set AMD_VISION_ENDPOINT (see docs/AMD_SETUP.md), then retry."}
        onRetry={onRetry}
      >
        Atelier reads trends only with a live vision model, and none is configured. Nothing was generated.
      </NotConnected>
    );
  }
  return <ErrorNotice title="Trend analysis failed" message={message} hint={hint} onRetry={onRetry} />;
}
