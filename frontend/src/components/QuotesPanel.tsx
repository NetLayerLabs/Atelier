"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  buttonClass,
  Card,
  cx,
  DUR,
  EASE,
  EmptyState,
  FileDrop,
  Eyebrow,
  GarmentTag,
  GlyphText,
  IconArrowUpRight,
  IconDocument,
  IconMail,
  InlineAlert,
  Label,
  ProgressBar,
  Select,
  Skeleton,
  Stat,
  Table,
  TapeMeasure,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  type Tone,
} from "@/components/ds";
import {
  assignUnmatchedQuote,
  chooseSupplier,
  closeQuoteRound,
  confirmQuote,
  getUnmatchedQuotes,
  errorHint,
  errorMessage,
  resolveAssetUrl,
  uploadQuote,
  type GuardrailReport,
  type PipelineRun,
  type QuoteEvaluation,
  type SupplierQuote,
  type UnmatchedQuote,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { Citations } from "./Citations";
import { RouteTag } from "./Inference";
import { int, money, NOT_STATED, pct, runCurrency, SheetHeading } from "./Sheet";

const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp";

/** The unit-cost limit the quotes are read against: the cost cap, or the margin floor at retail - the lower one. */
function unitLimit(report: GuardrailReport | undefined, retail: number): { value: number; label: string } | null {
  if (!report) return null;
  const caps: { value: number; label: string }[] = [];
  const g = report.guardrails;
  if (g.maxUnitCost)
    caps.push({ value: g.maxUnitCost, label: report.maxUnitCostDerived ? "auto cost cap" : "cost cap" });
  if (g.minGrossMarginPct != null && retail > 0)
    caps.push({ value: retail * (1 - g.minGrossMarginPct / 100), label: `${g.minGrossMarginPct}% margin floor` });
  if (!caps.length) return null;
  return caps.reduce((a, b) => (b.value < a.value ? b : a));
}

/** A round tick step giving about `n` numbered ticks (keeps narrow tapes legible). */
function niceStep(max: number, n: number): number {
  const raw = max / n;
  const p = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}

function niceMax(v: number): number {
  if (!(v > 0)) return 10;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

export function QuotesPanel({ run }: { run: PipelineRun }) {
  const updateRun = useAtelier((s) => s.updateRun);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | undefined>();
  const fail = (err: unknown, prefix = "") => {
    setError(`${prefix}${errorMessage(err)}`);
    setHint(errorHint(err));
  };

  const quotes = run.quotes ?? [];
  const rec = run.recommendation;
  const round = run.quoteRound;
  const step = run.steps.find((s) => s.key === "supplier_quotes");
  const quantity = run.techPack?.productionQuantity ?? 0;
  const locked = !!run.demand?.purchaseOrder;
  const emails = run.supplierEmails ?? [];
  const awaiting = emails.filter((e) => !quotes.some((q) => q.supplierName === e.supplierName));
  const prices = quotes.map((q) => q.unitPrice).filter((p): p is number => p != null);
  const cheapest = prices.length ? Math.min(...prices) : 0;
  const selected = rec?.selectedSupplierName;
  const brandCurrency = runCurrency(run);
  const waiting = round?.status === "awaiting";

  const choose = async (name: string) => {
    if (!rec || locked || name === selected) return;
    setPending(name);
    setError(null);
    try {
      updateRun(await chooseSupplier(run.id, name));
    } catch (err) {
      fail(err);
    } finally {
      setPending(null);
    }
  };

  // QA M10: a person checked the document and confirms the numbers the extractor read that weren't in its text.
  const confirm = async (name: string) => {
    setPending(`__confirm:${name}`);
    setError(null);
    try {
      updateRun(await confirmQuote(run.id, name));
    } catch (err) {
      fail(err);
    } finally {
      setPending(null);
    }
  };

  const closeRound = async () => {
    setPending("__close");
    setError(null);
    try {
      updateRun(await closeQuoteRound(run.id));
    } catch (err) {
      fail(err);
    } finally {
      setPending(null);
    }
  };

  const retail = run.techPack?.targetRetailPrice ?? 0;
  const expected = round?.expected ?? quotes.length + awaiting.length;
  const received = round?.received ?? quotes.length;
  const title = waiting
    ? `Awaiting replies - ${received} of ${expected} received`
    : !rec
      ? `${quotes.length} of ${expected} quotes in`
      : rec.overridden
        ? `Your pick: ${rec.selectedSupplierName}`
        : `Agent recommends ${rec.supplierName}`;

  const limit = unitLimit(run.guardrailReport, retail);
  const scaleMax = niceMax(Math.max(...prices, limit?.value ?? 0, 1) * 1.15);
  const breach = run.guardrailReport?.selectedOk === false;

  return (
    <Card as="section" pad="lg">
      <SheetHeading
        kicker="Supplier quotes"
        tone={waiting ? "accent" : breach ? "bad" : rec ? "ok" : "neutral"}
        live={waiting}
        title={title}
        aside={
          <>
            {round && <GarmentTag code={round.rfqRef}>Ref</GarmentTag>}
            {quotes.length > 0 && (
              <span title="Every quote below was read from a supplier's own document">
                <Badge tone="ok">Read from quote documents</Badge>
              </span>
            )}
          </>
        }
      />

      {round && (
        <div className="mb-6 grid gap-4 rounded-panel bg-paper-2/60 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:p-5">
          <ProgressBar
            value={expected > 0 ? received / expected : null}
            label={
              round.status === "awaiting"
                ? "Round open - waiting for the mills"
                : round.status === "closed"
                  ? "Round closed - recommending from the quotes in hand"
                  : "Round complete - every mill replied"
            }
            detail={`${received} of ${expected} replies`}
            tone={round.status === "complete" ? "ok" : "accent"}
          />
          <div className="flex flex-wrap gap-1.5 sm:justify-end">
            {round.awaiting.map((n) => (
              <Badge key={n} tone="faint">
                {n}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {round && !locked && <UnmatchedQuotes runId={run.id} onAssigned={updateRun} onError={fail} />}

      {round && !locked && (
        <QuoteDropzone
          runId={run.id}
          suppliers={emails.map((e) => e.supplierName)}
          defaultSupplier={awaiting[0]?.supplierName}
          onDone={updateRun}
          onError={(err, prefix) => {
            if (err == null) {
              setError(null);
              setHint(undefined);
            } else fail(err, prefix);
          }}
          waiting={waiting}
          canClose={waiting && quotes.length > 0}
          closing={pending === "__close"}
          onClose={closeRound}
        />
      )}

      {error && (
        <InlineAlert tone="bad" title="That didn't go through" hint={hint} className="mb-6">
          {error}
        </InlineAlert>
      )}

      {quotes.length === 0 && awaiting.length === 0 ? (
        <EmptyState compact icon={<IconMail size={18} />} title="No replies yet">
          Quotes appear here as the mills answer - uploaded above, or by email with the RFQ reference.
        </EmptyState>
      ) : (
        <>
          <Table className="hidden md:block" caption="Supplier quotes">
            <THead>
              <Tr>
                <Th className="min-w-[15rem]">Mill</Th>
                <Th className="min-w-[12.5rem]">
                  Unit cost
                  {limit && <span className="ml-1 normal-case">· limit {money(limit.value, brandCurrency)}</span>}
                </Th>
                <Th numeric>MOQ</Th>
                <Th numeric>Lead</Th>
                <Th numeric>Sample</Th>
                <Th className="min-w-[7rem]">Score</Th>
                <Th>
                  <span className="sr-only">Choose</span>
                </Th>
              </Tr>
            </THead>
            <TBody>
              {quotes.map((q) => (
                <QuoteRow
                  key={q.supplierName}
                  q={q}
                  evaluation={run.guardrailReport?.evaluations.find((e) => e.supplierName === q.supplierName)}
                  quantity={quantity}
                  retail={retail}
                  cheapest={cheapest}
                  brandCurrency={brandCurrency}
                  scaleMax={scaleMax}
                  limit={limit}
                  isAgentPick={rec?.supplierName === q.supplierName}
                  isSelected={selected === q.supplierName}
                  canChoose={!!rec && !locked}
                  busy={pending === q.supplierName}
                  onChoose={() => choose(q.supplierName)}
                  canConfirm={!locked}
                  confirming={pending === `__confirm:${q.supplierName}`}
                  onConfirm={() => confirm(q.supplierName)}
                />
              ))}
              {awaiting.map((e) => (
                <Tr key={`wait-${e.supplierName}`} muted>
                  <Td>
                    <p className="text-body text-fg-muted">{e.supplierName}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-micro text-fg-faint">
                      {step?.status === "running" ? (
                        <>
                          <Badge status="running">Awaiting reply</Badge>
                          <span className="break-all">RFQ sent to {e.toEmail}</span>
                        </>
                      ) : round?.status === "closed" ? (
                        <Badge tone="faint">No reply - round closed</Badge>
                      ) : (
                        <Badge status="pending">Waiting for RFQ</Badge>
                      )}
                    </div>
                  </Td>
                  <Td colSpan={6}>
                    {step?.status === "running" ? (
                      <Skeleton className="mt-2 h-3 w-full max-w-md rounded-full" />
                    ) : (
                      <span className="text-micro text-fg-faint">-</span>
                    )}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
          <ul className="flex flex-col gap-3 md:hidden" aria-label="Supplier quotes">
            {quotes.map((q) => (
              <QuoteRow
                layout="card"
                key={q.supplierName}
                q={q}
                evaluation={run.guardrailReport?.evaluations.find((e) => e.supplierName === q.supplierName)}
                quantity={quantity}
                retail={retail}
                cheapest={cheapest}
                brandCurrency={brandCurrency}
                scaleMax={scaleMax}
                limit={limit}
                isAgentPick={rec?.supplierName === q.supplierName}
                isSelected={selected === q.supplierName}
                canChoose={!!rec && !locked}
                busy={pending === q.supplierName}
                onChoose={() => choose(q.supplierName)}
                canConfirm={!locked}
                confirming={pending === `__confirm:${q.supplierName}`}
                onConfirm={() => confirm(q.supplierName)}
              />
            ))}
            {awaiting.map((e) => (
              <li key={`wait-${e.supplierName}`} className="rounded-panel border border-dashed border-line-strong p-4">
                <p className="text-body text-fg-muted">{e.supplierName}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-micro text-fg-faint">
                  {step?.status === "running" ? (
                    <>
                      <Badge status="running">Awaiting reply</Badge>
                      <span className="break-all">RFQ sent to {e.toEmail}</span>
                    </>
                  ) : round?.status === "closed" ? (
                    <Badge tone="faint">No reply - round closed</Badge>
                  ) : (
                    <Badge status="pending">Waiting for RFQ</Badge>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <AnimatePresence>
        {rec && (
          <motion.div
            key="rationale"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: DUR.reveal, ease: EASE }}
            className="mt-8 grid grid-cols-1 gap-6 rounded-panel border border-line p-5 sm:p-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)] lg:gap-10"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Eyebrow tone="accent">Why {rec.supplierName}</Eyebrow>
                <RouteTag route={rec.generatedBy} />
              </div>
              {rec.rationale ? (
                <p className="mt-3 text-title leading-snug font-light text-pretty text-fg">{rec.rationale}</p>
              ) : (
                <p className="mt-3 text-small text-fg-muted">
                  <span className="font-medium text-warn">Rationale unavailable</span>
                  {rec.rationaleError ? `: ${rec.rationaleError}` : "."} The pick is the deterministic weighted score of
                  the quotes; the scores are in the table.
                </p>
              )}
              {rec.overridden && (
                <p className="mt-4 text-small text-fg-muted">
                  You overrode the agent and chose{" "}
                  <span className="font-medium text-fg">{rec.selectedSupplierName}</span>
                  {run.demand ? ` - the pre-order threshold is now ${int(run.demand.threshold)} units.` : "."}
                </p>
              )}
              <Citations items={rec.citations} className="mt-5" />
            </div>
            <div className="min-w-0">
              <Label as="p">Scoring weights</Label>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {(
                  [
                    ["Price", rec.weights.price],
                    ["MOQ fit", rec.weights.moq],
                    ["Lead time", rec.weights.leadTime],
                  ] as const
                ).map(([k, w]) => (
                  <Stat key={k} size="sm" label={k} value={w == null ? "-" : pct(w)} />
                ))}
              </div>
              <p className="mt-3 text-micro text-fg-faint">
                From the Brand workspace; score = weighted sum of what each quote states.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {locked && (
        <InlineAlert
          tone="info"
          title={`PO ${run.demand?.purchaseOrder?.poNumber} drafted for ${run.demand?.purchaseOrder?.supplierName}`}
          className="mt-6"
        >
          Selection locked; quotes that arrive now are refused.
        </InlineAlert>
      )}
    </Card>
  );
}

function QuoteDropzone({
  runId,
  suppliers,
  defaultSupplier,
  onDone,
  onError,
  waiting,
  canClose,
  closing,
  onClose,
}: {
  runId: string;
  suppliers: string[];
  defaultSupplier?: string;
  onDone: (run: PipelineRun) => void;
  onError: (err: unknown, prefix?: string) => void;
  waiting: boolean;
  canClose: boolean;
  closing: boolean;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [supplier, setSupplier] = useState<string>("");

  const send = async (list: File[]) => {
    if (!list.length) return;
    onError(null);
    for (const f of list) {
      setBusy(f.name);
      try {
        onDone(await uploadQuote(runId, f, f.name, supplier || undefined));
      } catch (err) {
        onError(err, `${f.name}: `);
        break;
      }
    }
    setBusy(null);
    setSupplier("");
  };

  return (
    <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_16rem]" data-demo="quote-upload">
      <FileDrop
        layout="row"
        accept={ACCEPT}
        multiple
        busy={!!busy}
        onFiles={(files) => void send(files)}
        zoneLabel="Upload a supplier quote (PDF or image)"
        aria-label="Upload supplier quote"
        title={busy ? `Reading ${busy}…` : "Drop a supplier’s quote, or choose a file"}
        hint={
          <>
            PDF or image · read by the Evolus document extractor (or the AMD model when it isn&rsquo;t configured).
            Email replies arrive on their own through the Evolus inbound workflow.
          </>
        }
      />
      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-small font-medium text-fg">From mill</span>
          <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
            <option value="">Detect from document</option>
            {suppliers.map((s) => (
              <option key={s} value={s}>
                {s}
                {s === defaultSupplier ? " (next)" : ""}
              </option>
            ))}
          </Select>
        </label>
        {waiting && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            disabled={!canClose || closing}
            loading={closing}
            title={canClose ? "Recommend from the quotes in hand" : "Upload at least one quote first"}
          >
            Stop waiting &amp; recommend
          </Button>
        )}
      </div>
    </div>
  );
}

const LANG_NAME: Record<string, string> = { it: "Italian", pt: "Portuguese", en: "English" };
const FIELD_NAME: Record<string, string> = { unitPrice: "unit price", moq: "MOQ", leadTime: "lead time" };

function QuoteRow({
  layout = "row",
  q,
  evaluation,
  quantity,
  retail,
  cheapest,
  brandCurrency,
  scaleMax,
  limit,
  isAgentPick,
  isSelected,
  canChoose,
  busy,
  onChoose,
  canConfirm,
  confirming,
  onConfirm,
}: {
  /** row: a table row (md+); card: a stacked card (phones). */
  layout?: "row" | "card";
  q: SupplierQuote;
  brandCurrency?: string;
  /** v4: this quote against the brand guardrails. */
  evaluation?: QuoteEvaluation;
  quantity: number;
  retail: number;
  cheapest: number;
  scaleMax: number;
  limit: { value: number; label: string } | null;
  isAgentPick: boolean;
  isSelected: boolean;
  canChoose: boolean;
  busy: boolean;
  onChoose: () => void;
  canConfirm: boolean;
  confirming: boolean;
  onConfirm: () => void;
}) {
  const [showFields, setShowFields] = useState(false);
  const unverified = q.unverifiedFields ?? [];
  const over = q.moq != null && q.moq > quantity;
  const premium = cheapest > 0 && q.unitPrice != null ? q.unitPrice / cheapest - 1 : 0;
  const margin = retail > 0 && q.unitPrice != null ? (retail - q.unitPrice) / retail : null;
  const foreign = !!q.currency && q.currency !== brandCurrency;
  const sb = q.scoreBreakdown;
  const sc = (v: number | null) => (v == null ? "n/a" : v.toFixed(0));
  const src = q.source;
  const doc = src?.documentUrl ? resolveAssetUrl(src.documentUrl) : undefined;
  const tone: Tone = evaluation ? (evaluation.ok ? "ok" : "bad") : "accent";
  const priceUnverified = unverified.includes("unitPrice");
  const mill = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-body font-medium text-fg">{q.supplierName}</p>
        {isAgentPick && <GarmentTag tone="accent">Agent pick</GarmentTag>}
        {isSelected && !isAgentPick && <GarmentTag tone="ink">Your pick</GarmentTag>}
        {!!q.revision && (
          <span title={q.revises ? `Replaces ${q.revises}` : "Revised quote"}>
            <Badge tone="accent">Rev. {q.revision}</Badge>
          </span>
        )}
      </div>
      {evaluation && (
        <div
          className="mt-2"
          data-demo={evaluation.ok ? undefined : "guardrail-breach"}
          title={evaluation.checks.map((c) => c.message).join("\n")}
        >
          {evaluation.ok ? (
            <Badge tone="ok">Within guardrails</Badge>
          ) : (
            <span className="inline-flex max-w-full flex-wrap gap-1.5">
              {evaluation.checks
                .filter((c) => !c.ok)
                .map((c) => (
                  <Badge key={c.rule} tone="bad" className="border border-bad/40">
                    Breaks {c.label.toLowerCase()} · {c.actual} vs {c.limit}
                  </Badge>
                ))}
            </span>
          )}
        </div>
      )}
      <p className="mt-2 text-micro text-fg-faint">
        {q.region} · {q.paymentTerms ?? `payment terms ${NOT_STATED}`}
        {q.validUntil && ` · valid until ${q.validUntil}`}
      </p>
      {q.note && (
        <p lang={q.language ?? "en"} className="mt-2 max-w-md text-small leading-snug text-fg-muted">
          &ldquo;{q.note}&rdquo;
        </p>
      )}
      {q.note && q.language && q.language !== "en" && (
        <p className="mt-1 max-w-md text-micro leading-snug text-fg-muted">
          <Label className="mr-1 normal-case">
            {LANG_NAME[q.language] ?? q.language} → English
            {q.noteTranslation && q.noteTranslation !== "untranslated" && ` · ${q.noteTranslation}`}
          </Label>
          {q.noteEnglish ?? "Not translated - no model available and not a known phrase. The original is above."}
        </p>
      )}
      {src && (
        <div className="mt-3 flex max-w-md flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5 text-micro text-fg-faint">
            {doc ? (
              <a
                href={doc}
                target="_blank"
                rel="noreferrer"
                title={src.filename ?? "Source document"}
                className={buttonClass({ variant: "secondary", size: "sm", className: "h-7 gap-1 px-2.5 text-micro" })}
              >
                <IconDocument size={12} />
                {src.contentType?.startsWith("image/") ? "Image" : "PDF"}
                <IconArrowUpRight size={12} />
              </a>
            ) : (
              <Badge tone="faint">{src.channel === "email" ? "email" : "document"}</Badge>
            )}
            {q.quoteNumber && <span className="font-mono text-fg-muted">{q.quoteNumber}</span>}
            <span>· {src.channel === "email" ? `email${src.sender ? ` from ${src.sender}` : ""}` : "uploaded"}</span>
            <span>· {src.engineLabel}</span>
            {q.language && q.language !== "en" && <span>· written in {LANG_NAME[q.language] ?? q.language}</span>}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {src.confidence != null && (
              <Badge tone={src.confidence >= 0.8 ? "ok" : "warn"}>
                {pct(src.confidence)}{" "}
                {src.fields.some((f) => f.confidence != null) ? "confidence" : "of required fields"}
              </Badge>
            )}
            {!!q.duplicates && (
              <span title="Identical copies (webhook replay / re-upload) were ignored">
                <Badge tone="faint">Received again ×{q.duplicates} · ignored</Badge>
              </span>
            )}
            {q.confirmedBy && <Badge tone="ok">Numbers confirmed by {q.confirmedBy}</Badge>}
            {unverified.length > 0 && <Badge status="unverified">{unverified.length} unverified</Badge>}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2.5 text-micro"
              onClick={() => setShowFields((v) => !v)}
              aria-expanded={showFields}
            >
              {showFields ? "Hide fields" : `${src.fields.length} fields read`}
            </Button>
          </div>
          {showFields && (
            <ul className="flex flex-col rounded-panel bg-paper-2/70 px-3 py-2 text-micro">
              {src.fields.map((f) => (
                <li
                  key={f.name}
                  className="grid grid-cols-[7rem_minmax(0,1fr)] items-start gap-x-3 border-t border-line py-1.5 first:border-t-0"
                >
                  <span className="font-mono text-fg-faint">{f.name}</span>
                  <span className="flex min-w-0 flex-wrap items-center gap-1.5 break-words text-fg">
                    <span className="font-mono">{f.value}</span>
                    {f.confidence != null && <span className="text-fg-faint">{pct(f.confidence)}</span>}
                    {f.verified === true && <Badge tone="ok">in the document</Badge>}
                    {f.verified === false && <Badge status="unverified">not in the text</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {src.warnings.length > 0 && (
            <p className="text-micro text-warn">
              <GlyphText text={src.warnings.join(" · ")} />
            </p>
          )}
          {unverified.length > 0 && (
            <InlineAlert
              tone="warn"
              title="Check the document"
              className="p-3 sm:p-4"
              action={
                canConfirm ? (
                  <Button size="sm" variant="secondary" onClick={onConfirm} loading={confirming}>
                    {confirming ? "Confirming…" : "I checked the document - confirm"}
                  </Button>
                ) : undefined
              }
            >
              The {unverified.map((f) => FIELD_NAME[f] ?? f).join(", ")} read from it{" "}
              {unverified.length > 1 ? "are" : "is"} not printed in its text.
              {priceUnverified && " The agent won't pick this price on its own."}
            </InlineAlert>
          )}
        </div>
      )}
    </>
  );
  const cost = (
    <>
      {q.unitPrice != null ? (
        <>
          <TapeMeasure
            label={`${q.supplierName} unit cost`}
            min={0}
            max={scaleMax}
            value={q.unitPrice}
            format={(n) => money(n, brandCurrency, 0)}
            readout={money(q.unitPrice, brandCurrency)}
            tone={tone}
            target={limit ? { from: 0, to: limit.value } : undefined}
            majorStep={niceStep(scaleMax, 3)}
            className="min-w-[12rem]"
          />
          <p className="mt-1 font-mono text-micro text-fg-faint">
            {premium < 0.005 ? "lowest" : `+${(premium * 100).toFixed(0)}% vs lowest`}
            {margin != null && ` · ${pct(margin)} margin`}
            {evaluation?.marginPct != null && margin == null && ` · ${evaluation.marginPct.toFixed(0)}% margin`}
          </p>
          {foreign && q.unitPriceQuoted != null && (
            <p className="mt-0.5 font-mono text-micro text-fg-faint">
              quoted {money(q.unitPriceQuoted, q.currency)}
              {q.fxRate != null &&
                ` · ECB ${q.fxDate ?? "latest"} · 1 ${q.currency} = ${q.fxRate.toFixed(4)} ${brandCurrency}`}
            </p>
          )}
          {priceUnverified && (
            <p className="mt-1">
              <Badge status="unverified">price not in the text</Badge>
            </p>
          )}
        </>
      ) : q.unitPriceQuoted != null && q.currency ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-small text-fg">{money(q.unitPriceQuoted, q.currency)}</span>
          <Badge tone="warn">
            Not converted - no {q.currency}→{brandCurrency} rate
          </Badge>
        </div>
      ) : (
        <span className="text-small text-fg-faint">- {NOT_STATED}</span>
      )}
    </>
  );
  const moq = (
    <>
      {q.moq != null ? (
        <>
          <span className={over ? "text-bad" : "text-fg"}>{int(q.moq)}</span>
          <span className={cx("block text-micro", over ? "text-bad" : "text-fg-faint")}>
            {over ? `+${int(q.moq - quantity)} over run` : "fits run"}
          </span>
        </>
      ) : (
        <span className="text-fg-faint">{NOT_STATED}</span>
      )}
    </>
  );
  const lead = (
    <>{q.leadTimeWeeks != null ? `${q.leadTimeWeeks} wks` : <span className="text-fg-faint">{NOT_STATED}</span>}</>
  );
  const sample = (
    <>
      {q.sampleCost != null ? (
        money(q.sampleCost, brandCurrency, 0)
      ) : q.sampleCostQuoted != null && q.currency ? (
        <>
          {money(q.sampleCostQuoted, q.currency, 0)}
          <span className="block text-micro text-warn">not converted</span>
        </>
      ) : (
        <span className="text-fg-faint">{NOT_STATED}</span>
      )}
    </>
  );
  const score = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <span className="tabular text-[1.4rem] leading-none font-light tracking-[-0.03em] text-fg">
          {q.score.toFixed(0)}
        </span>
        <span className="text-micro text-fg-faint">/ 100</span>
      </div>
      <ProgressBar className="mt-2" size="sm" value={q.score / 100} tone={isAgentPick ? "accent" : "neutral"} />
      <p
        className="mt-1.5 font-mono text-micro whitespace-nowrap text-fg-faint"
        title="Price · MOQ fit · Lead time sub-scores"
      >
        P {sc(sb.price)} · M {sc(sb.moq)} · L {sc(sb.leadTime)}
      </p>
    </>
  );
  const choose = (
    <>
      {isSelected ? (
        <Badge tone="accent">Selected</Badge>
      ) : (
        <Button size="sm" variant="secondary" onClick={onChoose} disabled={!canChoose || busy} loading={busy}>
          Choose
        </Button>
      )}
    </>
  );
  if (layout === "row")
    return (
      <Tr selected={isSelected}>
        <Td>{mill}</Td>
        <Td>{cost}</Td>
        <Td numeric>{moq}</Td>
        <Td numeric>{lead}</Td>
        <Td numeric>{sample}</Td>
        <Td>{score}</Td>
        <Td className="text-right">{choose}</Td>
      </Tr>
    );
  return (
    <li
      className={cx(
        "rounded-panel border p-4",
        isSelected ? "border-accent/40 bg-accent-soft" : "border-line bg-surface",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">{mill}</div>
      </div>
      <div className="mt-4">{cost}</div>
      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-3 text-small">
        <div>
          <dt>
            <Label>MOQ</Label>
          </dt>
          <dd className="mt-1 font-mono text-[0.78rem]">{moq}</dd>
        </div>
        <div>
          <dt>
            <Label>Lead</Label>
          </dt>
          <dd className="mt-1 font-mono text-[0.78rem]">{lead}</dd>
        </div>
        <div>
          <dt>
            <Label>Sample</Label>
          </dt>
          <dd className="mt-1 font-mono text-[0.78rem]">{sample}</dd>
        </div>
      </dl>
      <div className="mt-4 flex items-end justify-between gap-4 border-t border-line pt-3">
        <div className="min-w-0 flex-1">{score}</div>
        <div className="shrink-0">{choose}</div>
      </div>
    </li>
  );
}

/** LOW: inbound (email) quotes that matched no run - a person assigns them (they are never guessed). */
function UnmatchedQuotes({
  runId,
  onAssigned,
  onError,
}: {
  runId: string;
  onAssigned: (run: PipelineRun) => void;
  onError: (err: unknown) => void;
}) {
  const [items, setItems] = useState<UnmatchedQuote[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getUnmatchedQuotes()
        .then((x) => alive && setItems(x))
        .catch(() => undefined); // not signed in / offline: nothing to show
    void load();
    const t = setInterval(load, 15_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [runId]);

  if (!items.length) return null;
  const assign = async (id: string) => {
    setBusy(id);
    try {
      onAssigned(await assignUnmatchedQuote(id, runId));
      setItems((xs) => xs.filter((x) => x.id !== id));
    } catch (err) {
      onError(err);
    } finally {
      setBusy(null);
    }
  };
  return (
    <InlineAlert
      tone="warn"
      title={`${items.length} unmatched inbound quote${items.length === 1 ? "" : "s"}`}
      className="mb-6"
    >
      These emailed quotes carried no RFQ reference and came from an unknown sender (or several runs could match), so
      none was attached automatically.
      <ul className="mt-3 flex flex-col">
        {items.map((x) => (
          <li
            key={x.id}
            className="flex flex-wrap items-center justify-between gap-2 border-t border-line py-2 first:border-t-0"
          >
            <span className="min-w-0 break-words text-fg">
              {x.supplierName ?? "Unknown mill"}
              {x.quoteNumber && <span className="font-mono text-micro"> · {x.quoteNumber}</span>}
              {x.sender && <span className="text-micro text-fg-faint"> · from {x.sender}</span>}
              <span className="text-micro text-fg-faint"> · {new Date(x.receivedAt).toLocaleString()}</span>
            </span>
            <Button size="sm" variant="secondary" onClick={() => assign(x.id)} loading={busy === x.id}>
              {busy === x.id ? "Assigning…" : "Assign to this run"}
            </Button>
          </li>
        ))}
      </ul>
    </InlineAlert>
  );
}
