"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  buttonClass,
  Card,
  cx,
  Disclosure,
  DUR,
  EASE,
  Eyebrow,
  GarmentTag,
  IconArrowUpRight,
  IconMail,
  IconRefresh,
  InlineAlert,
  Label,
  ProgressBar,
  Timeline,
  type StepStatus,
  type TimelineItem,
} from "@/components/ds";
import {
  getGuardrails,
  type Guardrails,
  type PipelineRun,
  type PipelineStep,
  type ShopifyProduct,
  type SupplierEmail,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { RouteTag, StepTelemetry } from "./Inference";
import { AuditTrail, DecisionPanel } from "./DecisionPanel";
import { DemandTracker } from "./DemandTracker";
import { ForecastPanel } from "./ForecastPanel";
import { GuardrailsPanel } from "./GuardrailsPanel";
import { QuotesPanel } from "./QuotesPanel";
import { money, SheetHeading } from "./Sheet";
import { TechPackEditor } from "./TechPackEditor";
import { SmartImage } from "./ui";

const STEP_PLACEHOLDERS: Pick<PipelineStep, "key" | "label">[] = [
  { key: "techpack", label: "Tech Pack" },
  { key: "supplier_outreach", label: "Supplier outreach" },
  { key: "supplier_quotes", label: "Quotes & recommendation" },
  { key: "shopify_preorder", label: "Shopify pre-order" },
  { key: "preorder_demand", label: "Demand validation" },
];

const STEP_BLURB: Record<string, string> = {
  techpack:
    "The connected brain (Evolus agent or AMD vLLM) drafts the BOM, measurements & construction from the brand book",
  supplier_outreach: "RFQs are drafted per mill and sent through the Evolus outreach workflow",
  supplier_quotes: "Mills reply with quote documents; each is extracted, checked against the guardrails and scored",
  shopify_preorder: "Opens a real Shopify pre-order (Evolus workflow or Admin API)",
  preorder_demand: "Real Shopify pre-orders must clear the threshold before a PO is drafted",
};

const SERVICE_NAME: Record<string, string> = {
  brain: "the brain (Evolus agent / AMD vLLM)",
  llm: "AMD vLLM",
  vision: "the vision model",
  diffusion: "the diffusion model",
  evolus_agent: "the Evolus agent",
  evolus_outreach: "Evolus outreach",
  evolus_negotiation: "Evolus outreach",
  evolus_po: "the Evolus PO workflow",
  evolus_shopify: "the Evolus Shopify workflow",
  evolus_extractor: "the Evolus extractor",
  shopify: "Shopify",
};

export function serviceName(service?: string): string | undefined {
  if (!service) return undefined;
  return SERVICE_NAME[service] ?? service.replace(/[_-]+/g, " ");
}

function duration(step: PipelineStep): string | undefined {
  if (!step.startedAt) return;
  const start = Date.parse(step.startedAt);
  const end = step.finishedAt ? Date.parse(step.finishedAt) : NaN;
  if (Number.isNaN(start) || Number.isNaN(end)) return;
  return `${Math.max(0, (end - start) / 1000).toFixed(1)}s`;
}

export function PipelineStage() {
  const approve = useAtelier((s) => s.approve);
  const run = useAtelier((s) => s.run);
  const poll = useAtelier((s) => s.poll);
  const designs = useAtelier((s) => s.designs);
  const labels = useAtelier((s) => s.labels);
  const resumePolling = useAtelier((s) => s.resumePolling);
  const runApprove = useAtelier((s) => s.runApprove);
  const retry = useAtelier((s) => s.retry);
  const retryRun = useAtelier((s) => s.retryRun);

  // The brand's saved guardrails (Brand workspace): shown above the pipeline and used by the tech pack costing.
  const [guardrails, setGuardrails] = useState<Guardrails | null>(null);
  useEffect(() => {
    let live = true;
    getGuardrails()
      .then((v) => live && setGuardrails(v))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const steps: PipelineStep[] = run?.steps ?? STEP_PLACEHOLDERS.map((s) => ({ ...s, status: "pending", log: [] }));
  const design = run ? designs[run.designId] : undefined;

  const demandRunning = run?.steps.some((s) => s.key === "preorder_demand" && s.status === "running");
  const awaitingHuman = !!run?.decision && run.decision.status !== "resolved";
  const headline =
    !run || run.status === "running"
      ? awaitingHuman
        ? "Waiting for your decision"
        : demandRunning
          ? "Collecting pre-orders"
          : "The agents are at work"
      : run.status === "completed"
        ? run.demand?.purchaseOrder
          ? "In production"
          : run.demand?.status === "expired"
            ? "Demand fell short"
            : "Ready for market"
        : "The run stopped short";
  const failedStep = run?.steps.find((s) => s.status === "error");
  const done = steps.filter((s) => s.status === "done").length;
  const stateTone = !run
    ? "faint"
    : run.status === "failed"
      ? "bad"
      : awaitingHuman
        ? "warn"
        : run.status === "completed"
          ? "ok"
          : "accent";
  const quantity = run?.techPack?.productionQuantity ?? approve.quantity;

  return (
    <div className="flex flex-col gap-4">
      {/* Run status */}
      <Card pad="md" className="overflow-hidden">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <Eyebrow tone={stateTone} live={run?.status === "running" && !awaitingHuman}>
              Run status
            </Eyebrow>
            <p className="mt-3 text-display-m text-fg" aria-live="polite">
              {headline}
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {design && labels[design.id] && <GarmentTag tone="ink">No. {labels[design.id]}</GarmentTag>}
              {run?.styleNumber && <GarmentTag code={run.styleNumber}>Style</GarmentTag>}
              {quantity != null && (
                <GarmentTag code={`${quantity.toLocaleString("en-US")} units`}>Planned run</GarmentTag>
              )}
            </div>
          </div>
          <div className="w-full shrink-0 lg:w-80">
            <ProgressBar
              value={run ? done / steps.length : 0}
              label="Agents finished"
              detail={`${done} of ${steps.length}`}
              tone={run?.status === "failed" ? "bad" : run?.status === "completed" ? "ok" : "neutral"}
            />
            {run && <p className="mt-2 truncate font-mono text-micro text-fg-faint">{run.id}</p>}
          </div>
        </div>
      </Card>

      <GuardrailsPanel report={run?.guardrailReport} value={guardrails} onChange={setGuardrails} />

      {/* The agent timeline */}
      <Card pad="lg">
        <SheetHeading
          kicker="Agent pipeline"
          title={`${steps.length} agents, in sequence`}
          lede="Each step runs inside the brand guardrails. Where a person is needed, the timeline stops and says so."
        />
        <Timeline
          items={steps.map((step) =>
            timelineItem(step, {
              known: !!run,
              waitingOnHuman: awaitingHuman && step.key === "supplier_quotes" && step.status === "running",
              onRetry: retryRun,
              retrying: retry.status === "loading",
            }),
          )}
        />
      </Card>

      {(poll.status === "error" || retry.status === "error" || run?.status === "failed") && (
        <div className="flex flex-col gap-3">
          {poll.status === "error" && (
            <InlineAlert
              tone="bad"
              title="Lost contact with the pipeline"
              action={
                <Button size="sm" variant="secondary" icon={<IconRefresh size={14} />} onClick={resumePolling}>
                  Reconnect
                </Button>
              }
            >
              {poll.error}
            </InlineAlert>
          )}
          {retry.status === "error" && (
            <InlineAlert
              tone="bad"
              title="Retry failed"
              hint={retry.hint}
              action={
                <Button size="sm" variant="secondary" icon={<IconRefresh size={14} />} onClick={retryRun}>
                  Retry
                </Button>
              }
            >
              {retry.error}
            </InlineAlert>
          )}
          {run?.status === "failed" && (
            <InlineAlert
              tone={failedStep?.unknownExecutionId ? "warn" : "bad"}
              title={
                failedStep?.unknownExecutionId
                  ? `${failedStep.label}: status unknown - confirm before sending again`
                  : failedStep?.service
                    ? `${failedStep.label} stopped - ${serviceName(failedStep.service)} is not connected or not answering`
                    : "The run stopped at an error"
              }
              hint={failedStep?.hint}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<IconRefresh size={14} />}
                  loading={retry.status === "loading"}
                  onClick={failedStep?.retryable ? retryRun : () => runApprove(approve.quantity ?? 300)}
                >
                  {failedStep?.unknownExecutionId
                    ? "Send again anyway…"
                    : failedStep?.retryable
                      ? `Retry from “${failedStep.label}”`
                      : "Run again"}
                </Button>
              }
            >
              {failedStep?.unknownExecutionId && (
                <span className="block">
                  Evolus execution <span className="font-mono">{failedStep.unknownExecutionId}</span> started but its
                  outcome couldn&rsquo;t be read - the emails may already have gone out. Check Evolus first.{" "}
                </span>
              )}
              {failedStep?.error ?? "One of the agents reported an error."}
            </InlineAlert>
          )}
        </div>
      )}

      <Deliverables run={run} guardrails={guardrails} />
    </div>
  );
}

const STATUS_BADGE: Record<
  StepStatus,
  { tone: "ok" | "accent" | "warn" | "bad" | "faint" | "neutral"; label: string }
> = {
  done: { tone: "ok", label: "Done" },
  running: { tone: "accent", label: "Working" },
  waiting: { tone: "warn", label: "Waiting on you" },
  error: { tone: "bad", label: "Failed" },
  pending: { tone: "faint", label: "Not started" },
  skipped: { tone: "faint", label: "Skipped" },
};

function timelineItem(
  step: PipelineStep,
  {
    known,
    waitingOnHuman,
    onRetry,
    retrying,
  }: { known: boolean; waitingOnHuman?: boolean; onRetry?: () => void; retrying?: boolean },
): TimelineItem {
  const status: StepStatus =
    step.status === "running"
      ? waitingOnHuman
        ? "waiting"
        : "running"
      : step.status === "error"
        ? "error"
        : step.status;
  const b = STATUS_BADGE[status];
  const d = duration(step);
  const unknown = step.status === "error" && !!step.unknownExecutionId;
  return {
    id: step.key,
    title: step.label,
    status,
    description: STEP_BLURB[step.key],
    meta: (
      <>
        {d && <span className="tabular font-mono">{d}</span>}
        {known && <RouteTag route={step.route} />}
        {unknown ? (
          <Badge status="unknown" />
        ) : status === "running" ? (
          <Badge status="running">Working</Badge>
        ) : (
          <Badge tone={b.tone}>{b.label}</Badge>
        )}
      </>
    ),
    children:
      step.log.length > 0 || step.error || (step.telemetry?.length ?? 0) > 0 ? (
        <div className="flex flex-col gap-3">
          {step.log.length > 0 && <StepLog log={step.log} running={step.status === "running"} />}
          {step.status === "error" && (
            <InlineAlert
              tone={unknown ? "warn" : "bad"}
              title={unknown ? "Status unknown - confirm before re-sending" : (step.error ?? "This step failed")}
              hint={step.hint}
              action={
                step.retryable && onRetry ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<IconRefresh size={14} />}
                    onClick={onRetry}
                    loading={retrying}
                  >
                    {unknown ? "Send again anyway…" : "Retry"}
                  </Button>
                ) : undefined
              }
            >
              {unknown
                ? step.error
                : step.service
                  ? `${serviceName(step.service)} is not connected or not answering.`
                  : undefined}
            </InlineAlert>
          )}
          <StepTelemetry calls={step.telemetry} />
        </div>
      ) : undefined,
  };
}

