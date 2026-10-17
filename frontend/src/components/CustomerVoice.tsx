"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  errorMessage,
  getVoiceSamples,
  type RecommendedChange,
  type VoiceInsights,
  type VoiceQuote,
  type VoiceSample,
  type VoiceTheme,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { useVoice } from "@/lib/voice";
import {
  Badge,
  Button,
  Card,
  Chip,
  Disclosure,
  Eyebrow,
  FileDrop,
  GlyphRating,
  GlyphStar,
  GlyphText,
  IconArrowRight,
  IconCheck,
  IconChevronDown,
  IconDocument,
  IconMessage,
  InlineAlert,
  Label,
  ProgressBar,
  Radar,
  SectionHeading,
  Skeleton,
  Stat,
  StatGroup,
  type Tone,
} from "./ds";
import { cx, DUR, EASE } from "./ds/tokens";
import { RouteTag } from "./Inference";
import { ErrorNotice } from "./ui";
import { useAdminAuth } from "./AdminLogin";

const ACCEPT = ".csv,.tsv,.txt,.pdf,text/csv,text/tab-separated-values,application/pdf";
const MAX_MB = 10;

/** v3: "Start from what your customers say" - the merchant's own reviews / returns / tickets. */
export function CustomerVoice() {
  const status = useVoice((s) => s.status);
  const error = useVoice((s) => s.error);
  const input = useVoice((s) => s.input);
  const insights = useVoice((s) => s.insights);
  const analyse = useVoice((s) => s.analyse);
  const clear = useVoice((s) => s.clear);

  return (
    <section aria-labelledby="voice-title" className="mt-20 sm:mt-28" data-demo="voice">
      <SectionHeading
        size="m"
        id="voice-title"
        eyebrow={
          <Eyebrow tone="accent">
            Customer voice <span className="text-fg-faint">·</span> reviews, returns, tickets
          </Eyebrow>
        }
        title="Start from what your customers say"
        lede="Drop in your own review, return or support-ticket export. Atelier counts what customers keep raising, quotes them word for word, and turns the patterns into tech pack changes you can apply to the design."
        actions={
          status === "done" ? (
            <Button variant="secondary" size="sm" onClick={clear}>
              Use different data
            </Button>
          ) : undefined
        }
      />

      <div className="mt-10">
        <AnimatePresence mode="wait" initial={false}>
          {status === "loading" ? (
            <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <VoiceAnalysing label={input?.kind === "file" ? input.file.name : input?.title} />
            </motion.div>
          ) : status === "done" && insights ? (
            <motion.div
              key="done"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: DUR.reveal, ease: EASE }}
            >
              <VoiceResults insights={insights} />
            </motion.div>
          ) : (
            <motion.div key="input" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {status === "error" && (
                <div className="mb-6">
                  <ErrorNotice
                    title="Couldn't analyse that data"
                    message={error}
                    onRetry={input ? () => analyse(input) : undefined}
                  />
                </div>
              )}
              <VoiceInputs />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- inputs

function VoiceInputs() {
  const analyse = useVoice((s) => s.analyse);
  const [note, setNote] = useState<string>();

  const pick = (files: File[]) => {
    const file = files[0];
    if (!file) return;
    if (!/\.(csv|tsv|txt|pdf)$/i.test(file.name)) {
      setNote(`${file.name} isn't a CSV, TSV or PDF.`);
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setNote(`${file.name} is over ${MAX_MB} MB.`);
      return;
    }
    setNote(undefined);
    void analyse({ kind: "file", file });
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Card pad="sm" className="flex flex-col gap-3">
        <FileDrop
          onFiles={pick}
          accept={ACCEPT}
          data-demo="voice-upload"
          title="Drop your customer data"
          hint={`CSV or PDF, up to ${MAX_MB} MB · reviews (Shopify, Judge.me, Yotpo…), return reasons, support tickets · columns detected automatically`}
          icon={<IconDocument size={18} />}
          className="min-h-60 flex-1"
        />
        {note && <InlineAlert tone="warn" title={note} />}
        <p className="px-2 pb-1 text-micro text-fg-faint">
          Files stay in this session&rsquo;s memory on the Atelier backend. Email, phone and name columns are ignored.
        </p>
      </Card>
      <SamplePicker />
    </div>
  );
}

function SamplePicker() {
  const analyse = useVoice((s) => s.analyse);
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; samples: VoiceSample[] }
  >({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    getVoiceSamples()
      .then((samples) => alive && setState({ kind: "ok", samples }))
      .catch((err) => alive && setState({ kind: "error", message: errorMessage(err) }));
    return () => {
      alive = false;
    };
  }, [attempt]);

  const source = state.kind === "ok" ? state.samples[0]?.source : undefined;
  return (
    <Card pad="md">
      <Eyebrow>No data to hand? Use a sample</Eyebrow>
      {state.kind === "loading" && (
        <div className="mt-4 flex flex-col gap-2" aria-busy aria-label="Loading samples">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}
      {state.kind === "error" && (
        <div className="mt-4">
          <ErrorNotice
            title="Samples unavailable"
            message={state.message}
            onRetry={() => {
              setState({ kind: "loading" });
              setAttempt((a) => a + 1);
            }}
          />
        </div>
      )}
      {state.kind === "ok" && state.samples.length === 0 && (
        <p className="mt-4 text-small text-fg-muted">No sample datasets on this backend.</p>
      )}
      {state.kind === "ok" && state.samples.length > 0 && (
        <>
          <ul className="mt-4 flex flex-col gap-2">
            {state.samples.map((s) => (
              <li key={s.key}>
                <button
                  type="button"
                  onClick={() => analyse({ kind: "sample", key: s.key, title: `Sample: ${s.title}` })}
                  data-demo={`voice-sample-${s.key}`}
                  className="group flex min-h-16 w-full items-center justify-between gap-4 rounded-panel border border-line bg-surface px-4 py-3 text-left transition-[border-color,background-color] duration-200 hover:border-line-bold hover:bg-surface-muted"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-paper-2 text-fg-muted">
                      <IconMessage size={16} />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-body font-medium text-fg">{s.title}</span>
                      <span className="block font-mono text-micro text-fg-faint tabular">{s.records} real reviews</span>
                    </span>
                  </span>
                  <span className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-line-strong px-3 text-small text-fg transition-colors group-hover:border-inverse group-hover:bg-inverse group-hover:text-on-inverse">
                    Analyse
                    <IconArrowRight size={13} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {source && <SourceNote source={source} />}
        </>
      )}
    </Card>
  );
}

function SourceNote({ source }: { source: VoiceInsights["source"] }) {
  return (
    <p className="mt-3 text-micro text-fg-faint">
      Sample: public review dataset ·{" "}
      {source.url ? (
        <a href={source.url} target="_blank" rel="noreferrer" className="underline decoration-line-strong underline-offset-2 hover:text-fg">
          Women&rsquo;s E-Commerce Clothing Reviews
        </a>
      ) : (
        "Women’s E-Commerce Clothing Reviews"
      )}{" "}
      · {source.licence}. Unedited, anonymised reviews; a seeded random sample.
    </p>
  );
}

const PHASES = [
  "Detecting columns",
  "Reading every review",
  "Matching fit & fabric language",
  "Discounting negations",
  "Counting by garment class",
  "Drafting tech pack changes",
];

function VoiceAnalysing({ label }: { label?: string }) {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setPhase((p) => Math.min(p + 1, PHASES.length - 1)), 700);
    return () => clearInterval(id);
  }, []);
  return (
    <Card pad="lg" className="grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" aria-live="polite" aria-busy>
      <div className="flex flex-col gap-3" aria-hidden>
        {[92, 71, 58, 44, 31, 22].map((w, i) => (
          <div key={i} style={{ width: `${w}%` }}>
            <Skeleton rounded="full" className="h-2.5" />
          </div>
        ))}
      </div>
      <div>
        <Eyebrow tone="accent" live>
          Analysing{label ? ` · ${label}` : ""}
        </Eyebrow>
        <p className="mt-3 text-display-m text-fg">{PHASES[phase]}…</p>
        <ProgressBar value={(phase + 1) / PHASES.length} tone="accent" size="sm" className="mt-6 max-w-md" />
        <p className="mt-4 max-w-md text-small text-fg-muted">
          Counts come from a deterministic apparel taxonomy, so every number is reproducible and every quote is a real
          record.
        </p>
      </div>
    </Card>
  );
}

// --------------------------------------------------------------------------- results

const POLARITY: Record<VoiceTheme["polarity"], { label: string; tone: Tone }> = {
  negative: { label: "Complaint", tone: "bad" },
  positive: { label: "Praise", tone: "ok" },
  mixed: { label: "Mixed", tone: "warn" },
};

const pct = (v: number) => `${v < 10 ? v.toFixed(1) : Math.round(v)}%`;

function VoiceResults({ insights }: { insights: VoiceInsights }) {
  const classes = insights.garmentClasses.length;
  return (
    <div className="flex flex-col gap-4">
      <Card pad="lg">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <Eyebrow>Dataset</Eyebrow>
            <p className="mt-2 text-title text-fg">{insights.name}</p>
            {insights.columns.text && (
              <p className="mt-1 font-mono text-micro text-fg-faint">text column “{insights.columns.text}”</p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            <Badge status="measured">Counts: deterministic</Badge>
            {insights.phrasedBy && (
              <span className="inline-flex items-center gap-1.5 text-micro text-fg-faint">
                phrased by <RouteTag route={insights.phrasedBy} />
              </span>
            )}
          </div>
        </div>
        <StatGroup className="mt-8">
          <Stat label={insights.noun} count={insights.analysedCount} size="sm" />
          {insights.avgRating != null && (
            <Stat label="average rating" value={insights.avgRating.toFixed(1)} unit={<GlyphStar />} size="sm" />
          )}
          {classes > 0 && <Stat label={classes === 1 ? "garment class" : "garment classes"} value={classes} size="sm" />}
          <Stat label="themes found" value={insights.themes.length} size="sm" />
        </StatGroup>
        <p className="mt-8 max-w-4xl text-body-l text-pretty text-fg-muted">
          <GlyphText text={insights.summary} />
        </p>
        {insights.phrasingError && (
          <InlineAlert tone="warn" className="mt-5" title="Not phrased by a model">
            {insights.phrasingError}. The counts and quotes below are computed from the data either way.
          </InlineAlert>
        )}
        {insights.source.kind === "sample" && <SourceNote source={insights.source} />}
        {insights.warnings.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1 text-micro text-fg-faint">
            {insights.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <VoiceRadar insights={insights} />
        <ThemeList insights={insights} />
      </div>

      <ChangeList insights={insights} />

      <Disclosure title={<span className="text-small font-medium">How this is counted</span>}>
        <p className="max-w-4xl text-small text-fg-muted">{insights.method}</p>
      </Disclosure>
    </div>
  );
}

/**
 * Fit radar over the areas customers talk about (fit, fabric, colour…). For each area it plots the share of
 * the loudest complaint and the loudest praise - the largest single theme, never a sum (one review can raise
 * several themes). Only areas the backend returned are drawn.
 */
function VoiceRadar({ insights }: { insights: VoiceInsights }) {
  const data = useMemo(() => {
    const groups = new Map<string, { label: string; neg: number; pos: number; total: number }>();
    for (const t of insights.themes) {
      const g = groups.get(t.group) ?? { label: t.groupLabel, neg: 0, pos: 0, total: 0 };
      if (t.polarity === "negative") g.neg = Math.max(g.neg, t.share);
      if (t.polarity === "positive") g.pos = Math.max(g.pos, t.share);
      g.total = Math.max(g.total, t.share);
      groups.set(t.group, g);
    }
    return [...groups.values()].sort((a, b) => b.total - a.total).slice(0, 8);
  }, [insights.themes]);

  if (data.length < 3) return null;
  const max = Math.max(5, Math.ceil(Math.max(...data.map((d) => Math.max(d.neg, d.pos))) / 5) * 5);
  return (
    <Card pad="md" className="flex flex-col">
      <Eyebrow>By area</Eyebrow>
      <p className="mt-1 text-micro text-fg-faint">Share of {insights.noun} raising the loudest complaint and praise per area</p>
      <div className="flex flex-1 items-center justify-center py-4">
        <Radar
          label={`Customer voice by area, share of ${insights.noun}`}
          axes={data.map((d) => d.label)}
          max={max}
          format={pct}
          size={420}
          series={[
            { name: "Loudest complaint", values: data.map((d) => d.neg) },
            { name: "Loudest praise", values: data.map((d) => d.pos), dashed: true, tone: "accent" },
          ]}
        />
      </div>
      <p className="text-center text-micro text-fg-faint">Scale 0–{max}% · values under each area are complaints</p>
    </Card>
  );
}

function ThemeList({ insights }: { insights: VoiceInsights }) {
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const themes = all ? insights.themes : insights.themes.slice(0, 8);
  const max = Math.max(...insights.themes.map((t) => t.share), 1);
  return (
    <Card pad="md">
      <div className="flex items-baseline justify-between gap-4">
        <Eyebrow>What they say</Eyebrow>
        <Label>share of {insights.noun}</Label>
      </div>
      <ol className="mt-3 divide-y divide-line">
        {themes.map((t, i) => {
          const isOpen = open === t.id;
          const pol = POLARITY[t.polarity];
          return (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : t.id)}
                aria-expanded={isOpen}
                className="group grid w-full grid-cols-[1.75rem_minmax(0,1fr)_auto_1.75rem] items-center gap-x-3 py-3.5 text-left"
              >
                <span className="font-mono text-micro text-fg-faint tabular">{String(i + 1).padStart(2, "0")}</span>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-body text-fg">{t.name}</span>
                    <Badge tone={pol.tone}>{pol.label}</Badge>
                    <span className="text-micro text-fg-faint">{t.groupLabel}</span>
                  </span>
                  <ProgressBar value={t.share / max} tone={pol.tone} size="sm" className="mt-2.5" />
                </span>
                <span className="text-right font-mono text-small text-fg tabular">
                  {t.share.toFixed(1)}%
                  <span className="block text-micro text-fg-faint">
                    {t.count} {t.count === 1 ? "mention" : "mentions"}
                  </span>
                </span>
                <span
                  aria-hidden
                  className={cx(
                    "grid size-7 place-items-center rounded-full bg-paper-2 text-fg-muted transition-transform duration-300 ease-thread group-hover:text-fg",
                    isOpen && "rotate-180",
                  )}
                >
                  <IconChevronDown size={14} />
                </span>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: DUR.ui, ease: EASE }}
                    className="overflow-hidden"
                  >
                    <ThemeDetail theme={t} />
                  </motion.div>
                )}
              </AnimatePresence>
            </li>
          );
        })}
      </ol>
      {insights.themes.length > 8 && (
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${insights.themes.length} themes`}
        </Button>
      )}
    </Card>
  );
}

function ThemeDetail({ theme }: { theme: VoiceTheme }) {
  return (
    <div className="pb-5 sm:pl-[2.5rem]">
      <p className="font-mono text-micro text-fg-muted">
        {theme.negativeCount} negative · {theme.positiveCount} positive
        {theme.neutralCount > 0 && ` · ${theme.neutralCount} unrated`}
        {theme.avgRating != null && (
          <>
            {" · avg "}
            <span className="whitespace-nowrap">
              {theme.avgRating.toFixed(1)}
              <GlyphStar />
            </span>
          </>
        )}
        {theme.returnedCount > 0 && theme.id !== "returns.returned" && ` · ${theme.returnedCount} also returned`}
      </p>
      {theme.byClass.length > 0 && (
        <p className="mt-1 font-mono text-micro text-fg-faint">
          {theme.byClass.map((c) => `${c.garmentClass} ${c.count}/${c.total}`).join(" · ")}
        </p>
      )}
      <ul className="mt-3 flex flex-col gap-2">
        {theme.quotes.map((q) => (
          <li key={q.recordId}>
            <Quote quote={q} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A real customer quote as an evidence card: the matched phrase highlighted, the record id and rating beneath. The
 * quote stays word for word (stars a customer typed included); only the rating row is drawn with glyphs.
 */
export function Quote({ quote, compact }: { quote: VoiceQuote; compact?: boolean }) {
  const { text, matchStart: a, matchEnd: b } = quote;
  const body =
    a != null && b != null && b > a ? (
      <>
        {text.slice(0, a)}
        <mark className="rounded-sm bg-paper-2 px-0.5 font-medium text-fg">{text.slice(a, b)}</mark>
        {text.slice(b)}
      </>
    ) : (
      text
    );
  const r = quote.rating != null ? Math.round(quote.rating) : null;
  return (
    <figure className={cx("rounded-panel bg-paper-2", compact ? "px-3 py-2.5" : "px-4 py-3")}>
      <blockquote className={cx("text-fg", compact ? "text-small" : "text-body")}>
        “{quote.truncated && "…"}
        {body}
        {quote.truncated && "…"}”
      </blockquote>
      <figcaption className="mt-1.5 flex flex-wrap items-center gap-x-2 font-mono text-micro text-fg-faint">
        <span>{quote.recordId}</span>
        {r != null && <GlyphRating value={r} className="text-fg-muted" />}
        {quote.garmentClass && <span>{quote.garmentClass}</span>}
        {quote.field !== "text" && <span>{quote.field}</span>}
      </figcaption>
    </figure>
  );
}

// --------------------------------------------------------------------------- changes

const CONFIDENCE: Record<RecommendedChange["confidence"], Tone | "faint"> = {
  high: "accent",
  medium: "neutral",
  low: "faint",
};

function ChangeList({ insights }: { insights: VoiceInsights }) {
  const selected = useVoice((s) => s.selected);
  const toggle = useVoice((s) => s.toggle);
  const [all, setAll] = useState(false);
  const changes = insights.recommendedChanges;
  const shown = all ? changes : changes.filter((c, i) => i < 4 || selected.includes(c.id));
  return (
    <div className="mt-8">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>What to change</Eyebrow>
          <p className="mt-2 text-title text-fg">Tech pack changes the evidence supports</p>
        </div>
        <Label>{selected.length} selected</Label>
      </div>
      {changes.length === 0 ? (
        <Card variant="muted" pad="md">
          <p className="text-small text-fg-muted">
            No problem theme reaches the evidence bar (3+ {insights.noun} and 1.5% of the data), so nothing to change
            yet.
          </p>
        </Card>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {shown.map((c) => (
            <ChangeCard
              key={c.id}
              change={c}
              selected={selected.includes(c.id)}
              onToggle={() => toggle(c.id)}
              conflictTitle={changes.find((o) => c.conflictsWith.includes(o.id))?.title}
            />
          ))}
        </ul>
      )}
      {shown.length < changes.length || all ? (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${changes.length} changes`}
        </Button>
      ) : null}
      {changes.length > 0 && <ApplyBar />}
    </div>
  );
}

