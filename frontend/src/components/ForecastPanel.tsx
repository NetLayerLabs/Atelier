"use client";

import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  cx,
  Disclosure,
  FanChart,
  Field,
  Input,
  InlineAlert,
  Label,
  ProgressBar,
  Ring,
  Skeleton,
  Stat,
  StatGroup,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  type FanPoint,
} from "@/components/ds";
import {
  errorMessage,
  getRunForecast,
  postForecast,
  type Forecast,
  type ForecastAssumptions,
  type ForecastSizeLine,
  type PipelineRun,
} from "@/lib/api";
import { int, KeyValues, money, OutlineBadge, pct, SheetHeading, signedMoney } from "./Sheet";

/**
 * "How many should we make?" - the explained production forecast (CONTRACT.md "v3").
 * Polls GET /api/runs/{id}/forecast while pre-orders are coming in; assumption tweaks recompute via POST /api/forecast.
 */

const POLL_MS = 2500;

/** Edited model parameters (every assumption) + the clearance value per unsold unit (economics.salvageValue). */
type Overrides = Partial<ForecastAssumptions> & { salvageValue?: number };

/** Defaults as documented in CONTRACT.md (used only to fill an input before the backend echoes the value). */
const DEFAULTS: ForecastAssumptions = {
  priorMeanPreorders: 250,
  priorCv: 0.75,
  bassP: 0.06,
  bassQ: 0.25,
  seasonMultiplier: 2.5,
  sizeCurve: { XS: 0.08, S: 0.22, M: 0.32, L: 0.24, XL: 0.14 },
  sizePriorStrength: 20,
  unsoldRiskThreshold: 0.2,
  levelCvFloor: 0.12,
  minExposure: 0.05,
  minWindowShareElapsed: 0.1,
  minOrders: 5,
};

/** Every editable scalar assumption, with the backend's validation bounds. */
const FIELDS: {
  key: Exclude<keyof ForecastAssumptions, "sizeCurve">;
  label: string;
  note: string;
  min: number;
  max: number;
  step: number;
}[] = [
  {
    key: "priorMeanPreorders",
    label: "Prior mean pre-orders (m₀)",
    note: "units a comparable launch takes in the window",
    min: 1,
    max: 1_000_000,
    step: 1,
  },
  {
    key: "priorCv",
    label: "Prior uncertainty (CV)",
    note: "how unsure we are about m₀",
    min: 0.06,
    max: 5,
    step: 0.05,
  },
  { key: "bassP", label: "Bass p · innovation / day", note: "the launch spike", min: 0.001, max: 5, step: 0.01 },
  { key: "bassQ", label: "Bass q · imitation / day", note: "word of mouth", min: 0, max: 5, step: 0.01 },
  {
    key: "seasonMultiplier",
    label: "Season ÷ window pre-orders (M)",
    note: "full-season demand per pre-order",
    min: 1,
    max: 50,
    step: 0.1,
  },
  {
    key: "sizePriorStrength",
    label: "Size-curve strength (κ)",
    note: "pseudo-orders behind the size curve",
    min: 0,
    max: 100_000,
    step: 1,
  },
  {
    key: "unsoldRiskThreshold",
    label: "Unsold-risk threshold",
    note: "share of the run reported as risk (0–1)",
    min: 0.01,
    max: 0.99,
    step: 0.01,
  },
  {
    key: "levelCvFloor",
    label: "Model-uncertainty floor",
    note: "minimum CV on the demand level",
    min: 0,
    max: 2,
    step: 0.01,
  },
  {
    key: "minExposure",
    label: "Early-window exposure floor",
    note: "G(t) counts as at least this share of a window",
    min: 0,
    max: 1,
    step: 0.01,
  },
  {
    key: "minWindowShareElapsed",
    label: "Evidence: window elapsed",
    note: "share of the window before recommending (0–1)",
    min: 0,
    max: 1,
    step: 0.01,
  },
  { key: "minOrders", label: "Evidence: orders", note: "orders in before recommending", min: 0, max: 100_000, step: 1 },
];