/** The step's log in a mono well. Finished steps show their last lines; the full log is one click away. */
function StepLog({ log, running }: { log: string[]; running: boolean }) {
  const [all, setAll] = useState(false);
  const TAIL = 3;
  const collapsed = !running && !all && log.length > TAIL + 1;
  const shown = collapsed ? log.slice(-TAIL) : log;
  const offset = log.length - shown.length;
  return (
    <div className="rounded-panel bg-paper-2/70 px-4 py-3">
      {collapsed && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="mb-1.5 font-mono text-micro text-fg-faint underline-offset-4 hover:text-fg hover:underline"
        >
          + {offset} earlier line{offset === 1 ? "" : "s"}
        </button>
      )}
      <ul className="flex flex-col gap-1.5 font-mono text-[0.74rem] leading-relaxed" aria-live="polite">
        {shown.map((line, i) => (
          <LogLine key={offset + i} text={line} active={running && offset + i === log.length - 1} />
        ))}
      </ul>
      {all && !running && log.length > TAIL + 1 && (
        <button
          type="button"
          onClick={() => setAll(false)}
          className="mt-1.5 font-mono text-micro text-fg-faint underline-offset-4 hover:text-fg hover:underline"
        >
          − show the last {TAIL} only
        </button>
      )}
    </div>
  );
}

