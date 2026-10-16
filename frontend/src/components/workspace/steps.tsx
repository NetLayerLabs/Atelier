"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
  cx,
  EmptyState,
  Eyebrow,
  Field,
  IconCheck,
  IconDocument,
  IconPlus,
  IconStore,
  InlineAlert,
  Input,
  Label,
  ProgressBar,
  SectionHeading,
  Select,
  Swatch,
  Table,
  TBody,
  Td,
  Textarea,
  Th,
  THead,
  toast,
  Tr,
} from "@/components/ds";
import { errorMessage } from "@/lib/api";
import {
  clearPrices,
  clearSales,
  confirmSuppliers,
  createSupplier,
  deleteBrandDocument,
  deleteSupplier,
  documentUrl,
  fmtDate,
  LANGUAGES,
  putProfile,
  putScoring,
  resetScoring,
  reviewGuardrails,
  RFQ_LANGUAGES,
  updateSupplier,
  uploadBrandDocument,
  uploadCertificate,
  type BrandProfileInput,
  type ColourStandard,
  type Provenance,
  type Supplier,
  type SupplierInput,
  type Workspace,
} from "@/lib/workspace";
import { GuardrailFacts, guardrailChips, GuardrailsForm } from "../GuardrailsPanel";
import { DropZone, ImportPanel } from "./ImportPanel";

