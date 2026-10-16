"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  buttonClass,
  Card,
  cx,
  DUR,
  EASE,
  Field,
  IconArrowDown,
  Input,
  Label,
  Select,
  Stat,
  StatGroup,
  Stitch,
  Swatch,
  Table,
  Tabs,
  TapeMeasure,
  TBody,
  Td,
  Th,
  THead,
  toast,
  Tr,
} from "@/components/ds";
import {
  errorMessage,
  getTechPackAlternatives,
  patchTechPack,
  techPackPdfUrl,
  type BillOfMaterialsItem,
  type BomAlternatives,
  type Guardrails,
  type PipelineRun,
  type TechPack,
} from "@/lib/api";
import { useDemoCommand } from "@/lib/demo";
import { useAtelier } from "@/lib/store";
import { Citations } from "./Citations";
import { CustomerEvidence } from "./CustomerEvidence";
import { currencySymbol, money, pct, runCurrency, SheetHeading, signedMoney } from "./Sheet";

interface Economics {
  unitCost: number;
  total: number;
  retail: number;
  margin: number;
  breakEven: number;
  quantity: number;
}

export function economics(bom: BillOfMaterialsItem[], retail: number, quantity: number): Economics {
  const unitCost = bom.reduce((s, m) => s + (Number(m.targetCostPerUnit) || 0), 0);
  const margin = retail > 0 ? (retail - unitCost) / retail : 0;
  const total = unitCost * quantity;
  return {
    unitCost,
    total,
    retail,
    margin,
    quantity,
    breakEven: retail > 0 ? Math.ceil(total / retail) : 0,
  };
}

/** "Grade-A cashmere - shell, colour Sand" -> "Grade-A cashmere". */
const head = (material: string) => material.split(/\s+[-–\u2014]\s+/)[0];

const sameBom = (a: BillOfMaterialsItem[], b: BillOfMaterialsItem[]) =>
  a.length === b.length &&
  a.every((m, i) => m.material === b[i].material && m.targetCostPerUnit === b[i].targetCostPerUnit);

type Tab = "bom" | "measurements" | "construction" | "colourway" | "evidence" | "sources";

/**
 * The cost limit a unit cost is read against: the brand's cap (set, or derived for this run) and the margin floor at
 * the current retail price, whichever is lower. Nothing here is invented: every limit comes from the Brand workspace.
 */
function costLimit(
  guardrails: Guardrails | null | undefined,
  run: PipelineRun,
  retail: number,
  costing: number,
): { value: number; label: string; why: string } | null {
  const g = guardrails ?? run.guardrailReport?.guardrails;
  if (!g) return null;
  const ccy = g.currency;
  const limits: { value: number; label: string; why: string }[] = [];
  if (g.maxUnitCost)
    limits.push({ value: g.maxUnitCost, label: "Cost cap", why: `brand cap ${money(g.maxUnitCost, ccy)}` });
  else if (run.guardrailReport?.maxUnitCostDerived && run.guardrailReport.guardrails.maxUnitCost)
    limits.push({
      value: run.guardrailReport.guardrails.maxUnitCost,
      label: "Auto cap",
      why: `auto cap ${money(run.guardrailReport.guardrails.maxUnitCost, ccy)} (costing + ${g.costHeadroomPct ?? "?"}%)`,
    });
  else if (g.costHeadroomPct != null && costing > 0) {
    const v = costing * (1 + g.costHeadroomPct / 100);
    limits.push({
      value: v,
      label: "Auto cap",
      why: `auto cap = saved costing ${money(costing, ccy)} + ${g.costHeadroomPct}%`,
    });
  }
  if (g.minGrossMarginPct != null && retail > 0) {
    const v = retail * (1 - g.minGrossMarginPct / 100);
    limits.push({
      value: v,
      label: "Margin floor",
      why: `${g.minGrossMarginPct}% margin floor at ${money(retail, ccy)} retail`,
    });
  }
  if (!limits.length) return null;
  return limits.reduce((a, b) => (b.value < a.value ? b : a));
}