/** A log line that types itself out once, when it first arrives. */
function LogLine({ text, active }: { text: string; active: boolean }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (reduce) return;
    const step = Math.max(1, Math.ceil(text.length / 40));
    const id = setInterval(() => {
      setShown((n) => {
        if (n + step >= text.length) {
          clearInterval(id);
          return text.length;
        }
        return n + step;
      });
    }, 16);
    return () => clearInterval(id);
  }, [text, reduce]);
  const typing = shown < text.length;
  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35 }}
      className="flex gap-2 break-words text-fg-muted"
    >
      <span aria-hidden className="text-fg-faint">
        ›
      </span>
      <span className={cx("min-w-0", (typing || active) && "caret")}>
        <span className={active ? "text-fg" : undefined}>{text.slice(0, shown)}</span>
      </span>
    </motion.li>
  );
}

const rise = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: DUR.reveal, ease: EASE },
};

function Deliverables({ run, guardrails }: { run?: PipelineRun; guardrails: Guardrails | null }) {
  if (!run) return null;
  const { techPack, supplierEmails, shopifyProduct } = run;
  return (
    <div className="mt-12 flex flex-col gap-16 sm:mt-16 sm:gap-20">
      <AnimatePresence>
        {techPack && (
          <motion.div key="tp" {...rise}>
            <TechPackEditor key={`${run.id}:${run.techPackRevision ?? 0}`} run={run} guardrails={guardrails} />
          </motion.div>
        )}
      </AnimatePresence>
      {(supplierEmails?.length || shopifyProduct) && (
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-6">
          <div className="min-w-0">
            {supplierEmails && supplierEmails.length > 0 && (
              <motion.div data-demo="outreach" {...rise}>
                <SupplierEmails
                  emails={supplierEmails}
                  route={run.steps.find((s) => s.key === "supplier_outreach")?.route}
                />
              </motion.div>
            )}
          </div>
          <div className="min-w-0">
            {shopifyProduct && (
              <motion.div data-demo="storefront" {...rise}>
                <ShopifyCard product={shopifyProduct} />
              </motion.div>
            )}
          </div>
        </div>
      )}
      {(run.quotes?.length || run.steps.some((s) => s.key === "supplier_quotes" && s.status === "running")) && (
        <motion.div data-demo="quotes" {...rise}>
          <QuotesPanel run={run} />
        </motion.div>
      )}
      {run.decision && <DecisionPanel run={run} />}
      {(run.audit?.length ?? 0) > 0 && <AuditTrail entries={run.audit ?? []} />}
      {run.demand && (
        <motion.div data-demo="demand" {...rise}>
          <DemandTracker run={run} />
        </motion.div>
      )}
      {run.demand && run.techPack && <ForecastPanel run={run} />}
    </div>
  );
}