const CONFIDENCE: Record<Forecast["confidence"], string> = {
  "prior-only": "Prior only",
  early: "Early read",
  firming: "Firming up",
  "data-driven": "Data-driven",
};

export function ForecastPanel({ run }: { run: PipelineRun }) {
  const [base, setBase] = useState<Forecast | null>(null);
  const [tweaked, setTweaked] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState<Overrides>({});
  const [busy, setBusy] = useState(false);

  const collecting = run.demand?.status === "collecting";
  // Refetch whenever something the forecast reads changes; keep polling while orders arrive.
  const inputsKey = [
    run.demand?.status,
    run.demand?.orders,
    run.techPackRevision ?? 0,
    run.recommendation?.selectedSupplierName ?? "",
    run.shopifyProduct?.price ?? "",
  ].join("|");

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const f = await getRunForecast(run.id);
        if (alive) {
          setBase(f);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(errorMessage(err));
      }
      if (alive && collecting) timer = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [run.id, collecting, inputsKey]);

  const hasOver = Object.keys(over).length > 0;

  useEffect(() => {
    if (!base || !hasOver) return;
    let alive = true;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const inputs = base.inputs;
        const { salvageValue, ...assumptions } = over;
        const f = await postForecast({
          ...inputs,
          economics: {
            ...inputs.economics,
            ...(salvageValue !== undefined ? { salvageValue } : {}),
          },
          assumptions: { ...inputs.assumptions, ...assumptions },
        });
        if (alive) {
          setTweaked(f);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(errorMessage(err));
      } finally {
        if (alive) setBusy(false);
      }
    }, 300);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [base, over, hasOver]);

  const f = hasOver ? (tweaked ?? base) : base;

  if (!f) {
    return (
      <Card as="section" pad="lg" data-demo="forecast" aria-busy={!error || undefined}>
        <SheetHeading kicker="Production forecast" title="How many should we make?" />
        {error ? (
          <InlineAlert tone="bad" title="The forecast couldn't be computed">
            {error}
          </InlineAlert>
        ) : (
          <div className="flex flex-col gap-3" aria-label="Loading forecast">
            <Skeleton className="h-56 w-full rounded-panel" />
            <p className="text-small text-fg-muted">Fitting the launch curve to the real pre-orders…</p>
          </div>
        )}
      </Card>
    );
  }

  const o = f.outcome;
  const current: ForecastAssumptions = { ...DEFAULTS, ...(base?.inputs.assumptions ?? {}), ...over };
  const salvage = over.salvageValue ?? f.salvageValue;
  const risk = f.inputs.assumptions?.unsoldRiskThreshold ?? current.unsoldRiskThreshold;
  const noOrders = f.explanation.data.orderEvents === 0;
  const tooEarly = f.recommendationStatus === "too_early";
  const days = Math.round(f.explanation.data.windowHours / 24);
  const ev = f.evidence;
  const threshold = run.demand?.threshold;

  return (
    <Card as="section" pad="lg" data-demo="forecast" aria-busy={busy || undefined}>
      <SheetHeading
        kicker="Production forecast · newsvendor"
        tone={tooEarly ? "warn" : "accent"}
        title="How many should we make?"
        aside={
          <>
            <span title="Closed-form statistics - no language model is used in this calculation">
              <Badge tone="neutral">No LLM · exact maths</Badge>
            </span>
            {noOrders && <Badge tone="faint">No orders yet</Badge>}
            {busy && <Badge status="running">Recomputing</Badge>}
          </>
        }
      />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
        {/* Recommendation + confidence */}
        <div className="flex min-w-0 flex-col gap-6">
          <div className="rounded-panel bg-paper-2/60 p-5 sm:p-6">
            <Label as="p">Recommendation</Label>
            {tooEarly ? (
              <>
                <p className="mt-3 text-display-m text-fg" aria-live="polite">
                  Too early to recommend
                </p>
                <p className="mt-3 text-small text-fg-muted">
                  The plan stands at <span className="font-mono text-fg">{int(f.recommendedQuantity)}</span> units until
                  there is enough evidence. Nothing below is a recommendation yet.
                </p>
                {ev && (
                  <div className="mt-5 flex flex-col gap-4">
                    <ProgressBar
                      value={ev.minOrders > 0 ? Math.min(1, ev.orders / ev.minOrders) : null}
                      label="Orders in"
                      detail={`${int(ev.orders)} of ${int(ev.minOrders)}`}
                      tone={ev.orders >= ev.minOrders ? "ok" : "accent"}
                    />
                    <ProgressBar
                      value={
                        ev.minWindowShareElapsed > 0
                          ? Math.min(1, ev.windowShareElapsed / ev.minWindowShareElapsed)
                          : null
                      }
                      label="Window elapsed"
                      detail={`${pct(ev.windowShareElapsed, 1)} of ${pct(ev.minWindowShareElapsed)}`}
                      tone={ev.windowShareElapsed >= ev.minWindowShareElapsed ? "ok" : "accent"}
                    />
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="mt-3" aria-live="polite">
                  <Stat size="lg" label="units to make" count={f.recommendedQuantity} format={(n) => int(n)} />
                </div>
                <p className="mt-4 text-small leading-relaxed text-fg-muted">
                  Stocks to the <span className="font-medium text-fg">{pct(f.criticalRatio)}</span> quantile of
                  full-season demand. The last unit made sells with a {pct(1 - f.criticalRatio)} chance: there, its
                  expected margin ({money(f.underageCost, f.currency, 0)} × {pct(1 - f.criticalRatio)}) equals its
                  expected clearance loss ({money(f.overageCost, f.currency, 0)} × {pct(f.criticalRatio)}).
                </p>
              </>
            )}
            {f.moqBinding && f.moqNote && (
              <p className="mt-4 rounded-panel bg-accent-soft px-4 py-3 text-small text-fg">{f.moqNote}</p>
            )}
          </div>

          <div className="flex items-center gap-5">
            <Ring
              value={f.posterior.dataWeight}
              label="Weight on your data"
              size={128}
              tone={f.confidence === "data-driven" ? "ok" : f.confidence === "prior-only" ? "warn" : "accent"}
              display={`${Math.round(f.posterior.dataWeight * 100)}%`}
              caption="on your data"
            />
            <div className="min-w-0">
              <Badge tone={f.confidence === "data-driven" ? "ok" : f.confidence === "prior-only" ? "warn" : "accent"}>
                {CONFIDENCE[f.confidence]}
              </Badge>
              <p className="mt-2 text-small leading-relaxed text-fg-muted">
                {noOrders && <span className="text-fg">No orders yet - this rests on the assumptions alone. </span>}
                {f.confidenceNote}
              </p>
              <p className="mt-1 text-micro text-fg-faint">
                The ring is the posterior weight on the real orders vs the prior.
              </p>
            </div>
          </div>
        </div>

        {/* Projection fan */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <Label as="p">Projected pre-orders over the window</Label>
            <p className="font-mono text-micro text-fg-muted">
              by day {days}: {int(f.preorders.mean)} · 80% {int(f.preorders.p10)}–{int(f.preorders.p90)}
            </p>
          </div>
          <FanChart
            className="mt-4"
            height={240}
            points={fanPoints(f)}
            threshold={threshold != null ? { value: threshold, label: "Threshold" } : undefined}
            format={(n) => int(n)}
            label={`Projected pre-orders by day ${days}: mean ${Math.round(f.preorders.mean)}, 80% interval ${f.preorders.p10} to ${f.preorders.p90}; ${f.observedUnits} observed so far`}
          />
          <p className="mt-3 text-micro text-fg-faint">
            Observed = real Shopify units so far (now: day {(f.explanation.data.elapsedHours / 24).toFixed(1)}). Median
            and the 80% band are the Gamma–Poisson posterior on the Bass launch curve.
          </p>
        </div>
      </div>

      <div className="mt-10 border-t border-line pt-8">
        <Label as="p" className="mb-5">
          {tooEarly
            ? `Outcome at the planned ${int(f.recommendedQuantity)} units - not a recommendation yet`
            : `Expected outcome at ${int(f.recommendedQuantity)} units`}
        </Label>
        <StatGroup>
          <Stat
            size="sm"
            label="Season demand"
            count={f.season.mean}
            format={(n) => int(n)}
            caption={`80%: ${int(f.season.p10)}–${int(f.season.p90)}`}
          />
          <Stat
            size="sm"
            label="Expected profit"
            count={o.expectedProfit}
            format={(n) => money(n, f.currency, 0)}
            caption={`${pct(o.expectedMargin, 1)} margin`}
          />
          <Stat
            size="sm"
            label="Expected revenue"
            count={o.expectedRevenue}
            format={(n) => money(n, f.currency, 0)}
            caption={`${int(o.expectedUnitsSold)} sold at ${money(f.retailPrice, f.currency, 0)}`}
          />
          <Stat
            size="sm"
            label={`Risk unsold > ${pct(risk)}`}
            count={o.unsoldRiskProbability * 100}
            format={(n) => `${n.toFixed(0)}%`}
            caption={`≈${int(o.expectedLeftover)} left over · ${pct(o.stockoutProbability)} stock-out`}
          />
        </StatGroup>
      </div>

      {f.baseline && f.profitDeltaVsBaseline !== undefined && f.baseline.quantity !== f.recommendedQuantity && (
        <p className="mt-6 text-small text-fg-muted">
          Against the planned run of <span className="font-mono text-fg">{int(f.baseline.quantity)}</span>:{" "}
          <span className={f.profitDeltaVsBaseline >= 0 ? "text-ok" : "text-bad"}>
            {signedMoney(f.profitDeltaVsBaseline, f.currency, 0)}
          </span>{" "}
          expected profit ({money(f.baseline.expectedProfit, f.currency, 0)} → {money(o.expectedProfit, f.currency, 0)}
          ), with {int(f.baseline.expectedLeftover)} → {int(o.expectedLeftover)} units expected left over.
        </p>
      )}

      <div className="mt-10">
        <SizeSplit
          sizes={f.sizes}
          total={f.recommendedQuantity}
          sized={f.explanation.data.sizedUnits}
          sizedOrders={f.explanation.data.sizedOrders}
        />
      </div>

      {error && (
        <InlineAlert tone="bad" title="Recompute failed" className="mt-6">
          {error}
        </InlineAlert>
      )}

      <div className="mt-10 flex flex-col gap-3">
        <HowCalculated f={f} />
        <Disclosure
          title={
            <>
              <span className="block">Adjust the model&rsquo;s assumptions</span>
              <span className="block text-small font-normal text-fg-muted">
                Model parameters, not data - fit them to the brand&rsquo;s own past launches. Editing one re-runs the
                forecast with the same orders.
              </span>
            </>
          }
          meta={hasOver ? <Badge tone="accent">Edited</Badge> : <Badge tone="faint">Defaults</Badge>}
        >
          <Slider
            label="Clearance value per unsold unit"
            value={salvage}
            min={0}
            max={Math.max(1, Math.floor(f.unitCost * 0.99))}
            step={1}
            display={`${money(salvage, f.currency)} · ${pct(salvage / f.unitCost)} of cost`}
            onChange={(v) => setOver((s) => ({ ...s, salvageValue: v }))}
          />
          <div className="mt-6 grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            {FIELDS.map((fd) => (
              <NumberField
                key={fd.key}
                label={fd.label}
                note={fd.note}
                value={current[fd.key]}
                min={fd.min}
                max={fd.max}
                step={fd.step}
                onChange={(v) => setOver((s) => ({ ...s, [fd.key]: v }))}
              />
            ))}
          </div>
          <SizeCurveEditor curve={current.sizeCurve} onChange={(sizeCurve) => setOver((s) => ({ ...s, sizeCurve }))} />
          {hasOver && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-5"
              onClick={() => {
                setOver({});
                setTweaked(null);
              }}
            >
              Reset to the defaults
            </Button>
          )}
        </Disclosure>
      </div>
    </Card>
  );
}

