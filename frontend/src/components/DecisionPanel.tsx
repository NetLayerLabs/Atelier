"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
  cx,
  Dial,
  DUR,
  EASE,
  Eyebrow,
  Field,
  GarmentTag,
  IconArrowRight,
  IconRefresh,
  InlineAlert,
  Input,
  Label,
  Spinner,
  Stitch,
  Textarea,
} from "@/components/ds";
import {
  approveDecision,
  errorHint,
  errorMessage,
  negotiateDecision,
  sendCounterOffer,
  switchDecision,
  type AuditEntry,
  type CounterOffer,
  type Decision,
  type PipelineRun,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { RouteTag } from "./Inference";
import { KeyValues, money, SheetHeading } from "./Sheet";

type ErrState = { message: string; hint?: string } | null;
const toErr = (err: unknown): ErrState => ({ message: errorMessage(err), hint: errorHint(err) });

function ErrLine({ error, onRetry, className }: { error: ErrState; onRetry?: () => void; className?: string }) {
  if (!error) return null;
  return (
    <InlineAlert
      tone="bad"
      title={error.hint ? "Not connected" : "That didn't go through"}
      hint={error.hint}
      className={className}
      action={
        onRetry ? (
          <Button size="sm" variant="secondary" icon={<IconRefresh size={14} />} onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
    >
      {error.message}
    </InlineAlert>
  );
}

const OUTCOME: Record<NonNullable<Decision["outcome"]>, string> = {
  approved: "Approved with an override",
  switched: "Switched mill",
  revised: "Revised quote inside the guardrails",
  guardrails_changed: "Guardrails changed - the pick now passes",
  techpack_changed: "Tech pack changed - the pick now passes",
};

/** v4: the human hand-off - the agent stopped because its pick breaks a brand guardrail. */
export function DecisionPanel({ run }: { run: PipelineRun }) {
  const updateRun = useAtelier((s) => s.updateRun);
  const d = run.decision;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ErrState>(null);
  const [lastAct, setLastAct] = useState<{ key: string; fn: () => Promise<PipelineRun> } | null>(null);
  const [note, setNote] = useState("");
  if (!d) return null;
  const open = d.status !== "resolved";

  const act = async (key: string, fn: () => Promise<PipelineRun>) => {
    setBusy(key);
    setError(null);
    setLastAct({ key, fn });
    try {
      updateRun(await fn());
    } catch (err) {
      setError(toErr(err));
    } finally {
      setBusy(null);
    }
  };

  if (!open) {
    return (
      <Card as="section" pad="lg" data-demo="decision">
        <SheetHeading
          kicker="Hand-off resolved"
          tone="ok"
          title={
            <>
              {d.outcome ? OUTCOME[d.outcome] : "Resolved"} <span className="text-fg-faint">→</span>{" "}
              {d.resolvedSupplierName}
            </>
          }
          lede={
            <>
              {d.resolvedBy}
              {d.resolvedAt && ` · ${new Date(d.resolvedAt).toLocaleTimeString()}`}
              {d.note && ` · “${d.note}”`}
              {d.negotiationRounds > 0 &&
                ` · ${d.negotiationRounds} counter-offer${d.negotiationRounds > 1 ? "s" : ""}`}
            </>
          }
        />
        {d.counterOffer && <CounterOfferView co={d.counterOffer} runId={run.id} readOnly />}
      </Card>
    );
  }

  const negotiate = d.options.find((o) => o.kind === "negotiate");
  const switches = d.options.filter((o) => o.kind === "switch");
  const co = d.counterOffer;
  const report = run.guardrailReport;
  const evaluation = report?.evaluations.find((e) => e.supplierName === d.supplierName);
  const floor = report?.guardrails.minGrossMarginPct;
  const margin = evaluation?.marginPct;
  return (
    <motion.section
      data-demo="decision"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.reveal, ease: EASE }}
      className="ds-inverse relative overflow-hidden rounded-card shadow-e3"
      aria-live="polite"
    >
      <div className="p-5 sm:p-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Eyebrow tone="warn" live>
            {d.status === "negotiating"
              ? "Negotiating - the pipeline is paused"
              : "Your call · the agent stopped and is asking you"}
          </Eyebrow>
          <Badge tone="faint">Nothing goes to Shopify until you decide</Badge>
        </div>
        <Stitch label="Agent → you" className="mt-6" />

        <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
          {/* What broke */}
          <div className="min-w-0">
            <Label as="p">What broke · {d.supplierName}</Label>
            <div className="mt-4 flex flex-col items-center rounded-panel border border-line bg-surface px-4 pt-8 pb-6">
              <Dial
                label="Gross margin"
                value={margin ?? null}
                floor={floor != null ? { value: floor, label: `Floor ${floor}%` } : undefined}
                format={(n) => `${Math.round(n)}%`}
                readout={
                  <>
                    <span className="tabular text-[2.6rem] leading-none font-light tracking-[-0.04em] text-fg">
                      {margin != null ? `${margin.toFixed(1)}%` : "-"}
                    </span>
                    <span className="mt-1.5 text-small text-fg-muted">Gross margin</span>
                  </>
                }
                caption={
                  margin == null
                    ? "margin not readable from this quote"
                    : floor == null
                      ? "no margin floor set - margin is not checked"
                      : margin >= floor
                        ? `above the ${floor}% floor`
                        : `${(floor - margin).toFixed(1)} pts below the ${floor}% floor`
                }
              />
            </div>
            <ul className="mt-4 flex flex-col">
              {d.breaches.map((b) => (
                <li
                  key={b.rule}
                  title={b.message}
                  className="flex items-start justify-between gap-3 border-t border-line py-3 first:border-t-0"
                >
                  <span className="min-w-0">
                    <span className="block text-small font-medium text-fg">{b.label}</span>
                    <span className="block text-micro text-fg-muted">{b.message}</span>
                  </span>
                  <span className="shrink-0 text-right font-mono text-small">
                    <span className="block text-bad">{b.actual}</span>
                    <span className="block text-micro text-fg-faint">limit {b.limit}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* The question and the options (first on a phone: the human's call leads) */}
          <div className="order-first min-w-0 lg:order-none">
            <h3 className="text-display-m text-balance text-fg">{d.headline}</h3>
            <p className="mt-4 max-w-2xl text-body leading-relaxed text-fg-muted">{d.explanation}</p>

            <div className="mt-8 flex flex-col gap-3" role="group" aria-label="Your options">
              <Option
                numeral="i"
                title="Approve anyway"
                detail={`Proceed with ${d.supplierName}. Recorded in the audit log as an override.`}
              >
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Note for the audit log (optional)"
                    aria-label="Override note"
                    className="h-10"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-10 sm:shrink-0"
                    data-demo="decision-approve"
                    loading={busy === "approve"}
                    disabled={!!busy}
                    onClick={() => act("approve", () => approveDecision(run.id, note))}
                  >
                    Approve with override
                  </Button>
                </div>
              </Option>
              <Option
                numeral="ii"
                title="Negotiate"
                detail={negotiate ? negotiate.detail : "Only certificates are missing - a mill can't negotiate those."}
                recommended={!!negotiate}
              >
                <Button
                  size="sm"
                  data-demo="decision-negotiate"
                  loading={busy === "negotiate"}
                  disabled={!negotiate || !!busy}
                  onClick={() => act("negotiate", () => negotiateDecision(run.id))}
                >
                  {co ? "Redraft counter-offer" : "Draft counter-offer"}
                </Button>
              </Option>
              <Option
                numeral="iii"
                title="Switch mill"
                detail={
                  switches.length === 0
                    ? d.allQuotesBreach
                      ? "Every quote breaks a guardrail."
                      : "No other quote is inside the guardrails."
                    : "Move the order to a quote that is inside every guardrail."
                }
              >
                {switches.length > 0 && (
                  <div className="flex flex-col gap-2">
                    {switches.map((o) => (
                      <button
                        key={o.supplierName}
                        type="button"
                        data-demo={`decision-switch-${o.supplierName}`}
                        disabled={!!busy}
                        onClick={() =>
                          act(`switch:${o.supplierName}`, () => switchDecision(run.id, o.supplierName ?? "", note))
                        }
                        className="group flex min-h-11 items-center justify-between gap-3 rounded-field border border-line-strong bg-surface px-4 py-2 text-left transition-colors hover:border-fg disabled:opacity-50"
                      >
                        <span className="min-w-0">
                          <span className="block text-small font-medium text-fg">{o.label}</span>
                          <span className="block font-mono text-micro text-fg-muted">{o.detail}</span>
                        </span>
                        {busy === `switch:${o.supplierName}` ? (
                          <Spinner />
                        ) : (
                          <IconArrowRight
                            size={16}
                            className="shrink-0 transition-transform group-hover:translate-x-0.5"
                          />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </Option>
            </div>
            <ErrLine
              error={error}
              className="mt-4"
              onRetry={error?.hint && lastAct ? () => act(lastAct.key, lastAct.fn) : undefined}
            />
          </div>
        </div>
      </div>
      <AnimatePresence>
        {co && (
          <motion.div
            key="co"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            transition={{ duration: DUR.sheet, ease: EASE }}
            className="overflow-hidden border-t border-line"
          >
            <div className="p-5 sm:p-10">
              <CounterOfferView key={co.createdAt} co={co} runId={run.id} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

/** One of the three hand-off options: a numbered card with its own action. */
function Option({
  numeral,
  title,
  detail,
  recommended,
  children,
}: {
  numeral: string;
  title: string;
  detail: ReactNode;
  recommended?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={cx("rounded-panel border bg-surface p-4 sm:p-5", recommended ? "border-line-bold" : "border-line")}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="grid size-7 shrink-0 place-items-center rounded-full border border-line-strong text-micro font-medium text-fg"
        >
          {numeral}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-body font-medium text-fg">{title}</p>
          <p className="mt-0.5 text-small text-fg-muted">{detail}</p>
          {children && <div className="mt-3">{children}</div>}
        </div>
      </div>
    </div>
  );
}

function CounterOfferView({ co, runId, readOnly }: { co: CounterOffer; runId: string; readOnly?: boolean }) {
  const updateRun = useAtelier((s) => s.updateRun);
  const [subject, setSubject] = useState(co.subject);
  const [body, setBody] = useState(co.body);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrState>(null);
  const draft = co.status === "draft" && !readOnly;
  // QA M3: the workflow started but its outcome couldn't be read - the mill may already have the email.
  const unknown = co.status === "unknown" && !readOnly;
  const foreign = co.language !== "en";
  const brand = co.brandCurrency ?? co.currency;

  const send = async () => {
    if (busy) return; // QA M2: one send at a time (the backend also answers 409 while one is in flight)
    if (
      unknown &&
      !window.confirm(
        `The counter-offer may already have reached ${co.supplierName} (Evolus execution ${co.executionId ?? "?"}, ` +
          "status unknown). Check Evolus first. Send it again anyway?",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      updateRun(
        await sendCounterOffer(
          runId,
          {
            subject: subject !== co.subject ? subject : undefined,
            body: body !== co.body ? body : undefined,
          },
          { confirmResend: unknown },
        ),
      );
    } catch (err) {
      setError(toErr(err));
    } finally {
      setBusy(false);
    }
  };

  const statusBadge =
    co.status === "draft" ? (
      <Badge status="draft" />
    ) : co.status === "unknown" ? (
      <Badge status="unknown" />
    ) : co.status === "sending" ? (
      <Badge status="running">Sending</Badge>
    ) : co.status === "queued" ? (
      <Badge status="pending">Queued</Badge>
    ) : (
      <Badge status="sent" />
    );

  return (
    <div data-demo="counter-offer" className={readOnly ? "mt-2" : undefined}>
      <div className="flex flex-wrap items-center gap-2">
        <Eyebrow tone="accent">
          Counter-offer to {co.supplierName} · in {co.languageName}
        </Eyebrow>
        {statusBadge}
        <RouteTag route={co.generatedBy} />
        {co.edited && <Badge tone="faint">edited by you</Badge>}
      </div>
      <p className="mt-2 text-micro text-fg-faint">The wording is drafted by a model; every number is computed.</p>

      <div className="mt-6 grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className={cx("grid min-w-0 gap-6", foreign && "md:grid-cols-2")}>
          <div className="flex min-w-0 flex-col gap-3" data-demo="counter-local">
            <Label as="p">{foreign ? `${co.languageName} - what the mill receives` : "Email"}</Label>
            {draft ? (
              <>
                <Field label="Subject">
                  <Input
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    aria-label="Counter-offer subject"
                  />
                </Field>
                <Field label="Message">
                  <Textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    aria-label="Counter-offer body"
                    rows={10}
                    className="text-small"
                  />
                </Field>
              </>
            ) : (
              <div className="rounded-panel border border-line bg-surface p-4">
                <p className="text-small font-medium text-fg">{co.subject}</p>
                <p className="mt-3 text-small leading-relaxed whitespace-pre-wrap text-fg-muted">{co.body}</p>
              </div>
            )}
          </div>
          {foreign && (
            <div className="flex min-w-0 flex-col gap-3" data-demo="counter-english">
              <Label as="p">English - for you</Label>
              <div className="rounded-panel bg-paper-2/70 p-4">
                <p className="text-small font-medium text-fg">{co.subjectEnglish}</p>
                <p className="mt-3 text-small leading-relaxed whitespace-pre-wrap text-fg-muted">{co.bodyEnglish}</p>
              </div>
            </div>
          )}
        </div>
        <aside className="flex min-w-0 flex-col gap-5">
          <div className="rounded-panel border border-line bg-surface" data-demo="counter-math">
            <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
              <Label as="p">The maths · deterministic</Label>
              {co.reductionPct > 0 && (
                <span className="font-mono text-micro text-fg-muted">−{co.reductionPct.toFixed(1)}% asked</span>
              )}
            </div>
            {(co.quotedUnitPrice != null || co.targetUnitPrice != null) && (
              <div className="grid grid-cols-2 border-b border-line">
                <div className="px-4 py-3">
                  <Label as="p">Quoted</Label>
                  <p className="mt-1 tabular text-[1.4rem] leading-none font-light text-fg">
                    {co.quotedUnitPrice != null ? money(co.quotedUnitPrice, brand) : "-"}
                  </p>
                  {co.quotedUnitPriceLocal != null && co.currency !== brand && (
                    <p className="mt-1 font-mono text-micro text-fg-faint">
                      {money(co.quotedUnitPriceLocal, co.currency)}
                    </p>
                  )}
                </div>
                <div className="border-l border-line px-4 py-3">
                  <Label as="p">Asking</Label>
                  <p className="mt-1 tabular text-[1.4rem] leading-none font-light text-accent">
                    {co.targetUnitPrice != null ? money(co.targetUnitPrice, brand) : "-"}
                  </p>
                  {co.targetUnitPriceLocal != null && co.currency !== brand && (
                    <p className="mt-1 font-mono text-micro text-fg-faint">
                      {money(co.targetUnitPriceLocal, co.currency)}
                    </p>
                  )}
                </div>
              </div>
            )}
            <ol className="flex flex-col px-4 py-2 font-mono text-[0.72rem] leading-relaxed text-fg-muted">
              {co.math.map((m, i) => (
                <li key={i} className="flex gap-3 border-t border-line py-2 first:border-t-0">
                  <span className="w-4 shrink-0 text-fg-faint">{i + 1}</span>
                  <span className="min-w-0 break-words">{m}</span>
                </li>
              ))}
            </ol>
          </div>
          <KeyValues
            rows={[
              [
                "To",
                <span key="to" className="break-all">
                  {co.toEmail}
                </span>,
              ],
              ["Quote", `${co.quoteNumber ?? "-"} · ${co.rfqRef}`],
              ...(co.sentVia
                ? ([["Sent", `${co.sentAt ? new Date(co.sentAt).toLocaleTimeString() : ""} · ${co.sentVia}`]] as [
                    ReactNode,
                    ReactNode,
                  ][])
                : []),
            ]}
          />
          {draft ? (
            <Button
              variant="accent"
              size="lg"
              data-demo="counter-send"
              onClick={send}
              loading={busy}
              disabled={!subject.trim() || !body.trim()}
            >
              Send to {co.supplierName}
            </Button>
          ) : unknown ? (
            <InlineAlert
              tone="warn"
              title="Status unknown - confirm before re-sending"
              action={
                <Button size="sm" variant="secondary" onClick={send} loading={busy}>
                  Send again anyway…
                </Button>
              }
            >
              Evolus execution <span className="font-mono">{co.executionId ?? "?"}</span> started but its outcome
              couldn&rsquo;t be read: the mill may already have this email.
            </InlineAlert>
          ) : co.status === "sending" ? (
            <p className="flex items-center gap-2 text-small text-accent">
              <Spinner /> Sending through Evolus…
            </p>
          ) : (
            !readOnly && (
              <div
                className="flex items-start gap-3 rounded-panel bg-accent-soft p-4 text-small text-fg"
                data-demo="counter-waiting"
              >
                <span aria-hidden className="mt-1.5 size-2 shrink-0 rounded-full bg-accent ds-live" />
                <span>
                  Waiting for {co.supplierName}&rsquo;s revised quote - drop it in the Quotes panel above, or it arrives
                  by email with ref <span className="font-mono">{co.rfqRef}</span>. It is checked against the guardrails
                  as soon as it lands.
                </span>
              </div>
            )
          )}
          {co.sendError && !error && (
            <InlineAlert tone={unknown ? "warn" : "bad"} title={unknown ? "Send status" : "Last send attempt failed"}>
              {co.sendError}
            </InlineAlert>
          )}
          <ErrLine error={error} onRetry={error?.hint ? send : undefined} />
        </aside>
      </div>
    </div>
  );
}

const ACTOR_TONE: Record<AuditEntry["actor"], "accent" | "ok" | "faint"> = {
  agent: "accent",
  human: "ok",
  system: "faint",
};

/** v4: who decided what, when, which guardrail, with the numbers. */
export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  const [all, setAll] = useState(false);
  if (!entries.length) return null;
  const shown = all ? entries : entries.slice(-8);
  return (
    <Card as="section" pad="lg" data-demo="audit">
      <SheetHeading
        kicker="Audit trail"
        title="Who decided what"
        lede="Every agent step and every human call, with the guardrail and the numbers it was judged on."
        aside={<GarmentTag code={String(entries.length)}>Entries</GarmentTag>}
      />
      <ol className="flex flex-col">
        {shown.map((a, i) => (
          <li
            key={`${a.at}-${i}`}
            className="grid grid-cols-[4.75rem_minmax(0,1fr)] gap-x-4 gap-y-1 border-t border-line py-4 first:border-t-0 sm:grid-cols-[5.5rem_5.5rem_minmax(0,1fr)]"
          >
            <span className="font-mono text-micro leading-6 text-fg-faint tabular">
              {new Date(a.at).toLocaleTimeString()}
            </span>
            <span className="sm:pt-px">
              <Badge tone={ACTOR_TONE[a.actor]}>{a.actor}</Badge>
            </span>
            <div className="col-span-2 min-w-0 sm:col-span-1">
              <p className="break-words text-small text-fg">
                <span className="font-mono text-micro text-fg-faint">{a.action.replace(/_/g, " ")} · </span>
                {a.summary}
              </p>
              {(a.guardrail || Object.keys(a.values).length > 0) && (
                <p className="mt-1 font-mono text-micro break-words text-fg-muted">
                  {a.guardrail && `guardrail ${a.guardrail}`}
                  {a.guardrail && Object.keys(a.values).length > 0 && " · "}
                  {Object.entries(a.values)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" · ")}
                </p>
              )}
              {a.note && <p className="mt-1 text-small text-fg-muted">“{a.note}”</p>}
            </div>
          </li>
        ))}
      </ol>
      {entries.length > 8 && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setAll(!all)}>
          {all ? "Show recent" : `Show all ${entries.length}`}
        </Button>
      )}
    </Card>
  );
}