const EMAIL_BADGE: Record<SupplierEmail["status"], "draft" | "pending" | "sent"> = {
  drafted: "draft",
  queued: "pending",
  sent: "sent",
};

function SupplierEmails({ emails, route }: { emails: SupplierEmail[]; route?: string }) {
  const [open, setOpen] = useState<number | null>(0);
  const [english, setEnglish] = useState<Record<number, boolean>>({});
  const languages = [...new Set(emails.map((e) => e.languageName).filter(Boolean))];
  const sent = emails.filter((e) => e.status === "sent").length;
  return (
    <section>
      <SheetHeading
        kicker="Supplier outreach"
        tone={sent === emails.length ? "ok" : sent > 0 ? "accent" : "faint"}
        title={`${emails.length} RFQ${emails.length === 1 ? "" : "s"} prepared`}
        lede={
          <>
            {sent} of {emails.length} sent
            {languages.length > 0 && <> · written in {languages.join(", ")}</>}. Each mill gets its own language; the
            English stays here for you.
          </>
        }
        route={route}
      />
      <ul className="flex flex-col gap-3">
        {emails.map((e, i) => {
          const isOpen = open === i;
          const foreign = !!e.language && e.language !== "en" && !!e.bodyEnglish;
          const showEn = foreign && !!english[i];
          const subject = showEn ? (e.subjectEnglish ?? e.subject) : e.subject;
          return (
            <li key={`${e.supplierName}-${i}`}>
              <Disclosure
                data-demo={`rfq-${e.language ?? "en"}`}
                open={isOpen}
                onOpenChange={(v) => setOpen(v ? i : null)}
                className="shadow-e1"
                leading={
                  <span
                    aria-hidden
                    className="relative grid size-10 place-items-center rounded-full bg-paper-2 text-fg"
                  >
                    <IconMail size={16} />
                    <span className="absolute -right-1 -bottom-1 rounded-full border-2 border-surface bg-inverse px-1 font-mono text-[0.55rem] leading-3.5 text-on-inverse">
                      {(e.language ?? "en").toUpperCase()}
                    </span>
                  </span>
                }
                title={
                  <>
                    <span className="block truncate">{e.supplierName}</span>
                    <span className="block truncate text-small font-normal text-fg-muted">
                      {e.region}
                      {e.languageName && ` · ${e.languageName}`}
                      <span className="hidden md:inline"> · {subject}</span>
                    </span>
                  </>
                }
                meta={<Badge status={EMAIL_BADGE[e.status]}>{e.status === "queued" ? "Queued" : undefined}</Badge>}
              >
                <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-small">
                  <dt>
                    <Label>To</Label>
                  </dt>
                  <dd className="font-mono text-[0.78rem] break-all text-fg">{e.toEmail}</dd>
                  <dt>
                    <Label>Subject</Label>
                  </dt>
                  <dd className="break-words text-fg">{subject}</dd>
                  {e.rfqRef && (
                    <>
                      <dt>
                        <Label>Ref</Label>
                      </dt>
                      <dd className="font-mono text-[0.78rem] text-fg-muted">{e.rfqRef}</dd>
                    </>
                  )}
                </dl>
                {foreign && (
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Badge tone="accent">{showEn ? "English - for you" : `Sent in ${e.languageName}`}</Badge>
                    <Button
                      size="sm"
                      variant="ghost"
                      data-demo="show-english"
                      onClick={() => setEnglish((m) => ({ ...m, [i]: !m[i] }))}
                      aria-pressed={showEn}
                    >
                      {showEn ? `Show the ${e.languageName} original` : "Show English"}
                    </Button>
                    {showEn && (
                      <span className="text-micro text-fg-faint">The mill receives the {e.languageName}.</span>
                    )}
                  </div>
                )}
                <p
                  lang={showEn ? "en" : (e.language ?? "en")}
                  className="mt-4 rounded-panel bg-paper-2/70 p-4 text-small leading-relaxed break-words whitespace-pre-wrap text-fg-muted sm:p-5"
                >
                  {showEn ? e.bodyEnglish : e.body}
                </p>
              </Disclosure>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * The listing price in the STORE's currency. When the store sells in another currency than the brand, both are shown
 * with the ECB rate used - never a brand-currency number labelled in the store's currency.
 */
function ListingPrice({ product }: { product: ShopifyProduct }) {
  const store = product.currency;
  const brand = product.brandCurrency;
  const converted = !!store && !!brand && store !== brand && product.priceBrand != null;
  return (
    <div className="mt-5 grid grid-cols-2 gap-4 rounded-panel bg-paper-2/70 p-4">
      <div className="min-w-0">
        <Label as="p">Store price{store ? ` · ${store}` : ""}</Label>
        <p className="mt-1.5 tabular text-[1.6rem] leading-none font-light tracking-[-0.03em] text-fg">
          {money(product.price, store ?? brand)}
        </p>
        <p className="mt-1 text-micro text-fg-faint">{store ? "what shoppers pay" : "store currency not verified"}</p>
      </div>
      <div className="min-w-0 border-l border-line pl-4">
        <Label as="p">Brand retail{brand ? ` · ${brand}` : ""}</Label>
        <p className="mt-1.5 tabular text-[1.6rem] leading-none font-light tracking-[-0.03em] text-fg">
          {converted
            ? money(product.priceBrand as number, brand)
            : store && brand && store === brand
              ? money(product.price, brand)
              : product.priceBrand != null
                ? money(product.priceBrand, brand)
                : "-"}
        </p>
        <p className="mt-1 text-micro text-fg-faint">
          {converted
            ? `ECB rate${product.fxDate ? ` of ${product.fxDate}` : ""}${product.fxRate ? ` · 1 ${brand} = ${product.fxRate.toFixed(4)} ${store}` : ""}`
            : store && brand && store === brand
              ? "same currency as the store"
              : !store
                ? `listed at the brand retail in ${brand ?? "the brand currency"} (no Admin API access)`
                : "no brand currency on the listing"}
        </p>
      </div>
    </div>
  );
}

function ShopifyCard({ product }: { product: ShopifyProduct }) {
  const via = product.source === "evolus" ? "Created by the Evolus workflow" : "Created via the Shopify Admin API";
  return (
    <section>
      <SheetHeading kicker={`Storefront · ${product.shopDomain ?? "Shopify"}`} tone="ok" live title="Pre-order live" />
      <Card pad="none" className="overflow-hidden">
        <div className="relative">
          <SmartImage src={product.imageUrl} alt={product.title} className="aspect-[16/10]" />
          <div className="absolute top-4 left-4 flex flex-wrap gap-2">
            <Badge tone="accent" className="bg-surface shadow-e1">
              Pre-order
            </Badge>
            {product.published && (
              <Badge tone="ok" className="bg-surface shadow-e1">
                Published
              </Badge>
            )}
          </div>
        </div>
        <div className="p-5 sm:p-6">
          <h4 className="text-title text-fg">{product.title}</h4>
          <p className="mt-1 font-mono text-micro break-all text-fg-faint">/{product.handle}</p>
          <ListingPrice product={product} />
          <p className="mt-4 text-micro text-fg-muted">
            {via}
            {product.published ? " · published to the Online Store" : ""}
            {product.sizes && product.sizes.length > 0 && ` · sizes ${product.sizes.join(", ")}`}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {product.url && (
              <a
                href={product.url}
                target="_blank"
                rel="noreferrer"
                className={buttonClass({ variant: "secondary", size: "sm" })}
              >
                View on store <IconArrowUpRight size={14} />
              </a>
            )}
            {product.adminUrl && (
              <a
                href={product.adminUrl}
                target="_blank"
                rel="noreferrer"
                className={buttonClass({ variant: "ghost", size: "sm" })}
              >
                Shopify admin <IconArrowUpRight size={14} />
              </a>
            )}
          </div>
        </div>
      </Card>
    </section>
  );
}