/** The projection on the FanChart's grid; "observed" = real cumulative units at each point up to now. */
function fanPoints(f: Forecast): FanPoint[] {
  const now = f.explanation.data.elapsedHours;
  const obs = [...f.observed].sort((a, b) => a.hour - b.hour);
  const at = (h: number) => {
    let u: number | undefined;
    for (const p of obs) if (p.hour <= h) u = p.units;
    return u ?? (obs.length || h <= now ? 0 : undefined);
  };
  return f.projection.map((p) => ({
    x: `d${Math.round(p.hour / 24)}`,
    p50: p.mean,
    lo: p.p10,
    hi: p.p90,
    actual: p.hour <= now + 1e-9 ? at(p.hour) : undefined,
  }));
}

function NumberField({
  label,
  note,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  note: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  const [text, setText] = useState(String(value));
  const [prev, setPrev] = useState(value);
  if (value !== prev) {
    setPrev(value);
    setText(String(value));
  }
  const commit = (raw: string) => {
    setText(raw);
    const n = Number(raw);
    if (raw.trim() !== "" && Number.isFinite(n) && n >= min && n <= max) onChange(n);
  };
  const n = Number(text);
  const invalid = text.trim() === "" || !Number.isFinite(n) || n < min || n > max;
  return (
    <Field label={label} hint={note} error={invalid ? `between ${min} and ${max}` : undefined}>
      <Input
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={text}
        onChange={(e) => commit(e.target.value)}
        className="font-mono"
      />
    </Field>
  );
}

/** Per-size weights of the base size curve (normalised by the backend). */
function SizeCurveEditor({
  curve,
  onChange,
}: {
  curve: Record<string, number>;
  onChange: (c: Record<string, number>) => void;
}) {
  const sizes = Object.keys(curve);
  const total = sizes.reduce((s, k) => s + (curve[k] || 0), 0);
  return (
    <div className="mt-6">
      <p className="text-small font-medium text-fg">Base size curve</p>
      <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
        {sizes.map((size) => (
          <label key={size} className="flex flex-col gap-1">
            <Label>{size}</Label>
            <Input
              type="number"
              min={0}
              step={0.01}
              value={curve[size]}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (!Number.isFinite(v) || v < 0) return;
                const next = { ...curve, [size]: v };
                if (Object.values(next).reduce((a, b) => a + b, 0) > 0) onChange(next);
              }}
              className="h-10 font-mono text-small"
            />
          </label>
        ))}
      </div>
      <p className="mt-1.5 text-micro text-fg-faint">
        weights per size{total > 0 && Math.abs(total - 1) > 0.001 ? ` · sum ${total.toFixed(2)}, normalised` : ""}
      </p>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-small font-medium text-fg">{label}</span>
        <span className="font-mono text-micro text-fg-muted">{display}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={Math.min(max, Math.max(min, value))}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-3 w-full accent-accent"
      />
    </label>
  );
}