/** Mounted with key = `${run.id}:${run.techPackRevision}` so a saved revision resets the draft. */
export function TechPackEditor({ run, guardrails }: { run: PipelineRun; guardrails?: Guardrails | null }) {
  const techPack = run.techPack as TechPack;
  const baseline = run.originalTechPack ?? techPack;
  const ccy = runCurrency(run); // every price on the tech pack is in the brand currency
  const updateRun = useAtelier((s) => s.updateRun);

  const [bom, setBom] = useState<BillOfMaterialsItem[]>(techPack.billOfMaterials);
  const [retail, setRetail] = useState(String(techPack.targetRetailPrice));
  const [quantity, setQuantity] = useState(String(techPack.productionQuantity));
  const [alternatives, setAlternatives] = useState<Record<number, BomAlternatives>>({});
  const [priceList, setPriceList] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("bom");
  const [save, setSave] = useState<{ status: "idle" | "saving" | "saved" | "error"; error?: string }>({
    status: (run.techPackRevision ?? 0) > 0 ? "saved" : "idle",
  });

  useEffect(() => {
    let live = true;
    getTechPackAlternatives(run.id)
      .then((res) => {
        if (!live) return;
        setAlternatives(Object.fromEntries(res.lines.map((l) => [l.index, l])));
        setPriceList(res.priceListDated ? `Swaps costed from your price list dated ${res.priceListDated}` : null);
      })
      .catch(() => {
        /* swaps are optional; the sheet still works without them */
      });
    return () => {
      live = false;
    };
  }, [run.id]);

  const retailN = Math.max(0, Number(retail) || 0);
  const qtyN = Math.max(1, Math.round(Number(quantity) || 0));
  const now = useMemo(() => economics(bom, retailN, qtyN), [bom, retailN, qtyN]);
  const orig = useMemo(
    () => economics(baseline.billOfMaterials, baseline.targetRetailPrice, baseline.productionQuantity),
    [baseline],
  );
  const saved = useMemo(
    () => economics(techPack.billOfMaterials, techPack.targetRetailPrice, techPack.productionQuantity),
    [techPack],
  );
  const dirty =
    !sameBom(bom, techPack.billOfMaterials) ||
    retailN !== techPack.targetRetailPrice ||
    qtyN !== techPack.productionQuantity;
  const changedVsOriginal =
    !sameBom(bom, baseline.billOfMaterials) ||
    retailN !== baseline.targetRetailPrice ||
    qtyN !== baseline.productionQuantity;
  const valid = Number(retail) > 0 && Number(quantity) >= 1;
  const poIssued = !!run.demand?.purchaseOrder;

  const swap = (index: number, material: string) => {
    const option = alternatives[index]?.options.find((o) => o.material === material);
    if (!option) return;
    setBom((cur) =>
      cur.map((m, i) =>
        i === index ? { ...m, material: option.material, targetCostPerUnit: option.targetCostPerUnit } : m,
      ),
    );
    setSave({ status: "idle" });
  };

  const resetToAgent = () => {
    setBom(baseline.billOfMaterials);
    setRetail(String(baseline.targetRetailPrice));
    setQuantity(String(baseline.productionQuantity));
    setSave({ status: "idle" });
  };

  const persist = async () => {
    setSave({ status: "saving" });
    try {
      const updated = await patchTechPack(run.id, {
        billOfMaterials: bom,
        targetRetailPrice: retailN,
        productionQuantity: qtyN,
      });
      toast(`Tech pack saved as rev ${String(updated.techPackRevision ?? 0).padStart(2, "0")}`, {
        description: "The PDF and the quote scoring use this revision.",
      });
      updateRun(updated); // remounts this editor on the new revision
    } catch (err) {
      setSave({ status: "error", error: errorMessage(err) });
    }
  };

  // Demo mode swaps one material and saves, through the same handlers as the select and the save button.
  useDemoCommand((c) => {
    if (c.type === "swap-material") swap(c.index, c.material);
    else if (c.type === "save-techpack" && dirty && valid) void persist();
  });

  const unitDelta = now.unitCost - orig.unitCost;
  const measurements = Object.entries(techPack.measurements);
  const rev = run.techPackRevision ?? 0;
  const limit = costLimit(guardrails, run, retailN, saved.unitCost);
  const over = limit ? now.unitCost > limit.value + 1e-9 : false;
  const scaleMax = niceMax(Math.max(now.unitCost, orig.unitCost, limit?.value ?? 0) * 1.25);
  const evidence = techPack.customerEvidence ?? [];
  const sources = techPack.citations ?? [];
  const construction = techPack.constructionNotes ?? [];
  const colourway = techPack.colorway ?? [];

  const tabs = [
    { value: "bom" as const, label: "Bill of materials", count: bom.length },
    {
      value: "measurements" as const,
      label: "Measurements",
      count: measurements.length,
      disabled: measurements.length === 0,
    },
    {
      value: "construction" as const,
      label: "Construction",
      count: construction.length,
      disabled: construction.length === 0,
    },
    { value: "colourway" as const, label: "Colourway", count: colourway.length, disabled: colourway.length === 0 },
    { value: "evidence" as const, label: "Customer evidence", count: evidence.length, disabled: evidence.length === 0 },
    { value: "sources" as const, label: "Sources", count: sources.length, disabled: sources.length === 0 },
  ];

  return (
    <Card as="article" pad="lg" data-demo="techpack">
      <SheetHeading
        kicker={[
          "Tech pack",
          run.styleNumber ? `style ${run.styleNumber}` : null,
          rev > 0 ? `rev ${String(rev).padStart(2, "0")}` : "agent draft",
        ]
          .filter(Boolean)
          .join(" · ")}
        tone={rev > 0 ? "ok" : "accent"}
        title={techPack.garmentName}
        lede={techPack.description}
        route={techPack.generatedBy}
        aside={
          <a
            href={techPackPdfUrl(run.id, rev)}
            download
            data-demo="pdf"
            className={buttonClass({ variant: "secondary", size: "sm" })}
          >
            <IconArrowDown size={14} /> Download PDF
          </a>
        }
      />

      {/* Live costing */}
      <section
        data-demo="costing"
        aria-label="Live costing"
        className="grid grid-cols-1 gap-6 rounded-panel bg-paper-2/60 p-4 sm:p-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] xl:gap-10"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <Label as="p">Unit cost against the guardrails</Label>
            {limit ? (
              <Badge tone={over ? "bad" : "ok"}>
                {over
                  ? `Over by ${money(now.unitCost - limit.value, ccy)}`
                  : `${money(limit.value - now.unitCost, ccy)} headroom`}
              </Badge>
            ) : (
              <Badge tone="faint">No cost guardrail</Badge>
            )}
          </div>
          <TapeMeasure
            className="mt-2"
            label="Landed unit cost"
            min={0}
            max={scaleMax}
            value={now.unitCost}
            format={(n) => money(n, ccy, 0)}
            readout={money(now.unitCost, ccy)}
            tone={limit ? (over ? "bad" : "ok") : "accent"}
            target={limit ? { from: 0, to: limit.value } : undefined}
            majorStep={niceStep(scaleMax, 4)}
            markers={[
              ...(limit ? [{ value: limit.value, label: limit.label, tone: "bad" as const }] : []),
              ...(changedVsOriginal && Math.abs(unitDelta) >= 0.005
                ? [{ value: orig.unitCost, label: "Agent draft" }]
                : []),
            ]}
          />
          <p className="mt-3 text-micro text-fg-muted" aria-live="polite">
            {limit
              ? `Shaded = within the guardrails. Limit: ${limit.why}.`
              : "No unit-cost cap or margin floor is set in the Brand workspace, so the cost isn't judged."}{" "}
            {changedVsOriginal
              ? `${signedMoney(unitDelta, ccy)}/unit vs the agent draft · margin ${pct(orig.margin)} → ${pct(now.margin)}.`
              : "Agent draft - swap a material or edit price and quantity."}
          </p>
          <div className="mt-5 grid grid-cols-2 gap-4 sm:max-w-md">
            <Field label="Quantity">
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                step={50}
                suffix="units"
                value={quantity}
                onChange={(e) => {
                  setQuantity(e.target.value);
                  setSave({ status: "idle" });
                }}
              />
            </Field>
            <Field label="Retail price">
              <Input
                type="number"
                inputMode="decimal"
                min={1}
                step={5}
                prefix={currencySymbol(ccy) || undefined}
                value={retail}
                onChange={(e) => {
                  setRetail(e.target.value);
                  setSave({ status: "idle" });
                }}
              />
            </Field>
          </div>
        </div>
        <StatGroup className="content-start self-center sm:gap-y-8 xl:grid xl:grid-cols-2 xl:gap-x-8 xl:*:border-l-0 xl:*:pl-0">
          <Stat
            size="sm"
            label="Unit cost"
            count={now.unitCost}
            format={(n) => money(n, ccy)}
            delta={Math.abs(unitDelta) >= 0.005 ? signedMoney(unitDelta, ccy) : undefined}
            deltaTone={unitDelta < 0 ? "ok" : "bad"}
          />
          <Stat
            size="sm"
            label="Gross margin"
            count={now.margin * 100}
            format={(n) => `${n.toFixed(0)}%`}
            delta={Math.abs(now.margin - orig.margin) >= 0.005 ? `${pct(orig.margin)} → ${pct(now.margin)}` : undefined}
            deltaTone={now.margin > orig.margin ? "ok" : "bad"}
          />
          <Stat
            size="sm"
            label="Production cost"
            count={now.total}
            format={(n) => money(n, ccy, 0)}
            delta={Math.abs(now.total - orig.total) >= 1 ? signedMoney(now.total - orig.total, ccy, 0) : undefined}
            deltaTone={now.total < orig.total ? "ok" : "bad"}
            caption={`${money(now.unitCost, ccy)} × ${qtyN.toLocaleString("en-US")}`}
          />
          <Stat
            size="sm"
            label="Break-even"
            count={now.breakEven}
            format={(n) => `${Math.round(n).toLocaleString("en-US")}`}
            unit="units"
            delta={
              now.breakEven !== orig.breakEven
                ? `${now.breakEven < orig.breakEven ? "−" : "+"}${Math.abs(now.breakEven - orig.breakEven).toLocaleString("en-US")} units`
                : undefined
            }
            deltaTone={now.breakEven < orig.breakEven ? "ok" : "bad"}
            caption={`production cost ÷ ${money(now.retail, ccy, 0)} retail`}
          />
        </StatGroup>
      </section>

      <Tabs
        className="mt-8"
        label="Tech pack sections"
        value={tab}
        onChange={setTab}
        items={tabs.map((t) => ({
          ...t,
          content:
            t.value === "bom" ? (
              <div className="min-w-0" data-demo="bom">
                {priceList && <p className="mb-3 text-micro text-fg-faint">{priceList}</p>}
                <Table caption="Bill of materials">
                  <THead>
                    <Tr>
                      <Th>Material</Th>
                      <Th>Qty</Th>
                      <Th numeric>Cost / unit</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {bom.map((m, i) => {
                      const alt = alternatives[i];
                      const base = baseline.billOfMaterials[i];
                      const delta = base ? m.targetCostPerUnit - base.targetCostPerUnit : 0;
                      const swapped = base && m.material !== base.material;
                      return (
                        <Tr key={i} selected={!!swapped}>
                          <Td className="min-w-[14rem]">
                            {alt ? (
                              <MaterialSelect
                                alt={alt}
                                value={m.material}
                                onChange={(v) => swap(i, v)}
                                label={`Material for line ${i + 1}`}
                                currency={ccy}
                              />
                            ) : (
                              <span className="break-words">{m.material}</span>
                            )}
                          </Td>
                          <Td className="font-mono text-[0.78rem] whitespace-nowrap text-fg-muted">{m.quantity}</Td>
                          <Td numeric>
                            {money(m.targetCostPerUnit, ccy)}
                            {Math.abs(delta) >= 0.005 && (
                              <span className={cx("block text-micro", delta < 0 ? "text-ok" : "text-bad")}>
                                {signedMoney(delta, ccy)}
                              </span>
                            )}
                          </Td>
                        </Tr>
                      );
                    })}
                  </TBody>
                  <tfoot className="border-t border-line-strong bg-paper-2/40">
                    <tr>
                      <td colSpan={2} className="py-3 pl-5 text-small font-medium text-fg">
                        Total per garment
                        <span className="block text-micro font-normal text-fg-faint">
                          × {qtyN.toLocaleString("en-US")} units = {money(now.total, ccy, 0)}
                        </span>
                      </td>
                      <td className="py-3 pr-5 text-right font-mono text-body text-fg tabular">
                        {money(now.unitCost, ccy)}
                      </td>
                    </tr>
                  </tfoot>
                </Table>
                {Object.keys(alternatives).length === 0 && (
                  <p className="mt-3 text-micro text-fg-faint">
                    No material swaps: they come from the price list in the Brand workspace, and none matches these
                    lines.
                  </p>
                )}
              </div>
            ) : t.value === "measurements" ? (
              <Table caption="Measurements" className="max-w-2xl">
                <THead>
                  <Tr>
                    <Th>Point of measure</Th>
                    <Th numeric>Value</Th>
                  </Tr>
                </THead>
                <TBody>
                  {measurements.map(([k, v]) => (
                    <Tr key={k}>
                      <Td className="first-letter:uppercase">{k.replace(/[_-]/g, " ")}</Td>
                      <Td numeric>{v}</Td>
                    </Tr>
                  ))}
                </TBody>
              </Table>
            ) : t.value === "construction" ? (
              <ol className="flex max-w-3xl flex-col">
                {construction.map((n, i) => (
                  <li
                    key={`${i}-${n}`}
                    className="flex gap-4 border-t border-line py-3 text-body text-fg first:border-t-0"
                  >
                    <span className="w-6 shrink-0 font-mono text-micro leading-6 text-fg-faint">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    {n}
                  </li>
                ))}
              </ol>
            ) : t.value === "colourway" ? (
              <div>
                <ul className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6" aria-label="Colourway">
                  {colourway.map((c, i) => (
                    <li key={`${c}-${i}`}>
                      <Swatch color={c} name={`Colour ${i + 1}`} code={c} />
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-micro text-fg-faint">
                  The effective colourway: the trend palette after any creative direction re-coloured it.
                </p>
              </div>
            ) : t.value === "evidence" ? (
              <CustomerEvidence items={evidence} />
            ) : (
              <Citations items={sources} />
            ),
        }))}
      />

      <Stitch label="Agent draft → your edits" className="mt-10" />
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button onClick={persist} disabled={!dirty || !valid} loading={save.status === "saving"}>
          {save.status === "saving" ? "Saving…" : "Save to tech pack"}
        </Button>
        {changedVsOriginal && (
          <Button variant="ghost" onClick={resetToAgent}>
            Reset to agent draft
          </Button>
        )}
        <AnimatePresence mode="wait">
          <motion.p
            key={save.status + (dirty ? "d" : "")}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: DUR.ui, ease: EASE }}
            className={cx("text-small", save.status === "error" ? "text-bad" : "text-fg-muted")}
            role={save.status === "error" ? "alert" : undefined}
          >
            {save.status === "error"
              ? save.error
              : dirty
                ? "Unsaved - the PDF and supplier quotes use the saved version."
                : save.status === "saved"
                  ? poIssued
                    ? `Saved as rev ${String(rev).padStart(2, "0")} · PO already drafted, quotes locked.`
                    : `Saved as rev ${String(rev).padStart(2, "0")} · quotes re-scored (the mills’ prices stay as quoted).`
                  : ""}
          </motion.p>
        </AnimatePresence>
      </div>
    </Card>
  );
}

/** A round tick step giving about `n` numbered ticks (keeps the tape legible on a phone). */
function niceStep(max: number, n: number): number {
  const raw = max / n;
  const p = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}

/** A round scale end for the tape (1, 2, 2.5 or 5 × 10ⁿ). */
function niceMax(v: number): number {
  if (!(v > 0)) return 10;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function MaterialSelect({
  alt,
  value,
  onChange,
  label,
  currency,
}: {
  currency?: string;
  alt: BomAlternatives;
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const current = alt.options.find((o) => o.material === value);
  const original = alt.options.find((o) => o.original);
  return (
    <div className="min-w-0">
      <Select
        aria-label={label}
        value={current ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 text-small"
      >
        {!current && <option value="">{value}</option>}
        {alt.options.map((o) => {
          const d = original ? o.targetCostPerUnit - original.targetCostPerUnit : 0;
          return (
            <option key={o.material} value={o.material}>
              {head(o.material)} · {money(o.targetCostPerUnit, currency)}
              {o.original ? " (agent pick)" : ` (${signedMoney(d, currency)})`}
            </option>
          );
        })}
      </Select>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-micro text-fg-faint">
        <span className="text-fg-muted">{alt.family}</span>
        {current && (
          <>
            <span>· {current.note}</span>
            {current.tag && <Badge tone="ok">{current.tag}</Badge>}
          </>
        )}
      </p>
    </div>
  );
}
