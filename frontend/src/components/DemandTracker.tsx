"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
  DUR,
  EASE,
  Eyebrow,
  GarmentTag,
  IconRefresh,
  InlineAlert,
  Label,
  Sparkline,
  Spinner,
  Stat,
  StatGroup,
  Stitch,
  Table,
  TapeMeasure,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ds";
import {
  errorHint,
  errorMessage,
  resolveAssetUrl,
  sendPurchaseOrder,
  type PipelineRun,
  type PreorderDemand,
  type PreorderOrder,
  type PurchaseOrder,
  type ShopifyProduct,
} from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { int, money, NOT_STATED, OutlineBadge, SheetHeading } from "./Sheet";

function timeLeft(hours: number): string {
  const h = Math.max(0, Math.round(hours));
  const d = Math.floor(h / 24);
  return d > 0 ? `${d}d ${h % 24}h` : `${h}h`;
}

function ago(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

/** "12 orders (incl. 3 test orders)" - test orders are always labelled. */
function withTests(n: number, tests: number, noun: string, testNoun: string): string {
  const base = `${int(n)} ${noun}`;
  return tests > 0 ? `${base} (incl. ${int(tests)} ${testNoun})` : base;
}

function niceMax(v: number): number {
  if (!(v > 0)) return 10;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

/** The pre-order window: real Shopify orders only. */
export function DemandTracker({ run }: { run: PipelineRun }) {
  const d = run.demand as PreorderDemand;
  return <RealDemand run={run} d={d} />;
}

function RealDemand({ run, d }: { run: PipelineRun; d: PreorderDemand }) {
  const product = run.shopifyProduct;
  const units = d.units ?? d.orders;
  const unlocked = d.status === "unlocked";
  const expired = d.status === "expired";
  const prod = d.productionThreshold ?? d.threshold;
  const stage = d.stageThreshold;
  const currency = d.currency ?? product?.currency; // the store's currency (orders are paid in it)
  const title = unlocked ? "Production unlocked" : expired ? "Threshold missed" : "Pre-orders are open";
  const orders = d.recentOrders ?? [];
  const sizes = product?.sizes ?? [];
  const testOrders = d.testOrders ?? 0;
  const testUnits = d.testUnits ?? 0;
  const brand = product?.brandCurrency;
  // Revenue is paid in the store's currency; the brand equivalent uses the listing's ECB rate (store per brand unit).
  const revenueBrand =
    brand && currency && brand !== currency && product?.fxRate ? d.revenue / product.fxRate : undefined;
  // The tape is scaled to the threshold that unlocks the PO (a production plan far beyond it is stated in words).
  const scaleMax = niceMax(Math.max(d.threshold, units) * 1.25);
  const markers = [
    {
      value: d.threshold,
      label: stage ? `Stage ${int(stage)}` : `Threshold ${int(d.threshold)}`,
      tone: unlocked ? ("ok" as const) : undefined,
    },
    ...(stage && prod !== d.threshold && prod <= scaleMax ? [{ value: prod, label: `Plan ${int(prod)}` }] : []),
  ];

  return (
    <Card as="section" pad="lg">
      <SheetHeading
        kicker={`Demand validation · real Shopify pre-orders${product?.shopDomain ? ` · ${product.shopDomain}` : ""}`}
        tone={unlocked ? "ok" : expired ? "bad" : "accent"}
        live={!unlocked && !expired}
        title={title}
        aside={<Badge status="connected">Shopify orders</Badge>}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-6">
          <div className="rounded-panel bg-paper-2/60 p-4 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <Stat
                size="lg"
                label={stage ? "Units pre-ordered · toward the stage threshold" : "Units pre-ordered"}
                count={units}
                unit={`/ ${int(d.threshold)}`}
                caption={
                  testUnits > 0
                    ? `incl. ${int(testUnits)} unit${testUnits === 1 ? "" : "s"} from test orders`
                    : undefined
                }
              />
              <div className="text-right">
                <Label as="p">Window</Label>
                <p className="mt-1 font-mono text-small text-fg">{timeLeft(d.hoursLeft)} left</p>
                <p className="text-micro text-fg-faint">of {Math.round(d.windowHours / 24)} days</p>
              </div>
            </div>
            <TapeMeasure
              className="mt-4"
              label="Real pre-orders toward the threshold"
              min={0}
              max={scaleMax}
              value={units}
              format={(n) => int(n)}
              readout={`${int(units)} units`}
              tone={unlocked ? "ok" : expired ? "bad" : "accent"}
              target={{ from: d.threshold, to: scaleMax }}
              markers={markers}
            />
            {stage ? (
              <p className="mt-3 text-small text-fg-muted" data-demo="stage-threshold">
                <span className="font-medium text-accent">Stage threshold: {int(stage)} pre-orders</span>{" "}
                <span className="text-fg-faint">(production plan: {int(prod)} units)</span>
                <span className="mt-1 block text-micro text-fg-faint">
                  The stage threshold is a setting (DEMAND_STAGE_THRESHOLD): the PO is drafted once {int(stage)} units
                  are pre-ordered, for the {int(prod)}-unit production plan.
                </span>
              </p>
            ) : (
              <p className="mt-3 text-small text-fg-muted">
                Production unlocks at {int(d.threshold)} units -{" "}
                {d.thresholdBasis === "moq" ? "the chosen mill's MOQ" : "the planned production run"}.
              </p>
            )}
          </div>

          <div>
            <div className="flex items-baseline justify-between gap-3">
              <Label as="p">Units since launch</Label>
              <span className="font-mono text-micro text-fg-faint">
                day {(d.elapsedHours / 24).toFixed(1)} of {Math.round(d.windowHours / 24)}
              </span>
            </div>
            {d.series.length > 1 ? (
              <Sparkline
                className="mt-3"
                height={56}
                values={d.series.map((p) => p.orders)}
                label="Cumulative units pre-ordered"
                tone={unlocked ? "ok" : "accent"}
              />
            ) : (
              <p className="mt-3 rounded-panel border border-dashed border-line-strong px-4 py-4 text-small text-fg-faint">
                - No orders yet, so no curve: it draws from the first real order.
              </p>
            )}
          </div>

          <StatGroup>
            <Stat
              size="sm"
              label="Orders"
              count={d.orders}
              caption={testOrders > 0 ? `incl. ${int(testOrders)} test order${testOrders === 1 ? "" : "s"}` : undefined}
            />
            <Stat
              size="sm"
              label="Units"
              count={units}
              caption={testUnits > 0 ? `incl. ${int(testUnits)} from tests` : undefined}
            />
            <Stat
              size="sm"
              label={`Revenue${currency ? ` · ${currency}` : ""}`}
              count={d.revenue}
              format={(n) => money(n, currency, 0)}
              caption={
                revenueBrand != null
                  ? `≈ ${money(revenueBrand, brand, 0)} in ${brand} (ECB)`
                  : testOrders > 0
                    ? "incl. test orders"
                    : undefined
              }
            />
            <Stat size="sm" label="Time left" value={timeLeft(d.hoursLeft)} />
          </StatGroup>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {product && <PreorderQr product={product} />}
          <div className="rounded-panel border border-line p-4 sm:p-5">
            <div className="flex items-baseline justify-between gap-3">
              <Label as="p">Orders as they land</Label>
              <span className="text-micro text-fg-faint">
                first name · city{sizes.length > 0 && " · size"}
              </span>
            </div>
            {orders.length === 0 ? (
              <p className="mt-4 text-small text-fg-muted">
                No orders yet
                <span className="caret" />
                <span className="mt-1 block text-micro text-fg-faint">
                  Scan the code to open the real product page and place a pre-order.
                </span>
              </p>
            ) : (
              <ul className="mt-2 flex flex-col" aria-live="polite">
                <AnimatePresence initial={false}>
                  {orders.map((o) => (
                    <OrderRow key={o.orderId} order={o} />
                  ))}
                </AnimatePresence>
              </ul>
            )}
            {sizes.length > 0 && <SizeTally d={d} sizes={sizes} />}
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4 text-micro text-fg-faint">
        <p>
          Tracking {d.tracking || "Shopify orders"}
          {d.lastCheckedAt && ` · last checked ${ago(d.lastCheckedAt)}`}
        </p>
        <p>
          {withTests(
            d.orders,
            testOrders,
            d.orders === 1 ? "order" : "orders",
            testOrders === 1 ? "test order" : "test orders",
          )}{" "}
          from Shopify.
        </p>
      </div>
      {d.trackingError && (
        <InlineAlert tone="warn" title="Order tracking problem" className="mt-4">
          {d.trackingError}
        </InlineAlert>
      )}

      <Outcome run={run} d={d} unlocked={unlocked} expired={expired} units={units} currency={currency} />
    </Card>
  );
}

/** v4: "M" · "2× M, L" - the sizes in one order. */
function orderSizes(order: PreorderOrder): string {
  return (order.lines ?? [])
    .filter((l) => l.size)
    .map((l) => (l.quantity > 1 ? `${l.quantity}× ${l.size}` : l.size))
    .join(", ");
}

/** v4: units pre-ordered per size, in the product's size order (sizes outside it go last). */
function sizeTally(d: PreorderDemand, sizes: string[]): { size: string; units: number }[] {
  const counts = new Map<string, number>(sizes.map((s) => [s, 0]));
  for (const e of d.orderEvents ?? []) {
    if (e.size) counts.set(e.size, (counts.get(e.size) ?? 0) + e.quantity);
  }
  return [...counts].map(([size, units]) => ({ size, units }));
}

function SizeTally({ d, sizes }: { d: PreorderDemand; sizes: string[] }) {
  const reduce = useReducedMotion();
  const tally = sizeTally(d, sizes);
  const max = Math.max(1, ...tally.map((t) => t.units));
  return (
    <div className="mt-5 border-t border-line pt-4" data-demo="size-tally">
      <Label as="p">Pre-orders by size</Label>
      <ul className="mt-3 flex items-end gap-2" aria-label={tally.map((t) => `${t.size}: ${t.units}`).join(", ")}>
        {tally.map((t) => (
          <li key={t.size} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <span className="font-mono text-micro text-fg tabular">{int(t.units)}</span>
            <span className="relative block h-10 w-full overflow-hidden rounded-md bg-paper-2" aria-hidden>
              <motion.span
                className="absolute inset-x-0 bottom-0 block rounded-md bg-accent"
                initial={reduce ? false : { height: 0 }}
                animate={{ height: `${(t.units / max) * 100}%` }}
                transition={{ duration: DUR.settle, ease: EASE }}
              />
            </span>
            <span className="font-mono text-micro text-fg-muted">{t.size}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OrderRow({ order }: { order: PreorderOrder }) {
  const who = [order.firstName, order.city, orderSizes(order)].filter(Boolean).join(" · ") || "A customer";
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.reveal, ease: EASE }}
      className="flex items-center justify-between gap-3 border-t border-line py-3 first:border-t-0"
    >
      <div className="min-w-0">
        <p className="truncate text-small font-medium text-fg">{who}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-micro text-fg-faint">
          {order.name} · {ago(order.createdAt)}
          {order.via === "webhook" && " · webhook"}
          {order.test && (
            <OutlineBadge title="Placed in Shopify test mode (e.g. the Bogus Gateway) - not a paying customer">
              test order
            </OutlineBadge>
          )}
        </p>
      </div>
      <p className="shrink-0 text-right font-mono text-small text-fg tabular">
        {order.units > 1 && <span className="text-fg-faint">{order.units} × </span>}
        {money(order.amount, order.currency, 0)}
      </p>
    </motion.li>
  );
}

function PreorderQr({ product }: { product: ShopifyProduct }) {
  const qr = product.qrUrl ? resolveAssetUrl(product.qrUrl) : "";
  return (
    <div
      className="flex items-center gap-4 rounded-panel border border-line bg-surface p-4 sm:gap-5 sm:p-5"
      data-demo="preorder-qr"
    >
      {qr ? (
        // The QR stays on a white tile in both themes so phones can scan it off a projector.
        <a
          href={product.url}
          target="_blank"
          rel="noreferrer"
          className="block w-28 shrink-0 rounded-panel bg-white p-2.5 shadow-e1 sm:w-32"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qr} alt={`QR code for ${product.url}`} className="block h-auto w-full" />
        </a>
      ) : (
        <div className="grid size-28 shrink-0 place-items-center rounded-panel border border-dashed border-line-strong p-2 text-center text-micro text-fg-faint">
          - QR unavailable
        </div>
      )}
      <div className="min-w-0">
        <Eyebrow tone="accent">Pre-order now</Eyebrow>
        <a
          href={product.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 block font-mono text-micro break-all text-fg underline-offset-4 hover:text-accent hover:underline"
        >
          {product.shortUrl || product.url}
        </a>
        {product.storefrontPassword && (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-micro text-fg-muted">
            Store password
            <span className="rounded-chip border border-line-strong bg-paper-2 px-2 py-0.5 font-mono text-fg">
              {product.storefrontPassword}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- outcome + purchase order

function Outcome({
  run,
  d,
  unlocked,
  expired,
  units,
  currency,
}: {
  run: PipelineRun;
  d: PreorderDemand;
  unlocked: boolean;
  expired: boolean;
  units: number;
  currency?: string;
}) {
  const po = d.purchaseOrder;
  const testUnits = d.testUnits ?? 0;
  return (
    <AnimatePresence>
      {unlocked && (
        <motion.div
          key="unlocked"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: DUR.reveal, ease: EASE }}
          className="mt-10"
        >
          <Stitch label="Demand → mill" />
          <div className="mt-8 flex flex-col gap-2">
            <Eyebrow tone="ok">
              {d.stageThreshold ? "Stage threshold" : "Threshold"} crossed · {int(units)} units pre-ordered
              {testUnits > 0 && ` (incl. ${int(testUnits)} from test orders)`}
            </Eyebrow>
            <p className="text-display-m text-fg">Demand validated - the purchase order is drafted.</p>
            <p className="font-mono text-micro text-fg-faint">
              {withTests(d.orders, d.testOrders ?? 0, "orders", "test orders")} · {money(d.revenue, currency, 0)}
            </p>
          </div>
          {po ? (
            <PurchaseOrderBlock runId={run.id} po={po} garment={run.techPack?.garmentName} />
          ) : (
            <p className="mt-6 flex items-center gap-2 text-small text-fg-muted">
              <Spinner /> Drafting the purchase order…
            </p>
          )}
        </motion.div>
      )}
      {expired && (
        <motion.div key="expired" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="mt-10">
          <InlineAlert tone="bad" title="Demand fell short - no PO drafted">
            {int(units)} of {int(d.threshold)} units pre-ordered. If the threshold is missed, no PO is drafted. The
            pre-orders stay as open orders in Shopify; Atelier does not refund or cancel them - do that in Shopify
            admin.
          </InlineAlert>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const PO_BADGE: Record<PurchaseOrder["status"], ReactNode> = {
  draft: <Badge status="draft">Draft - not sent</Badge>,
  sending: <Badge status="running">Sending</Badge>,
  queued: <Badge status="pending">Queued</Badge>,
  sent: <Badge status="sent" />,
  failed: <Badge status="failed">Send failed</Badge>,
  unknown: <Badge status="unknown" />,
};

/** v5: a real PO. Draft / failed ⇒ "Draft - not sent" + Send PO; sent / queued ⇒ "Sent via …". Never "issued". */
function PurchaseOrderBlock({ runId, po, garment }: { runId: string; po: PurchaseOrder; garment?: string }) {
  const updateRun = useAtelier((s) => s.updateRun);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const sent = po.status === "sent" || po.status === "queued";
  const draft = po.status === "draft" || po.status === "failed";
  // QA M3: the workflow started but its outcome couldn't be read - the mill may already have the PO.
  const unknown = po.status === "unknown";

  const send = async () => {
    if (
      unknown &&
      !window.confirm(
        `${po.poNumber} may already have reached ${po.supplierName} (Evolus execution ${po.executionId ?? "?"}, ` +
          "status unknown). Check Evolus first. Send it again anyway?",
      )
    )
      return;
    setSending(true);
    setError(null);
    try {
      updateRun(await sendPurchaseOrder(runId, { confirmResend: unknown }));
    } catch (err) {
      setError({ message: errorMessage(err), hint: errorHint(err) });
    } finally {
      setSending(false);
    }
  };

  // The mill quoted in its own currency; show the brand-currency equivalent only when it is a different currency.
  const brand = po.brandCurrency;
  const converted = !!brand && brand !== po.currency && po.totalBrand != null && po.unitPriceBrand != null;

  return (
    <motion.article
      key="po"
      data-demo="po"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.reveal, ease: EASE }}
      className="mt-8 overflow-hidden rounded-card border border-line-strong bg-surface shadow-e2"
    >
      {/* letterhead */}
      <div className="flex flex-col gap-4 border-b border-line px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-8 sm:py-6">
        <div className="min-w-0">
          <Label as="p">Purchase order</Label>
          <p className="mt-2 font-mono text-[1.6rem] leading-none tracking-[-0.02em] text-fg">{po.poNumber}</p>
          <p className="mt-2 text-micro text-fg-muted">
            {new Date(po.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
            {po.quoteNumber && ` · against quote ${po.quoteNumber}`}
            {po.rfqRef && ` · ${po.rfqRef}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">{PO_BADGE[po.status]}</div>
      </div>

      <div className="grid grid-cols-1 gap-6 px-5 py-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-8">
        <div className="min-w-0">
          <Label as="p">To</Label>
          <p className="mt-1.5 text-title text-fg">
            <GarmentTag tone="accent">{po.supplierName}</GarmentTag>
          </p>
          <p className="mt-2 text-small text-fg-muted">{po.region}</p>
          {po.toEmail && <p className="font-mono text-micro break-all text-fg-faint">{po.toEmail}</p>}
        </div>
        <div className="sm:text-right">
          <Label as="p">Lead time</Label>
          <p className="mt-1.5 font-mono text-small text-fg">
            {po.leadTimeWeeks != null ? `${po.leadTimeWeeks} weeks` : NOT_STATED}
          </p>
        </div>
      </div>

      <div className="px-5 sm:px-8">
        <Table caption="Purchase order lines" dense>
          <THead>
            <Tr>
              <Th>Item</Th>
              <Th numeric>Qty</Th>
              <Th numeric>Unit · {po.currency}</Th>
              <Th numeric>Total · {po.currency}</Th>
            </Tr>
          </THead>
          <TBody>
            <Tr>
              <Td className="min-w-[10rem]">{garment ?? "Production run"}</Td>
              <Td numeric>{int(po.quantity)}</Td>
              <Td numeric>{money(po.unitPrice, po.currency)}</Td>
              <Td numeric>{money(po.total, po.currency, 0)}</Td>
            </Tr>
          </TBody>
        </Table>
      </div>

      <div className="flex flex-col gap-6 px-5 py-6 sm:flex-row sm:items-end sm:justify-between sm:px-8">
        <div className="flex flex-wrap gap-x-10 gap-y-6">
          <Stat
            size="md"
            label={converted ? `PO value · ${po.currency}, as quoted` : `PO value · ${po.currency}`}
            value={money(po.total, po.currency, 0)}
            caption={`${int(po.quantity)} × ${money(po.unitPrice, po.currency)}`}
          />
          {converted && (
            <Stat
              size="md"
              label={`In the brand currency · ${brand}`}
              value={money(po.totalBrand as number, brand, 0)}
              caption={`${money(po.unitPriceBrand as number, brand)} / unit · ECB reference rate`}
              className="sm:border-l sm:border-line sm:pl-10"
            />
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-2 sm:items-end">
          {sent ? (
            <p className="text-small text-ok">
              {po.status === "queued" ? "Queued" : "Sent"} via {po.sentVia ?? "Evolus"}
              {po.sentAt && <span className="text-fg-faint"> · {new Date(po.sentAt).toLocaleString()}</span>}
            </p>
          ) : po.status === "sending" ? (
            <p className="flex items-center gap-2 text-small text-accent">
              <Spinner /> Sending through the Evolus PO workflow…
            </p>
          ) : null}
          {draft && (
            <Button variant="accent" onClick={send} loading={sending}>
              Send PO
            </Button>
          )}
        </div>
      </div>

      {(unknown || (draft && (po.sendError || po.hint)) || error) && (
        <div className="flex flex-col gap-3 border-t border-line px-5 py-5 sm:px-8">
          {unknown && (
            <InlineAlert
              tone="warn"
              title={`Send status unknown - check Evolus execution ${po.executionId ?? "?"}`}
              action={
                <Button size="sm" variant="secondary" icon={<IconRefresh size={14} />} onClick={send} loading={sending}>
                  Send again anyway…
                </Button>
              }
            >
              {po.sendError ??
                "The workflow started but its outcome couldn't be read; the mill may already have the PO."}
            </InlineAlert>
          )}
          {draft && (po.sendError || po.hint) && (
            <InlineAlert
              tone={po.sendError ? "bad" : "info"}
              title={po.sendError ? "Not sent" : "Draft - not sent"}
              hint={po.hint}
            >
              {po.sendError}
            </InlineAlert>
          )}
          {error && (
            <InlineAlert
              tone="bad"
              title="Send failed"
              hint={error.hint && error.hint !== po.hint ? error.hint : undefined}
            >
              {error.message}
            </InlineAlert>
          )}
        </div>
      )}
      <p
        className="border-t border-dashed border-line-strong px-5 py-3 text-micro text-fg-faint sm:px-8"
      >
        Placed in {po.currency}, the currency the mill quoted in. Without the Evolus PO workflow it stays a draft -
        never “issued”.
      </p>
    </motion.article>
  );
}