function SizeSplit({
  sizes,
  total,
  sized,
  sizedOrders,
}: {
  sizes: ForecastSizeLine[];
  total: number;
  sized: number;
  sizedOrders?: number;
}) {
  const maxShare = Math.max(...sizes.map((s) => Math.max(s.share, s.baseShare)), 0.01);
  const nOrders = sizedOrders ?? sized;
  const source =
    sized > 0
      ? `from ${int(nOrders)} sized order${nOrders === 1 ? "" : "s"} (${int(sized)} unit${sized === 1 ? "" : "s"}) + base curve`
      : "base curve only - no sized orders yet";
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-title text-fg">Size split · {int(total)} units</p>
        <p className="font-mono text-micro text-fg-faint">{source}</p>
      </div>
      <Table caption="Size split">
        <THead>
          <Tr>
            <Th>Size</Th>
            <Th numeric>Ord.</Th>
            <Th className="w-1/2 min-w-[6rem]">
              Share<span className="hidden sm:inline"> · tick = base curve</span>
            </Th>
            <Th numeric>Units</Th>
          </Tr>
        </THead>
        <TBody>
          {sizes.map((s) => (
            <Tr key={s.size}>
              <Td className="font-mono">{s.size}</Td>
              <Td numeric>{s.orders > 0 ? int(s.orders) : <span className="text-fg-faint">-</span>}</Td>
              <Td>
                <div
                  className="flex items-center gap-3"
                  title={`share ${pct(s.share, 1)} · base curve ${pct(s.baseShare, 1)} · ${s.orders} ordered`}
                >
                  <div className="relative h-1.5 flex-1 rounded-full bg-paper-2">
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-accent"
                      style={{ width: `${(s.share / maxShare) * 100}%` }}
                    />
                    {s.baseShare > 0 && (
                      <span
                        aria-hidden
                        className="absolute -top-1.5 -bottom-1.5 w-px bg-fg"
                        style={{ left: `${(s.baseShare / maxShare) * 100}%` }}
                      />
                    )}
                  </div>
                  <span className="hidden w-12 text-right font-mono text-micro text-fg-muted sm:inline">
                    {pct(s.share, 1)}
                  </span>
                </div>
              </Td>
              <Td numeric>{int(s.units)}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function ProfitCurve({ f }: { f: Forecast }) {
  const W = 1200;
  const H = 220;
  const pad = 10;
  const pts = f.profitCurve;
  if (pts.length < 2) return null;
  const qMax = pts[pts.length - 1].quantity || 1;
  const vals = pts.map((p) => p.expectedProfit);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(...vals, 1);
  const x = (q: number) => pad + (q / qMax) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad);
  const d = `M ${pts.map((p) => `${x(p.quantity).toFixed(1)},${y(p.expectedProfit).toFixed(1)}`).join(" L ")}`;
  const q = f.recommendedQuantity;
  const planned = f.baseline?.quantity;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full overflow-visible"
      role="img"
      aria-label={`Expected profit by production quantity; peak near ${int(q)} units`}
    >
      {lo < 0 && (
        <line
          x1={pad}
          x2={W - pad}
          y1={y(0)}
          y2={y(0)}
          stroke="var(--line-bold)"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
      )}
      <line
        x1={pad}
        x2={W - pad}
        y1={H - pad}
        y2={H - pad}
        stroke="var(--line)"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      />
      <path d={d} fill="none" stroke="var(--fg)" strokeWidth="1.75" vectorEffect="non-scaling-stroke" />
      {planned !== undefined && planned !== q && planned <= qMax && (
        <g>
          <line
            x1={x(planned)}
            x2={x(planned)}
            y1={pad}
            y2={H - pad}
            stroke="var(--fg-faint)"
            strokeDasharray="3 4"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          <text x={x(planned) + 6} y={H - pad - 6} fontSize="20" fill="var(--fg-muted)" fontFamily="var(--font-mono)">
            planned {planned.toLocaleString("en-US")}
          </text>
        </g>
      )}
      <line
        x1={x(q)}
        x2={x(q)}
        y1={pad}
        y2={H - pad}
        stroke="var(--accent)"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={x(q)}
        cy={y(f.outcome.expectedProfit)}
        r="6"
        fill="var(--accent)"
        stroke="var(--surface)"
        strokeWidth="2"
      />
      <text
        x={x(q) + (x(q) > W * 0.7 ? -10 : 10)}
        y={pad + 18}
        textAnchor={x(q) > W * 0.7 ? "end" : "start"}
        fontSize="20"
        fill="var(--accent)"
        fontFamily="var(--font-mono)"
      >
        make {q.toLocaleString("en-US")}
      </text>
    </svg>
  );
}

function HowCalculated({ f }: { f: Forecast }) {
  const d = f.explanation.data;
  const span = d.spanHours >= 48 ? `${(d.spanHours / 24).toFixed(1)} days` : `${d.spanHours.toFixed(0)} hours`;
  const dataRows: [string, string][] = [
    ["Orders", `${int(d.orderEvents)} events · ${int(d.units)} units`],
    ["With a size", `${int(d.sizedUnits)} units${d.sizedOrders != null ? ` · ${int(d.sizedOrders)} orders` : ""}`],
    ["Time span", d.orderEvents ? span : "-"],
    ["Window elapsed", `${(d.elapsedHours / 24).toFixed(1)} of ${(d.windowHours / 24).toFixed(0)} days`],
    ["Launch curve says in by now", pct(d.windowShareElapsed)],
    ["Weight on your data", pct(f.posterior.dataWeight)],
    ...(d.avgOrderPrice !== undefined
      ? ([["Avg. order price", money(d.avgOrderPrice, f.currency)]] as [string, string][])
      : []),
    ["Unit cost (selected quote)", money(f.unitCost, f.currency)],
    ["Retail price", money(f.retailPrice, f.currency)],
    ["Supplier MOQ", int(f.moq)],
    ...(f.fixedCosts > 0
      ? ([["Fixed costs (sampling)", money(f.fixedCosts, f.currency, 0)]] as [string, string][])
      : []),
    ["Source", d.orderEvents ? "Shopify orders" : "No orders yet"],
  ];
  return (
    <>
      <Disclosure
        data-demo="forecast-explain"
        title={
          <>
            <span className="block">How this was calculated</span>
            <span className="block text-small font-normal text-fg-muted">
              Gamma–Poisson demand on a Bass launch curve, then the newsvendor rule. Every formula with its numbers.
            </span>
          </>
        }
        meta={<Badge tone="faint">{f.explanation.steps.length} steps</Badge>}
      >
        <p className="max-w-3xl text-body leading-relaxed text-fg">{f.explanation.summary}</p>
        <ol className="mt-5 flex flex-col">
          {f.explanation.steps.map((s, i) => (
            <li key={s.title} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 border-t border-line py-4">
              <span className="font-mono text-micro leading-6 text-fg-faint">{String(i + 1).padStart(2, "0")}</span>
              <div className="min-w-0">
                <p className="text-small font-medium text-fg">{s.title}</p>
                <p className="mt-2 rounded-chip bg-accent-soft px-3 py-2 font-mono text-[0.76rem] break-words text-accent">
                  {s.formula}
                </p>
                <p className="mt-1.5 font-mono text-[0.72rem] break-words text-fg-muted">{s.substituted}</p>
                <p className="mt-1.5 text-small break-words text-fg">→ {s.result}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-2 border-t border-line pt-5">
          <Label as="p">Expected profit by quantity</Label>
          <div className="mt-4">
            <ProfitCurve f={f} />
          </div>
        </div>
      </Disclosure>
      <Disclosure
        title={
          <>
            <span className="block">Assumptions and the data used</span>
            <span className="block text-small font-normal text-fg-muted">
              {f.explanation.assumptions.length} assumptions, the orders read, and the costs from the selected quote.
            </span>
          </>
        }
        meta={<Badge tone="faint">{f.explanation.assumptions.length} assumptions</Badge>}
      >
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          <ul className="flex flex-col">
            {f.explanation.assumptions.map((a) => (
              <li key={a.key} className="border-t border-line py-3 first:border-t-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="flex flex-wrap items-center gap-2 text-small text-fg">
                    <OutlineBadge>assumption</OutlineBadge>
                    {a.label}
                  </p>
                  <span className="font-mono text-micro text-accent">{a.value}</span>
                </div>
                <p className="mt-1 text-micro text-fg-muted">{a.note}</p>
              </li>
            ))}
          </ul>
          <div className="min-w-0">
            <KeyValues rows={dataRows} />
            {f.explanation.notes.length > 0 && (
              <ul className="mt-5 flex flex-col gap-2">
                {f.explanation.notes.map((n) => (
                  <li
                    key={n}
                    className={cx("rounded-panel bg-paper-2/70 px-3 py-2 text-micro leading-relaxed text-fg-muted")}
                  >
                    {n}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-5 text-micro text-fg-faint">
              method <span className="font-mono">{f.method}</span> · no language model · deterministic (exact sums, no sampling)
            </p>
          </div>
        </div>
      </Disclosure>
    </>
  );
}
