"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState, type FormEvent } from "react";
import {
  Button,
  Card,
  cx,
  Dial,
  DUR,
  EASE,
  Eyebrow,
  Field,
  InlineAlert,
  Input,
  Label,
  Segmented,
} from "@/components/ds";
import { errorMessage, putGuardrails, resetGuardrails, type GuardrailReport, type Guardrails } from "@/lib/api";
import { currencySymbol, money } from "./Sheet";

/**
 * v4: the brand's guardrails. The agent stops and hands the case to a person when its pick breaks one.
 * `value` is the saved set from the Brand workspace (loaded by the pipeline); the run's report only adds the derived
 * unit-cost cap for this tech pack.
 */
export function GuardrailsPanel({
  report,
  value,
  onChange,
}: {
  report?: GuardrailReport;
  value?: Guardrails | null;
  onChange?: (g: Guardrails) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shown = value ?? report?.guardrails;
  if (!shown) return null;
  const chips = guardrailChips(shown, report);
  const selected = report?.evaluations.find((e) => e.supplierName === report.selectedSupplierName);

  return (
    <Card as="section" pad="none" data-demo="guardrails" className="overflow-hidden">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div className="min-w-0">
          <Eyebrow tone={report ? (report.selectedOk === false ? "bad" : "ok") : "neutral"}>Brand guardrails</Eyebrow>
          <p className="mt-2 max-w-2xl text-small text-fg-muted">
            The agent checks every quote against these and stops to ask you when its pick breaks one. Rules marked “not
            set” are not checked.
          </p>
        </div>
        {value && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setEditing((v) => !v)}
            aria-expanded={editing}
            className="shrink-0"
          >
            {editing ? "Close" : "Edit guardrails"}
          </Button>
        )}
      </div>
      <GuardrailFacts chips={chips} />
      <AnimatePresence initial={false}>
        {editing && value && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: DUR.ui, ease: EASE }}
            className="overflow-hidden border-t border-line"
          >
            <div className="p-5 sm:p-6">
              <GuardrailsForm
                value={value}
                reading={
                  selected?.marginPct != null
                    ? { value: selected.marginPct, label: `${selected.supplierName}'s quote` }
                    : undefined
                }
                onSaved={(v) => {
                  onChange?.(v);
                  setEditing(false);
                  setError(null);
                }}
                onError={setError}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {error && (
        <div className="border-t border-line p-4 sm:p-5">
          <InlineAlert tone="bad" title="Guardrails not saved">
            {error}
          </InlineAlert>
        </div>
      )}
    </Card>
  );
}