const list = (s: string) =>
  s
    .split(/[,;\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
const numOrNull = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
};
const HEX = /^#[0-9A-Fa-f]{6}$/;

/** Where a section's data came from ("Imported from suppliers.csv on 13 Oct 2026 (12 rows)"). */
export function ProvenanceLine({ p, empty }: { p?: Provenance | null; empty?: string }) {
  if (!p) return empty ? <p className="text-micro text-fg-faint">{empty}</p> : null;
  return (
    <p className="flex items-center gap-1.5 text-micro text-fg-faint">
      <IconDocument size={12} className="shrink-0" />
      <span className="min-w-0 break-words">{p.label}</span>
    </p>
  );
}

export function StepHeader({
  numeral,
  title,
  lede,
  children,
}: {
  numeral?: string;
  title: string;
  lede: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4">
      <SectionHeading
        size="m"
        as="h2"
        eyebrow={<Eyebrow numeral={numeral}>Workspace step</Eyebrow>}
        title={title}
        lede={lede}
      />
      {children && <div className="flex flex-col gap-2">{children}</div>}
    </div>
  );
}

function Sub({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mt-12 border-t border-line pt-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-title text-fg">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children: ReactNode }) {
  return (
    <EmptyState compact icon={icon} title={title}>
      {children}
    </EmptyState>
  );
}

function Msg({ msg }: { msg: { ok: boolean; text: string } | null }) {
  if (!msg) return null;
  return msg.ok ? (
    <p role="status" className="flex items-center gap-1.5 text-small text-ok">
      <IconCheck size={14} strokeWidth={2.4} /> {msg.text}
    </p>
  ) : (
    <p role="alert" className="text-small font-medium text-bad">
      {msg.text}
    </p>
  );
}

// --------------------------------------------------------------------------- 1. brand profile

export function ProfileStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const p = ws.profile;
  const [name, setName] = useState(p?.name ?? "");
  const [currency, setCurrency] = useState(p?.currency ?? "");
  const [markets, setMarkets] = useState((p?.targetMarkets ?? []).join(", "));
  const [voice, setVoice] = useState(p?.voice ?? "");
  const [sizes, setSizes] = useState((p?.defaultSizeRange ?? []).join(", "));
  const [colours, setColours] = useState<ColourStandard[]>(p?.colours ?? []);
  const [paMode, setPaMode] = useState<"" | "retail_multiple" | "target_margin">(p?.priceArchitecture?.mode ?? "");
  const [paValue, setPaValue] = useState(p?.priceArchitecture ? String(p.priceArchitecture.value) : "");
  const [promise, setPromise] = useState(p?.deliveryPromiseWeeks ? String(p.deliveryPromiseWeeks) : "");
  const [windowDays, setWindowDays] = useState(p?.preorderWindowDays ? String(p.preorderWindowDays) : "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const pa = numOrNull(paValue);
    const pw = numOrNull(promise);
    const wd = numOrNull(windowDays);
    if (!name.trim()) return setMsg({ ok: false, text: "The brand name is required." });
    if (!/^[A-Za-z]{3}$/.test(currency.trim()))
      return setMsg({ ok: false, text: "Currency: a three-letter ISO code such as EUR, USD, GBP." });
    if ([pa, pw, wd].some((x) => Number.isNaN(x) || (x !== null && x <= 0)))
      return setMsg({ ok: false, text: "Numbers must be positive (or empty)." });
    if (paMode && pa === null) return setMsg({ ok: false, text: "Give the price architecture value." });
    const bad = colours.find((c) => !c.name.trim() || !HEX.test(c.hex));
    if (bad) return setMsg({ ok: false, text: `Colour “${bad.name || "(no name)"}”: a name and a #RRGGBB hex.` });
    const body: BrandProfileInput = {
      name: name.trim(),
      currency: currency.trim().toUpperCase(),
      targetMarkets: list(markets),
      voice: voice.trim(),
      defaultSizeRange: list(sizes),
      colours: colours.map((c) => ({
        name: c.name.trim(),
        hex: c.hex,
        ...(c.code?.trim() ? { code: c.code.trim() } : {}),
      })),
      priceArchitecture: paMode && pa !== null ? { mode: paMode, value: pa } : null,
      deliveryPromiseWeeks: pw === null ? null : Math.round(pw),
      preorderWindowDays: wd === null ? null : Math.round(wd),
    };
    setBusy(true);
    setMsg(null);
    try {
      await putProfile(body);
      setMsg({ ok: true, text: "Saved." });
      toast("Brand profile saved", { description: `${body.name} · prices in ${body.currency}` });
      reload();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <StepHeader
        numeral="I"
        title="Brand profile"
        lede="Who the agent works for. The name and voice replace any persona in the prompts; the colour standards, size range and price architecture go into every tech pack brief. Leave anything you don't have empty - Atelier never fills it in for you."
      >
        <ProvenanceLine p={p?.provenance} empty="Not set yet." />
      </StepHeader>
      <form onSubmit={submit} className="grid gap-5 sm:grid-cols-2 lg:grid-cols-6" data-testid="profile-form">
        <Field label="Brand name" className="sm:col-span-2 lg:col-span-3">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Currency (ISO)" hint="every price is in this currency">
          <Input
            className="font-mono uppercase"
            maxLength={3}
            placeholder="EUR"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          />
        </Field>
        <Field label="Target markets" optional hint="comma-separated" className="lg:col-span-2">
          <Input value={markets} onChange={(e) => setMarkets(e.target.value)} />
        </Field>
        <Field
          label="Persona & voice notes"
          optional
          hint="used in the agent's prompts"
          className="sm:col-span-2 lg:col-span-6"
        >
          <Textarea rows={4} value={voice} onChange={(e) => setVoice(e.target.value)} />
        </Field>
        <Field label="Price architecture" optional className="lg:col-span-3">
          <Select value={paMode} onChange={(e) => setPaMode(e.target.value as typeof paMode)}>
            <option value="">not set</option>
            <option value="retail_multiple">Retail = multiple of landed cost</option>
            <option value="target_margin">Target gross margin %</option>
          </Select>
        </Field>
        <Field
          label={paMode === "target_margin" ? "Target margin" : "Retail multiple"}
          optional
          className="lg:col-span-3"
        >
          <Input
            inputMode="decimal"
            className="font-mono"
            disabled={!paMode}
            placeholder="not set"
            suffix={paMode === "target_margin" ? "%" : "× cost"}
            value={paValue}
            onChange={(e) => setPaValue(e.target.value)}
          />
        </Field>
        <Field label="Default size range" optional className="lg:col-span-2">
          <Input placeholder="e.g. XS, S, M, L, XL" value={sizes} onChange={(e) => setSizes(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-5 sm:col-span-2 lg:col-span-4">
          <Field label="Delivery promise" optional>
            <Input
              inputMode="numeric"
              className="font-mono"
              placeholder="-"
              suffix="wks"
              value={promise}
              onChange={(e) => setPromise(e.target.value)}
            />
          </Field>
          <Field label="Pre-order window" optional>
            <Input
              inputMode="numeric"
              className="font-mono"
              placeholder="-"
              suffix="days"
              value={windowDays}
              onChange={(e) => setWindowDays(e.target.value)}
            />
          </Field>
        </div>
        <div className="sm:col-span-2 lg:col-span-6">
          <p className="text-small font-medium text-fg">
            Colour standards <span className="font-normal text-fg-faint">optional</span>
          </p>
          <p className="mt-1 text-micro text-fg-faint">
            Name and hex; a Pantone / TCX code only if your brand book gives one.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            {colours.map((c, i) => (
              <div
                key={i}
                className="grid grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-panel border border-line p-3 sm:grid-cols-[2.25rem_minmax(0,1fr)_8.5rem_11rem_auto] sm:border-0 sm:p-0"
              >
                {HEX.test(c.hex) ? (
                  <Swatch color={c.hex} size="sm" weave={false} />
                ) : (
                  <span aria-hidden className="size-9 rounded-md border border-dashed border-line-strong" />
                )}
                <Input
                  aria-label="Colour name"
                  placeholder="name"
                  value={c.name}
                  onChange={(e) => setColours(colours.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)))}
                />
                <Input
                  aria-label="Hex"
                  className="col-start-2 font-mono sm:col-start-auto"
                  placeholder="#RRGGBB"
                  value={c.hex}
                  onChange={(e) => setColours(colours.map((x, k) => (k === i ? { ...x, hex: e.target.value } : x)))}
                />
                <Input
                  aria-label="Pantone / TCX code"
                  className="col-start-2 font-mono sm:col-start-auto"
                  placeholder="code (optional)"
                  value={c.code ?? ""}
                  onChange={(e) => setColours(colours.map((x, k) => (k === i ? { ...x, code: e.target.value } : x)))}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="col-start-2 justify-self-start sm:col-start-auto"
                  onClick={() => setColours(colours.filter((_, k) => k !== i))}
                >
                  Remove
                </Button>
              </div>
            ))}
            <div>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={<IconPlus size={14} />}
                onClick={() => setColours([...colours, { name: "", hex: "" }])}
              >
                Add colour
              </Button>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-5 sm:col-span-2 lg:col-span-6">
          <Button type="submit" loading={busy}>
            Save profile
          </Button>
          <Msg msg={msg} />
        </div>
      </form>

      <Sub title="Size blocks & points of measure" aside={<ProvenanceLine p={ws.sizeProvenance} />}>
        {ws.sizePoints.length > 0 ? (
          <SizeSummary ws={ws} />
        ) : (
          <Empty title="No size blocks yet">
            Import your graded specs: one row per block, point of measure and size.
          </Empty>
        )}
        <div className="mt-6">
          <ImportPanel kind="sizes" noun="size blocks" onCommitted={reload} />
        </div>
      </Sub>
    </div>
  );
}

function SizeSummary({ ws }: { ws: Workspace }) {
  const blocks = Array.from(new Set(ws.sizePoints.map((p) => p.block)));
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {blocks.map((b) => {
        const pts = ws.sizePoints.filter((p) => p.block === b);
        const poms = new Set(pts.map((p) => p.pointOfMeasure));
        const sizes = Array.from(new Set(pts.map((p) => p.size)));
        return (
          <li key={b} className="rounded-panel bg-paper-2/70 px-4 py-3">
            <p className="text-small font-medium text-fg">{b}</p>
            <p className="mt-1 text-micro text-fg-muted">
              {poms.size} points of measure · sizes <span className="font-mono">{sizes.join(", ")}</span>
            </p>
          </li>
        );
      })}
    </ul>
  );
}

// --------------------------------------------------------------------------- 2. brand book

export function BrandBookStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const books = ws.documents.filter((d) => d.kind === "brand_book");
  const upload = async (f: File) => {
    setBusy(true);
    setError(null);
    try {
      await uploadBrandDocument(f);
      reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <StepHeader
        numeral="II"
        title="Brand book"
        lede="Your brand book, fabric standards, sustainability policy, tone-of-voice guide - whatever the agent should follow. Atelier keeps the file, extracts its text locally so every tech pack, RFQ and recommendation can cite the passage it used, and sends it to the Evolus knowledge library when one is connected."
      />
      <DropZone
        accept=".pdf,.docx,.md,.markdown,.txt"
        busy={busy}
        onFile={upload}
        hint="PDF, DOCX or Markdown · up to 25 MB"
        label="Drop a brand document, or click to choose"
      />
      {error && (
        <InlineAlert tone="bad" title="Upload failed" className="mt-4">
          {error}
        </InlineAlert>
      )}
      <div className="mt-6">
        {books.length === 0 ? (
          <Empty icon={<IconDocument size={18} />} title="No documents yet">
            Optional, but without one the agent has only your profile and supplier directory to cite.
          </Empty>
        ) : (
          <ul className="flex flex-col gap-3">
            {books.map((d) => (
              <li
                key={d.id}
                className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span
                    aria-hidden
                    className="grid size-10 shrink-0 place-items-center rounded-full bg-paper-2 text-fg"
                  >
                    <IconDocument size={16} />
                  </span>
                  <div className="min-w-0">
                    <a
                      href={documentUrl(d.id)}
                      className="block text-body font-medium break-words text-fg hover:text-accent"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {d.filename}
                    </a>
                    <p className="mt-0.5 text-micro text-fg-faint">
                      Uploaded {fmtDate(d.uploadedAt)} ·{" "}
                      {d.size < 1024 ? `${d.size} B` : `${Math.round(d.size / 1024)} KB`} · {d.passages} passage
                      {d.passages === 1 ? "" : "s"} for local grounding
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 pl-13 sm:pl-0">
                  <EvolusBadge status={d.evolus?.status} detail={d.evolus?.detail} />
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      await deleteBrandDocument(d.id).catch((e) => setError(errorMessage(e)));
                      reload();
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function EvolusBadge({ status, detail }: { status?: string; detail?: string }) {
  return (
    <span title={detail}>
      {status === "uploaded" ? (
        <Badge tone="ok">In Evolus library</Badge>
      ) : status === "failed" ? (
        <Badge status="failed">Evolus upload failed</Badge>
      ) : (
        <Badge tone="faint">Local grounding only</Badge>
      )}
    </span>
  );
}

// --------------------------------------------------------------------------- 3. suppliers

const EMPTY_SUPPLIER: SupplierInput = {
  name: "",
  city: "",
  country: "",
  language: "en",
  emails: [],
  categories: [],
  capabilities: [],
  certifications: [],
  moq: null,
  leadTimeWeeks: null,
  paymentTerms: "",
  notes: "",
  rfqEmailOverride: null,
};

function toInput(s: Supplier): SupplierInput {
  return {
    name: s.name,
    city: s.city,
    country: s.country,
    language: s.language,
    emails: s.emails,
    categories: s.categories,
    capabilities: s.capabilities,
    certifications: s.certifications.map((c) => ({
      name: c.name,
      expiresOn: c.expiresOn ?? null,
      documentId: c.documentId ?? null,
    })),
    moq: s.moq ?? null,
    leadTimeWeeks: s.leadTimeWeeks ?? null,
    paymentTerms: s.paymentTerms,
    notes: s.notes,
    rfqEmailOverride: s.rfqEmailOverride ?? null,
  };
}

export function SuppliersStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const [editing, setEditing] = useState<Supplier | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agree, setAgree] = useState(false);
  const [pilotInbox, setPilotInbox] = useState("");
  const [busy, setBusy] = useState(false);
  const conf = ws.supplierConfirmation;
  const sups = ws.suppliers;
  const provenance = ws.status.sections.find((x) => x.key === "suppliers")?.provenance;

  const routeAll = async () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(pilotInbox.trim()))
      return setError("Enter the inbox address to route RFQs to.");
    setBusy(true);
    setError(null);
    try {
      for (const s of sups) await updateSupplier(s.id, { ...toInput(s), rfqEmailOverride: pilotInbox.trim() });
      reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <StepHeader
        numeral="III"
        title="Suppliers"
        lede={
          <>
            Your supplier directory. These are <strong className="font-medium text-fg">real contacts</strong>: when you
            approve a design, Atelier drafts RFQs and emails the suppliers it shortlists (categories and capabilities
            are matched against the design&apos;s fabrics; a supplier with the category “CMT” is the cut-make-trim
            maker). During a pilot you can route a supplier&apos;s RFQs to your own sourcing inbox instead.
          </>
        }
      />
      <ImportPanel
        kind="suppliers"
        noun="supplier directory"
        onCommitted={() => {
          setAgree(false);
          reload();
        }}
        confirmNote={
          <p className="text-micro text-fg-faint">
            After importing you&apos;ll confirm the contacts before anything is sent.
          </p>
        }
      />

      <Sub
        title={`Directory · ${sups.length} supplier${sups.length === 1 ? "" : "s"}`}
        aside={
          <div className="flex flex-wrap items-center gap-3">
            {provenance && <ProvenanceLine p={provenance} />}
            <Button size="sm" variant="secondary" icon={<IconPlus size={14} />} onClick={() => setEditing("new")}>
              Add supplier
            </Button>
          </div>
        }
      >
        {error && (
          <InlineAlert tone="bad" title="Not saved" className="mb-4">
            {error}
          </InlineAlert>
        )}
        {editing && (
          <SupplierForm
            initial={editing === "new" ? null : editing}
            onClose={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              reload();
            }}
          />
        )}
        {sups.length === 0 ? (
          <Empty icon={<IconStore size={18} />} title="No suppliers yet">
            Import your directory above (download the template for the columns) or add one by hand.
          </Empty>
        ) : (
          <Table caption="Supplier directory">
            <THead>
              <Tr>
                <Th>Supplier</Th>
                <Th>Language</Th>
                <Th>RFQs go to</Th>
                <Th>Categories</Th>
                <Th>Certifications</Th>
                <Th>MOQ · lead · terms</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </Tr>
            </THead>
            <TBody>
              {sups.map((s) => (
                <Tr key={s.id}>
                  <Td className="min-w-[11rem]">
                    <p className="flex flex-wrap items-center gap-2 font-medium text-fg">
                      {s.name} {s.maker && <Badge tone="neutral">CMT</Badge>}
                    </p>
                    <p className="text-micro text-fg-faint">{[s.city, s.country].filter(Boolean).join(", ") || "-"}</p>
                    {s.provenance?.source === "form" && (
                      <p className="mt-1 text-micro text-fg-faint">{s.provenance.label}</p>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-fg-muted">
                    {LANGUAGES[s.language] ?? s.language}
                    {!RFQ_LANGUAGES.has(s.language) && (
                      <span className="block text-micro text-fg-faint">RFQs in English</span>
                    )}
                  </Td>
                  <Td className="min-w-[13rem]">
                    <p
                      className={cx(
                        "font-mono text-[0.78rem] break-all",
                        s.rfqEmailOverride ? "text-accent" : "text-fg",
                      )}
                    >
                      {s.rfqRecipient}
                    </p>
                    <p className="text-micro break-all text-fg-faint">
                      {s.rfqEmailOverride ? `override · contact: ${s.emails.join(", ")}` : s.emails.slice(1).join(", ")}
                    </p>
                  </Td>
                  <Td className="min-w-[10rem] text-fg-muted">
                    {[...s.categories, ...s.capabilities].join(", ") || "-"}
                  </Td>
                  <Td className="min-w-[10rem]">
                    {s.certifications.length === 0 && <span className="text-fg-faint">-</span>}
                    <span className="flex flex-wrap gap-1">
                      {s.certifications.map((c) => (
                        <span
                          key={c.name}
                          title={c.expiresOn ? `expires ${c.expiresOn}` : "no expiry recorded"}
                          className="inline-flex items-center gap-1"
                        >
                          <Badge tone={c.expired ? "bad" : "neutral"}>
                            {c.name}
                            {c.expiresOn && ` · ${c.expired ? "expired" : "exp."} ${c.expiresOn}`}
                          </Badge>
                          {c.documentId && (
                            <a
                              href={documentUrl(c.documentId)}
                              target="_blank"
                              rel="noreferrer"
                              className="text-accent"
                              aria-label={`${c.name} certificate document`}
                            >
                              <IconDocument size={14} />
                            </a>
                          )}
                        </span>
                      ))}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap">
                    <span className="font-mono text-[0.78rem] text-fg">
                      {s.moq ? s.moq.toLocaleString("en-US") : "-"} · {s.leadTimeWeeks ? `${s.leadTimeWeeks} wks` : "-"}
                    </span>
                    <span className="block text-micro text-fg-faint">{s.paymentTerms || ""}</span>
                  </Td>
                  <Td className="text-right whitespace-nowrap">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="hover:text-bad"
                      onClick={async () => {
                        if (!window.confirm(`Remove ${s.name} from the directory?`)) return;
                        await deleteSupplier(s.id).catch((e) => setError(errorMessage(e)));
                        reload();
                      }}
                    >
                      Remove
                    </Button>
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        )}
        {sups.length > 0 && (
          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field
              label="Pilot: route every supplier's RFQs to one inbox"
              hint="sets each supplier's RFQ override"
              className="flex-1"
            >
              <Input
                className="font-mono"
                placeholder="sourcing@your-brand.com"
                value={pilotInbox}
                onChange={(e) => setPilotInbox(e.target.value)}
              />
            </Field>
            <Button variant="secondary" onClick={routeAll} loading={busy} className="sm:mb-[1.4rem]">
              Apply to all
            </Button>
          </div>
        )}
      </Sub>

      {sups.length > 0 && (
        <Sub title="Confirm the contacts">
          {conf.confirmedAt ? (
            <InlineAlert tone="ok" title={`Confirmed by ${conf.confirmedBy} on ${fmtDate(conf.confirmedAt)}`}>
              {conf.suppliers} suppliers. Editing a contact or importing again asks for a new confirmation.
            </InlineAlert>
          ) : (
            <Card variant="outline" pad="md" className="border-warn/40 bg-warn-soft">
              <Eyebrow tone="warn">Waiting on you</Eyebrow>
              <p className="mt-3 text-body text-fg">
                Atelier will email these suppliers when you approve a design - at the address in “RFQs go to”.
              </p>
              <label className="mt-4 flex cursor-pointer items-start gap-3 text-small text-fg-muted">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-accent"
                  checked={agree}
                  onChange={(e) => setAgree(e.target.checked)}
                />
                I confirm these are the right contacts and that the brand may email them (or the override inbox) with
                RFQs and counter-offers.
              </label>
              <div className="mt-5">
                <Button
                  variant="accent"
                  disabled={!agree}
                  onClick={async () => {
                    await confirmSuppliers().catch((e) => setError(errorMessage(e)));
                    reload();
                  }}
                >
                  Confirm {sups.length} supplier contact{sups.length === 1 ? "" : "s"}
                </Button>
              </div>
            </Card>
          )}
        </Sub>
      )}
    </div>
  );
}

function SupplierForm({
  initial,
  onClose,
  onSaved,
}: {
  initial: Supplier | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const base = initial ? toInput(initial) : EMPTY_SUPPLIER;
  const [v, setV] = useState({
    name: base.name,
    city: base.city,
    country: base.country,
    language: base.language,
    emails: base.emails.join(", "),
    categories: base.categories.join(", "),
    capabilities: base.capabilities.join("; "),
    certs: base.certifications.map((c) => (c.expiresOn ? `${c.name}=${c.expiresOn}` : c.name)).join("; "),
    moq: base.moq ? String(base.moq) : "",
    lead: base.leadTimeWeeks ? String(base.leadTimeWeeks) : "",
    terms: base.paymentTerms,
    notes: base.notes,
    override: base.rfqEmailOverride ?? "",
  });
  const [certFile, setCertFile] = useState<{ cert: string; file: File | null }>({ cert: "", file: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const moq = numOrNull(v.moq);
    const lead = numOrNull(v.lead);
    if (!v.name.trim()) return setError("Name is required.");
    if (list(v.emails).length === 0) return setError("At least one contact email is required.");
    if ([moq, lead].some((x) => Number.isNaN(x) || (x !== null && x <= 0)))
      return setError("MOQ and lead time must be positive whole numbers.");
    const certifications = v.certs
      .split(";")
      .map((x) => x.trim())
      .filter(Boolean)
      .map((x) => {
        const [name, exp] = x.split("=").map((y) => y.trim());
        const prev = base.certifications.find((c) => c.name.toLowerCase() === name.toLowerCase());
        return { name, expiresOn: exp || null, documentId: prev?.documentId ?? null };
      });
    if (certifications.some((c) => c.expiresOn && !/^\d{4}-\d{2}-\d{2}$/.test(c.expiresOn)))
      return setError("Certificate expiry: NAME=YYYY-MM-DD.");
    const body: SupplierInput = {
      name: v.name.trim(),
      city: v.city.trim(),
      country: v.country.trim(),
      language: v.language,
      emails: list(v.emails),
      categories: list(v.categories),
      capabilities: v.capabilities
        .split(";")
        .map((x) => x.trim())
        .filter(Boolean),
      certifications,
      moq: moq === null ? null : Math.round(moq),
      leadTimeWeeks: lead === null ? null : Math.round(lead),
      paymentTerms: v.terms.trim(),
      notes: v.notes.trim(),
      rfqEmailOverride: v.override.trim() || null,
    };
    setBusy(true);
    setError(null);
    try {
      const saved = initial ? await updateSupplier(initial.id, body) : await createSupplier(body);
      if (certFile.file && certFile.cert.trim()) await uploadCertificate(saved.id, certFile.cert.trim(), certFile.file);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card variant="muted" pad="md" className="mb-6">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <p className="text-title text-fg sm:col-span-2 lg:col-span-4">
          {initial ? `Edit ${initial.name}` : "New supplier"}
        </p>
        <Field label="Name" className="sm:col-span-2">
          <Input value={v.name} onChange={set("name")} />
        </Field>
        <Field label="City" optional>
          <Input value={v.city} onChange={set("city")} />
        </Field>
        <Field label="Country" optional>
          <Input value={v.country} onChange={set("country")} />
        </Field>
        <Field label="Contact emails" hint="comma-separated" className="sm:col-span-2">
          <Input className="font-mono" value={v.emails} onChange={set("emails")} />
        </Field>
        <Field label="Language">
          <Select value={v.language} onChange={set("language")}>
            {Object.entries(LANGUAGES).map(([k, n]) => (
              <option key={k} value={k}>
                {n}
                {RFQ_LANGUAGES.has(k) ? "" : " (RFQs in English)"}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="RFQ email override" optional>
          <Input
            className="font-mono"
            placeholder="e.g. your sourcing inbox"
            value={v.override}
            onChange={set("override")}
          />
        </Field>
        <Field label="Categories" hint="comma-separated; “CMT” = cut-make-trim maker" className="sm:col-span-2">
          <Input value={v.categories} onChange={set("categories")} />
        </Field>
        <Field label="Capabilities" optional hint="semicolon-separated" className="sm:col-span-2">
          <Input value={v.capabilities} onChange={set("capabilities")} />
        </Field>
        <Field
          label="Certifications"
          optional
          hint="NAME or NAME=YYYY-MM-DD expiry; semicolon-separated"
          className="sm:col-span-2"
        >
          <Input value={v.certs} onChange={set("certs")} />
        </Field>
        <Field label="MOQ" optional>
          <Input inputMode="numeric" className="font-mono" suffix="pcs" value={v.moq} onChange={set("moq")} />
        </Field>
        <Field label="Typical lead time" optional>
          <Input inputMode="numeric" className="font-mono" suffix="wks" value={v.lead} onChange={set("lead")} />
        </Field>
        <Field label="Payment terms" optional className="sm:col-span-2">
          <Input value={v.terms} onChange={set("terms")} />
        </Field>
        <Field label="Notes" optional className="sm:col-span-2">
          <Input value={v.notes} onChange={set("notes")} />
        </Field>
        <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2 lg:col-span-4">
          <Field label="Certificate document - for certification" optional>
            <Input
              placeholder="certification name, e.g. GOTS"
              value={certFile.cert}
              onChange={(e) => setCertFile({ ...certFile, cert: e.target.value })}
            />
          </Field>
          <label className="flex flex-col gap-1.5">
            <span className="text-small font-medium text-fg">File</span>
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              className="min-h-11 rounded-field border border-line-strong bg-surface px-2 py-1.5 text-small text-fg-muted file:mr-3 file:h-8 file:rounded-full file:border-0 file:bg-paper-2 file:px-3 file:text-small file:text-fg"
              onChange={(e) => setCertFile({ ...certFile, file: e.target.files?.[0] ?? null })}
            />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-4">
          <Button type="submit" loading={busy}>
            {initial ? "Save supplier" : "Add supplier"}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {error && (
            <p role="alert" className="text-small font-medium text-bad">
              {error}
            </p>
          )}
        </div>
      </form>
    </Card>
  );
}

// --------------------------------------------------------------------------- 4. price list

export function PricesStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const pl = ws.priceList;
  return (
    <div>
      <StepHeader
        numeral="IV"
        title="Material price list"
        lede="Your material prices. The tech pack editor offers swaps from the same category on this list and costs them against the line's current material. Without a price list there are no swaps - Atelier doesn't invent prices."
      >
        {pl.items.length > 0 ? (
          <p className="flex flex-wrap items-center gap-2 text-small text-fg">
            <Badge tone="ok">{pl.items.length} prices</Badge> dated <span className="font-mono">{pl.dated}</span>
            {pl.provenance && <span className="text-micro text-fg-faint">· {pl.provenance.label}</span>}
          </p>
        ) : (
          <p className="text-micro text-fg-faint">No price list yet (optional).</p>
        )}
      </StepHeader>
      <ImportPanel kind="prices" noun="price list" onCommitted={reload} />
      {pl.items.length > 0 && (
        <Sub
          title="Current prices"
          aside={
            <Button
              size="sm"
              variant="danger"
              onClick={async () => {
                if (window.confirm("Remove the whole price list?")) {
                  await clearPrices();
                  reload();
                }
              }}
            >
              Clear price list
            </Button>
          }
        >
          <Table caption="Material price list" dense className="max-h-[26rem] overflow-y-auto">
            <THead>
              <Tr>
                <Th>Material</Th>
                <Th>Category</Th>
                <Th numeric>Price</Th>
                <Th>Supplier</Th>
                <Th>Valid from</Th>
              </Tr>
            </THead>
            <TBody>
              {pl.items.map((it, i) => (
                <Tr key={i}>
                  <Td className="min-w-[12rem]">{it.material}</Td>
                  <Td className="text-fg-muted">{it.category}</Td>
                  <Td numeric>
                    {it.currency} {it.price.toFixed(2)}
                    <span className="text-fg-faint">/{it.unit}</span>
                  </Td>
                  <Td className="text-fg-muted">{it.supplier || "-"}</Td>
                  <Td className="font-mono text-[0.78rem] whitespace-nowrap text-fg-faint">{it.validFrom}</Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </Sub>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- 5. guardrails + scoring

const RULE_LABELS: Record<string, string> = {
  min_margin: "gross-margin floor",
  max_unit_cost: "unit-cost cap",
  max_lead_time: "max lead time",
  max_moq: "max MOQ",
  certifications: "required certifications",
};

export function GuardrailsStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const g = ws.guardrails;
  const [error, setError] = useState<string | null>(null);
  const unset = g.unset ?? [];
  return (
    <div>
      <StepHeader
        numeral="V"
        title="Guardrails"
        lede="Your hard limits for a supplier quote. When the agent's pick breaks one, the run stops before Shopify and hands the decision to you. Nothing is pre-filled: a rule you leave empty is not checked."
      >
        <div className="flex flex-wrap items-center gap-2">
          {g.reviewedAt ? (
            <Badge tone="ok">
              Reviewed {fmtDate(g.reviewedAt)} ({g.updatedBy ?? "brand"})
            </Badge>
          ) : (
            <Badge tone="warn">Not reviewed yet - save your limits, or confirm you want none</Badge>
          )}
        </div>
        {unset.length > 0 && (
          <p className="text-small text-fg-muted">
            Not set, so not checked: <span className="text-fg">{unset.map((r) => RULE_LABELS[r] ?? r).join(", ")}</span>
            .
          </p>
        )}
      </StepHeader>
      <Card pad="none" className="overflow-hidden">
        <div className="px-5 pt-5 pb-4 sm:px-6">
          <Label as="p">Saved limits</Label>
        </div>
        <GuardrailFacts chips={guardrailChips(g)} />
        <div className="border-t border-line p-5 sm:p-6">
          <GuardrailsForm key={g.updatedAt ?? "new"} value={g} onSaved={() => reload()} onError={setError} />
        </div>
      </Card>
      {error && (
        <InlineAlert tone="bad" title="Guardrails not saved" className="mt-4">
          {error}
        </InlineAlert>
      )}
      {!g.reviewedAt && (
        <div className="mt-4">
          <Button
            variant="secondary"
            onClick={async () => {
              await reviewGuardrails().catch((e) => setError(errorMessage(e)));
              reload();
            }}
          >
            {unset.length === 5 ? "Continue with no guardrails" : "Mark as reviewed"}
          </Button>
        </div>
      )}
      <ScoringWeightsEditor ws={ws} reload={reload} />
    </div>
  );
}

function ScoringWeightsEditor({ ws, reload }: { ws: Workspace; reload: () => void }) {
  const w = ws.scoring;
  const [price, setPrice] = useState(String(Math.round(w.price * 100)));
  const [moq, setMoq] = useState(String(Math.round(w.moq * 100)));
  const [lead, setLead] = useState(String(Math.round(w.leadTime * 100)));
  const [error, setError] = useState<string | null>(null);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const vals = [price, moq, lead].map(Number);
    if (vals.some((x) => !Number.isFinite(x) || x < 0) || vals.every((x) => x === 0))
      return setError("Weights are non-negative numbers, at least one above zero.");
    try {
      await putScoring({ price: vals[0], moq: vals[1], leadTime: vals[2] });
      setError(null);
      reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  const nums = [price, moq, lead].map((x) => Math.max(0, Number(x) || 0));
  const sum = nums.reduce((a, b) => a + b, 0);
  const rows = [
    ["Price", price, setPrice],
    ["MOQ fit", moq, setMoq],
    ["Lead time", lead, setLead],
  ] as const;
  return (
    <Sub title="Supplier scoring weights" aside={<Badge tone={w.isDefault ? "faint" : "ok"}>{w.label}</Badge>}>
      <p className="mb-5 max-w-3xl text-small text-fg-muted">
        How the agent ranks quotes before it picks one.{" "}
        {w.isDefault && "These are Atelier's default weighting - change them to your own."} Any scale; they are
        normalised to 100%.
      </p>
      <form onSubmit={save} className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="grid grid-cols-3 gap-3">
          {rows.map(([l, val, setter]) => (
            <Field key={l} label={l}>
              <Input
                inputMode="decimal"
                className="font-mono"
                suffix="%"
                value={val}
                onChange={(e) => setter(e.target.value)}
              />
            </Field>
          ))}
        </div>
        <div className="flex flex-col gap-3 rounded-panel bg-paper-2/60 p-4">
          <Label as="p">Normalised · what the agent will use</Label>
          {rows.map(([l], i) => (
            <ProgressBar
              key={l}
              size="sm"
              value={sum > 0 ? nums[i] / sum : null}
              label={l}
              detail={sum > 0 ? `${Math.round((nums[i] / sum) * 100)}%` : "-"}
              tone="accent"
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <Button type="submit" variant="secondary">
            Save weights
          </Button>
          {!w.isDefault && (
            <Button
              type="button"
              variant="ghost"
              onClick={async () => {
                const d = await resetScoring();
                setPrice(String(Math.round(d.price * 100)));
                setMoq(String(Math.round(d.moq * 100)));
                setLead(String(Math.round(d.leadTime * 100)));
                reload();
              }}
            >
              Back to default weighting
            </Button>
          )}
          {error && (
            <p role="alert" className="text-small font-medium text-bad">
              {error}
            </p>
          )}
        </div>
      </form>
    </Sub>
  );
}

// --------------------------------------------------------------------------- 6. sales history

export function SalesStep({ ws, reload }: { ws: Workspace; reload: () => void }) {
  return (
    <div>
      <StepHeader
        numeral="VI"
        title="Sales history"
        lede="Optional. Past launches, week by week: one row per style, week since launch and (optionally) size. Stored in the workspace so the production forecast can fit its launch-curve and size-mix priors to your own history instead of generic ones."
      >
        {ws.sales.rows > 0 ? (
          <p className="flex flex-wrap items-center gap-2 text-small text-fg">
            <Badge tone="ok">
              {ws.sales.rows} rows · {ws.sales.styles} styles
            </Badge>
            {ws.sales.provenance && <ProvenanceLine p={ws.sales.provenance} />}
          </p>
        ) : (
          <p className="text-micro text-fg-faint">
            No sales history yet. The preview draws units per week from the file you drop.
          </p>
        )}
      </StepHeader>
      <ImportPanel kind="sales" noun="sales history" onCommitted={reload} />
      {ws.sales.rows > 0 && (
        <div className="mt-6">
          <Button
            size="sm"
            variant="danger"
            onClick={async () => {
              if (window.confirm("Remove the sales history?")) {
                await clearSales();
                reload();
              }
            }}
          >
            Clear sales history
          </Button>
        </div>
      )}
    </div>
  );
}