function ChangeCard({
  change: c,
  selected,
  onToggle,
  conflictTitle,
}: {
  change: RecommendedChange;
  selected: boolean;
  onToggle: () => void;
  conflictTitle?: string;
}) {
  const [quotes, setQuotes] = useState(false);
  const ev = c.evidence;
  return (
    <li
      className={cx(
        "rounded-card border bg-surface p-5 shadow-e1 transition-[border-color,box-shadow] duration-300 sm:p-6",
        selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-bold",
      )}
    >
      <div className="flex items-start gap-4">
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          onClick={onToggle}
          aria-label={`${selected ? "Deselect" : "Select"}: ${c.title}`}
          data-demo={`voice-change-${c.id}`}
          className={cx(
            "mt-0.5 grid size-6 shrink-0 place-items-center rounded-md border-[1.5px] transition-colors",
            selected ? "border-accent bg-accent text-on-accent" : "border-line-bold text-transparent hover:border-fg",
          )}
        >
          <IconCheck size={14} strokeWidth={2.6} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <button type="button" onClick={onToggle} className="text-left text-title text-fg hover:text-fg-muted">
              {c.title}
            </button>
            <span className="font-mono text-small text-fg tabular" title={`${ev.count} of ${ev.base} ${ev.garmentClass ?? ""}`.trim()}>
              {ev.count}
              <span className="text-fg-faint"> / {ev.base}</span>
            </span>
          </div>
          <p className="mt-2 text-small text-fg-muted">{c.action}</p>
          {c.pointsOfMeasure.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Points of measure">
              {c.pointsOfMeasure.map((p) => (
                <li key={p} className="max-w-full">
                  <Chip size="sm" variant="soft" className="font-mono">
                    {p}
                  </Chip>
                </li>
              ))}
            </ul>
          )}
          {c.instruction && (
            <div className="mt-4 rounded-r-panel border-l-2 border-fg bg-paper-2 py-2.5 pr-3 pl-3.5">
              <p className="text-small text-fg">
                <GlyphText text={c.instruction} />
              </p>
              <p className="mt-1 font-mono text-micro text-fg-faint">drafted by {c.instructionBy ?? "the brain"}</p>
            </div>
          )}

          <p className="mt-3 text-micro text-fg-faint">
            <GlyphText text={`${ev.summary}.`} />
          </p>
          {c.rationale && (
            <p className="mt-1 text-small text-fg-muted">
              <GlyphText text={c.rationale} />
            </p>
          )}
          {conflictTitle && <p className="mt-2 text-micro font-medium text-bad">Contradicts “{conflictTitle}”: apply only one.</p>}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge tone={CONFIDENCE[c.confidence]}>{c.confidence} confidence</Badge>
            <Chip size="sm">{c.area}</Chip>
            {ev.quotes.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setQuotes(!quotes)}
                aria-expanded={quotes}
                className="ml-auto"
                trailing={<IconChevronDown size={14} className={cx("transition-transform", quotes && "rotate-180")} />}
              >
                {quotes ? "Hide" : "Read"} {ev.quotes.length} quote{ev.quotes.length > 1 ? "s" : ""}
              </Button>
            )}
          </div>
          <AnimatePresence initial={false}>
            {quotes && (
              <motion.ul
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: DUR.ui, ease: EASE }}
                className="flex flex-col gap-2 overflow-hidden pt-3"
              >
                {ev.quotes.map((q) => (
                  <li key={q.recordId}>
                    <Quote quote={q} compact />
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>
      </div>
    </li>
  );
}

function ApplyBar() {
  const trend = useAtelier((s) => s.trend);
  const run = useAtelier((s) => s.run);
  const selected = useVoice((s) => s.selected);
  const apply = useVoice((s) => s.apply);
  const applyTo = useVoice((s) => s.applyTo);
  const auth = useAdminAuth();
  const visitor = !!auth?.required && !auth.signedIn; // hosted demo: applying changes the design an admin approves

  // Pending or already-applied selections follow the trend: a newly read trend gets them too.
  const trendId = trend?.id;
  useEffect(() => {
    if (!trendId) return;
    const st = useVoice.getState().apply;
    if ((st.pending || (st.status === "done" && st.trendId !== trendId)) && st.status !== "loading") {
      void useVoice.getState().applyTo(trendId);
    }
  }, [trendId]);

  const n = selected.length;
  const done = apply.status === "done" && apply.trendId === trendId;
  let note: string;
  if (apply.status === "error") note = apply.error ?? "Couldn't apply the changes.";
  else if (apply.pending) note = "Queued: they attach to the design as soon as you read a trend.";
  else if (done && apply.applied.length === 0) note = "Cleared: the next tech pack carries no customer evidence.";
  else if (done)
    note = run
      ? "Applied. The tech pack already in production is unchanged; the next approval carries them."
      : `Applied to every concept from “${trend?.trendName}”. They're written into the tech pack when you approve.`;
  else note = trend ? "Every concept from this trend inherits the selected changes." : "Read a trend and they attach to its concepts.";

  return (
    <div className="sticky bottom-4 z-20 mt-6 flex flex-col gap-3 rounded-card border border-line bg-surface/95 p-3 pl-5 shadow-e3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
      <p
        className={cx(
          "flex items-center gap-2 text-small",
          apply.status === "error" ? "text-bad" : done ? "text-ok" : "text-fg-muted",
        )}
        aria-live="polite"
      >
        {done && <IconCheck size={15} strokeWidth={2.4} className="shrink-0" />}
        {note}
      </p>
      <Button
        variant="accent"
        onClick={() => applyTo(trendId)}
        loading={apply.status === "loading"}
        disabled={visitor || done || (n === 0 && !(apply.status === "done" || apply.trendId))}
        title={visitor ? "Applying changes the design that gets approved, so it needs the admin token" : undefined}
        className="shrink-0"
        data-demo="voice-apply"
      >
        {visitor ? "Apply (admin)" : done ? `${apply.applied.length} applied` : n === 0 ? "Clear from design" : `Apply ${n} to design`}
      </Button>
    </div>
  );
}