/** The five rules as a row of label / value cells (hairline-separated; 2 columns on mobile). */
export function GuardrailFacts({ chips, className }: { chips: [string, string][]; className?: string }) {
  return (
    <dl className={cx("grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-5", className)}>
      {chips.map(([k, v], i) => (
        <div
          key={k}
          className={cx(
            "min-w-0 bg-surface px-5 py-4 sm:px-6",
            i === chips.length - 1 && chips.length % 2 === 1 && "col-span-2 sm:col-span-1",
          )}
        >
          <dt>
            <Label>{k}</Label>
          </dt>
          <dd className={cx("mt-1.5 font-mono text-small break-words", v === NOT_SET ? "text-fg-faint" : "text-fg")}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const NOT_SET = "not set";

/** The guardrails as label/value chips; a rule the brand left empty reads "not set". */
export function guardrailChips(shown: Guardrails, report?: GuardrailReport): [string, string][] {
  const autoCap = !shown.maxUnitCost && report?.maxUnitCostDerived ? report.guardrails.maxUnitCost : undefined;
  const unitCost = shown.maxUnitCost
    ? `≤ ${money(shown.maxUnitCost, shown.currency)}`
    : autoCap
      ? `≤ ${money(autoCap, shown.currency)} (auto)`
      : shown.costHeadroomPct != null
        ? `≤ costing + ${shown.costHeadroomPct}%`
        : NOT_SET;
  return [
    ["Margin", shown.minGrossMarginPct != null ? `≥ ${shown.minGrossMarginPct}%` : NOT_SET],
    ["Unit cost", unitCost],
    ["Lead time", shown.maxLeadTimeWeeks ? `≤ ${shown.maxLeadTimeWeeks} wks` : NOT_SET],
    ["MOQ", shown.maxMoq ? `≤ ${shown.maxMoq.toLocaleString("en-US")}` : NOT_SET],
    [
      "Certificates",
      shown.requiredCertifications.length
        ? shown.requiredCertifications.join(shown.certificationsMode === "any" ? " or " : " + ")
        : NOT_SET,
    ],
  ];
}

const num = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
};

/**
 * The guardrails editor (pipeline panel and Brand workspace step V). Units sit inside the inputs; the margin floor
 * is previewed live on a Dial. `reading` puts a real margin on the dial (e.g. the selected quote's); without one the
 * needle stays parked and the dial reads "-".
 */
export function GuardrailsForm({
  value,
  onSaved,
  onError,
  reading,
}: {
  value: Guardrails;
  onSaved: (g: Guardrails) => void;
  onError: (msg: string | null) => void;
  reading?: { value: number; label: string };
}) {
  const [margin, setMargin] = useState(value.minGrossMarginPct != null ? String(value.minGrossMarginPct) : "");
  const [maxCost, setMaxCost] = useState(value.maxUnitCost ? String(value.maxUnitCost) : "");
  const [headroom, setHeadroom] = useState(value.costHeadroomPct != null ? String(value.costHeadroomPct) : "");
  const [lead, setLead] = useState(value.maxLeadTimeWeeks ? String(value.maxLeadTimeWeeks) : "");
  const [moq, setMoq] = useState(value.maxMoq ? String(value.maxMoq) : "");
  const [certs, setCerts] = useState(value.requiredCertifications.join(", "));
  const [mode, setMode] = useState(value.certificationsMode);
  const [busy, setBusy] = useState<"save" | "reset" | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const m = num(margin);
    const c = num(maxCost);
    const h = num(headroom);
    const l = num(lead);
    const q = num(moq);
    if (m !== null && (Number.isNaN(m) || m < 0 || m >= 100))
      return onError("Margin floor must be between 0 and 99 (or empty: not set).");
    if ([c, h, l, q].some((x) => x !== null && (Number.isNaN(x) || x <= 0)))
      return onError("Limits must be positive numbers (leave a field empty: not set, not checked).");
    setBusy("save");
    onError(null);
    try {
      onSaved(
        await putGuardrails({
          minGrossMarginPct: m,
          maxUnitCost: c,
          costHeadroomPct: h,
          maxLeadTimeWeeks: l === null ? null : Math.round(l),
          maxMoq: q === null ? null : Math.round(q),
          requiredCertifications: certs
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          certificationsMode: mode,
        }),
      );
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    setBusy("reset");
    try {
      onSaved(await resetGuardrails());
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const floor = num(margin);
  const floorOk = floor !== null && !Number.isNaN(floor) && floor >= 0 && floor < 100;
  const sym = currencySymbol(value.currency);

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Field label="Minimum gross margin" hint="the floor on the dial; empty = not checked">
          <Input
            inputMode="decimal"
            suffix="%"
            placeholder="not set"
            value={margin}
            onChange={(e) => setMargin(e.target.value)}
          />
        </Field>
        <Field label="Max unit cost" hint={`in ${value.currency}, the brand currency`}>
          <Input
            inputMode="decimal"
            prefix={sym || undefined}
            placeholder={headroom ? `auto: costing + ${headroom}%` : "not set"}
            value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)}
          />
        </Field>
        <Field
          label="Auto cap headroom"
          hint={maxCost.trim() ? "off while a max unit cost is set" : "cap = tech pack costing + this"}
        >
          <Input
            inputMode="decimal"
            suffix="%"
            placeholder="not set"
            value={headroom}
            disabled={!!maxCost.trim()}
            onChange={(e) => setHeadroom(e.target.value)}
          />
        </Field>
        <Field label="Max lead time">
          <Input
            inputMode="numeric"
            suffix="weeks"
            placeholder="not set"
            value={lead}
            onChange={(e) => setLead(e.target.value)}
          />
        </Field>
        <Field label="Max MOQ">
          <Input
            inputMode="numeric"
            suffix="pcs / col."
            placeholder="not set"
            value={moq}
            onChange={(e) => setMoq(e.target.value)}
          />
        </Field>
        <Field label="Required certificates" hint="comma-separated">
          <Input placeholder="e.g. GOTS, OEKO-TEX" value={certs} onChange={(e) => setCerts(e.target.value)} />
        </Field>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-small font-medium text-fg">Certificates rule</span>
          <Segmented
            className="self-start"
            label="Certificates rule"
            value={mode}
            onChange={(v) => setMode(v)}
            options={[
              { value: "all", label: "All of them" },
              { value: "any", label: "Any of them" },
            ]}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <Button type="submit" loading={busy === "save"}>
            Save guardrails
          </Button>
          <Button type="button" variant="ghost" onClick={reset} loading={busy === "reset"}>
            Clear all rules
          </Button>
          <p className="text-micro text-fg-faint">
            Prices in {value.currency}. Saved in the Brand workspace; empty fields are not checked. Saving re-checks any
            open hand-off.
          </p>
        </div>
      </div>
      <div className="flex flex-col items-center self-start rounded-panel border border-line bg-surface px-5 pt-8 pb-6">
        <Dial
          size="md"
          label="Gross margin"
          value={reading?.value ?? null}
          floor={floorOk ? { value: floor as number, label: `Floor ${floor}%` } : undefined}
          format={(n) => `${Math.round(n)}%`}
          caption={reading ? reading.label : "no quote to read yet"}
        />
        <p className="mt-3 text-center text-micro text-fg-muted">
          {floorOk
            ? `A quote below ${floor}% margin stops the run and asks you.`
            : "No margin floor: margin is not checked."}
        </p>
      </div>
    </form>
  );
}
