"use client";

// /design - the design-system showcase. Renders every primitive once per theme (each band scopes its theme
// with data-theme). Values on this page are specimens for review, not product data.

import { MotionConfig } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Header } from "../Header";
import {
  AtelierMark,
  Badge,
  Button,
  Card,
  CardHeader,
  Chip,
  ChipButton,
  Dial,
  Disclosure,
  Em,
  EmptyState,
  Eyebrow,
  FanChart,
  Field,
  FileDrop,
  GarmentTag,
  IconArrowRight,
  IconArrowUpRight,
  IconButton,
  IconImage,
  IconMail,
  IconPlus,
  IconRefresh,
  IconRuler,
  IconSignal,
  IconSun,
  InlineAlert,
  Input,
  Label,
  LinkButton,
  Modal,
  NotConnected,
  ProgressBar,
  Radar,
  Ring,
  SectionHeading,
  Segmented,
  Select,
  Sheet,
  Skeleton,
  SkeletonText,
  Sparkline,
  Stat,
  StatGroup,
  StatusDot,
  Stepper,
  Stitch,
  Swatch,
  SwatchStrip,
  Table,
  Tabs,
  TapeMeasure,
  TBody,
  Td,
  Textarea,
  Th,
  THead,
  Timeline,
  toast,
  Tr,
  Wordmark,
  type BadgeStatus,
} from "../ds";
import * as Icons from "../ds/icons";

type View = "both" | "light" | "dark";

export function DesignShowcase() {
  const router = useRouter();
  const [view, setView] = useState<View>("both");
  return (
    <MotionConfig reducedMotion="user">
      <Header onStartOver={() => router.push("/")} />
      <main className="w-full flex-1">
        <div className="mx-auto max-w-[1400px] px-4 pt-10 pb-12 sm:px-8 sm:pt-16 lg:px-12">
          <SectionHeading
            as="h1"
            size="xl"
            eyebrow={<Eyebrow>Atelier design system · Scenar fidelity, made for fashion · dev only</Eyebrow>}
            title={
              <>
                Calm, precise, <Em>cut to measure.</Em>
              </>
            }
            lede="Every primitive in components/ds, rendered in the light theme and the dark projector theme. Spec: docs/DESIGN.md. Values on this page are specimens for review."
            actions={
              <Segmented<View>
                label="Themes shown"
                value={view}
                onChange={setView}
                options={[
                  { value: "both", label: "Both" },
                  { value: "light", label: "Light" },
                  { value: "dark", label: "Dark" },
                ]}
              />
            }
          />
        </div>
        {view !== "dark" && <Band theme="light" />}
        {view !== "light" && <Band theme="dark" />}
      </main>
    </MotionConfig>
  );
}

function Band({ theme }: { theme: "light" | "dark" }) {
  return (
    <div data-theme={theme} className="border-t border-line bg-paper text-fg">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-20 px-4 py-14 sm:px-8 sm:py-20 lg:px-12">
        <div className="flex items-center gap-3">
          <Badge tone="neutral">{theme === "light" ? "Light theme" : "Dark theme · projector"}</Badge>
          <Stitch className="flex-1" />
        </div>
        <Foundations />
        <Brand />
        <Controls />
        <Forms />
        <Navigation />
        <Content />
        <Instruments />
        <Feedback />
      </div>
    </div>
  );
}

function Group({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-8">
      <SectionHeading size="m" eyebrow={<Eyebrow>{title}</Eyebrow>} title={note ?? title} />
      {children}
    </section>
  );
}

function Specimen({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <Label as="p" className="mb-5">
        {label}
      </Label>
      {children}
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ foundations

const COLOURS: { name: string; v: string; note: string }[] = [
  { name: "paper", v: "--paper", note: "page" },
  { name: "paper-2", v: "--paper-2", note: "wells, tracks" },
  { name: "surface", v: "--surface", note: "cards" },
  { name: "fg", v: "--fg", note: "ink" },
  { name: "fg-muted", v: "--fg-muted", note: "secondary" },
  { name: "fg-faint", v: "--fg-faint", note: "meta" },
  { name: "inverse", v: "--inverse", note: "pills, decision" },
  { name: "ok", v: "--ok", note: "connected" },
  { name: "warn", v: "--warn", note: "needs you" },
  { name: "bad", v: "--bad", note: "breach, fake" },
  { name: "tension", v: "--tension-grad", note: "margin vs floor" },
];

function Foundations() {
  return (
    <Group title="Foundations" note="Ink on white. Colour only for meaning: ok · warn · bad and the tension gradient">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {COLOURS.map((c) => (
          <div key={c.name} className="flex flex-col gap-2">
            <span className="h-14 rounded-panel ring-1 ring-line ring-inset" style={{ background: `var(${c.v})` }} />
            <span className="text-small font-medium">{c.name}</span>
            <span className="-mt-2 text-micro text-fg-muted">{c.note}</span>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Specimen label="Type · Inter 300 display (-0.03em), Inter 400–600 UI, Geist Mono for measures">
          <div className="flex flex-col gap-5">
            <p className="text-display-xl">Display XL</p>
            <p className="text-display-l">
              Display L <Em>chapter</Em>
            </p>
            <p className="text-display-m">Display M · section</p>
            <p className="text-title">Title · card heading 500</p>
            <p className="text-body-l text-fg-muted">Body L · ledes and the first paragraph of a section.</p>
            <p className="text-body">Body · 16px at the 17px root; 18px root from 1280px for projectors.</p>
            <p className="text-small text-fg-muted">Small · secondary text, hints, captions.</p>
            <p className="text-micro text-fg-faint">Micro · meta, timestamps.</p>
            <Label>Label · small muted</Label>
            <p className="font-mono text-small tabular">Mono · 42.5 cm · €38.20</p>
          </div>
        </Specimen>
        <div className="flex flex-col gap-4">
          <Specimen label="Radii · chip 8 · field 12 · panel 20 · card 24 · sheet 28 · pill">
            <div className="flex flex-wrap items-end gap-3">
              {["rounded-chip", "rounded-field", "rounded-panel", "rounded-card", "rounded-sheet", "rounded-full"].map((r) => (
                <span key={r} className={`size-14 border border-line-bold bg-paper-2 ${r}`} title={r} />
              ))}
            </div>
          </Specimen>
          <Specimen label="Elevation · e1 resting · e2 hover · e3 overlays">
            <div className="flex gap-4">
              {["shadow-e1", "shadow-e2", "shadow-e3"].map((s) => (
                <span key={s} className={`grid h-16 flex-1 place-items-center rounded-panel border border-line bg-surface text-micro text-fg-muted ${s}`}>
                  {s.replace("shadow-", "")}
                </span>
              ))}
            </div>
          </Specimen>
          <Specimen label="Seam · the one fashion touch">
            <Stitch />
            <Stitch label="Agent → you" className="mt-5" />
          </Specimen>
        </div>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ brand

function Brand() {
  const icons = Object.entries(Icons).filter(([k]) => k.startsWith("Icon")) as [string, (p: { size?: number }) => ReactNode][];
  return (
    <Group title="Brand & icons" note="A needle for a stem, one thread for the letter">
      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <Specimen label="Mark & wordmark">
          <div className="flex flex-wrap items-center gap-6">
            <AtelierMark size={64} />
            <AtelierMark size={40} />
            <AtelierMark size={24} />
            <span className="flex items-center gap-2">
              <AtelierMark size={30} />
              <Wordmark />
            </span>
          </div>
        </Specimen>
        <Specimen label={`Icons · ${icons.length} · 24 grid · 1.75 stroke`}>
          <div className="grid grid-cols-6 gap-2 sm:grid-cols-10 lg:grid-cols-12">
            {icons.map(([name, I]) => (
              <span key={name} title={name} className="grid aspect-square place-items-center rounded-field bg-paper-2 text-fg">
                <I size={18} />
              </span>
            ))}
          </div>
        </Specimen>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ controls

const STATUSES: BadgeStatus[] = [
  "connected",
  "not-connected",
  "unreachable",
  "unverified",
  "fake",
  "measured",
  "sent",
  "received",
  "draft",
  "pending",
  "running",
  "approved",
  "rejected",
  "failed",
  "unknown",
];

function Controls() {
  const [sel, setSel] = useState<string[]>(["Knitwear"]);
  return (
    <Group title="Controls" note="Pills, round controls, tags">
      <div className="grid gap-4 lg:grid-cols-2">
        <Specimen label="Buttons · primary · secondary · ghost · accent · danger">
          <div className="flex flex-wrap items-center gap-3">
            <Button trailing={<IconArrowUpRight size={14} strokeWidth={2.2} />} trailingBadge>
              Enter the studio
            </Button>
            <Button variant="secondary">Read a different trend</Button>
            <Button variant="ghost">Cancel</Button>
            <Button variant="accent">Approve design</Button>
            <Button variant="danger">Exit tour</Button>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button size="sm" icon={<IconPlus size={14} />}>
              Small
            </Button>
            <Button size="md" trailing={<IconArrowRight size={16} />}>
              Medium
            </Button>
            <Button size="lg">Large</Button>
            <Button loading>Saving</Button>
            <Button disabled variant="secondary">
              Disabled
            </Button>
            <LinkButton href="/workspace" variant="secondary" size="sm">
              Link button
            </LinkButton>
          </div>
        </Specimen>
        <Specimen label="Icon buttons · solid · soft · outline · ghost · status dot">
          <div className="flex flex-wrap items-center gap-3">
            <IconButton label="Add" variant="solid">
              <IconPlus size={16} />
            </IconButton>
            <IconButton label="Theme" variant="soft">
              <IconSun size={16} />
            </IconButton>
            <IconButton label="Open" variant="outline">
              <IconArrowUpRight size={16} />
            </IconButton>
            <IconButton label="Refresh" variant="ghost">
              <IconRefresh size={16} />
            </IconButton>
            <IconButton label="System: all connected" variant="solid" dot="ok" dotLive>
              <IconSignal size={16} />
            </IconButton>
            <IconButton label="System: degraded" variant="soft" dot="bad" size="lg">
              <IconSignal size={18} />
            </IconButton>
            <IconButton label="Small" variant="outline" size="sm">
              <IconRuler size={14} />
            </IconButton>
          </div>
        </Specimen>
        <Specimen label="Eyebrows & dots">
          <div className="flex flex-col gap-3">
            <Eyebrow>Customer voice</Eyebrow>
            <Eyebrow numeral="II">Generative ideation</Eyebrow>
            <Eyebrow tone="ok" live>
              Shopify dev store · live
            </Eyebrow>
            <Eyebrow tone="warn">Waiting on you</Eyebrow>
            <div className="flex items-center gap-3">
              <StatusDot tone="ok" live />
              <StatusDot tone="accent" />
              <StatusDot tone="warn" />
              <StatusDot tone="bad" />
              <StatusDot tone="faint" />
            </div>
          </div>
        </Specimen>
        <Specimen label="Chips · garment tags">
          <div className="flex flex-wrap items-center gap-2">
            <Chip>Merino</Chip>
            <Chip dot="accent">Outerwear</Chip>
            <Chip variant="soft">Boxy</Chip>
            <Chip variant="ink" size="sm">
              NEW
            </Chip>
            {["Knitwear", "Denim", "Tailoring"].map((c) => (
              <ChipButton
                key={c}
                selected={sel.includes(c)}
                onClick={() => setSel((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c]))}
              >
                {c}
              </ChipButton>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <GarmentTag>Look A</GarmentTag>
            <GarmentTag code="SKU AT-0142">Cropped bomber</GarmentTag>
            <GarmentTag tone="ink" code="€38.00">Unit cost</GarmentTag>
            <GarmentTag tone="accent">Chosen mill</GarmentTag>
          </div>
        </Specimen>
        <Specimen label="Status badges · one vocabulary" className="lg:col-span-2">
          <div className="flex flex-wrap gap-2">
            {STATUSES.map((s) => (
              <Badge key={s} status={s} />
            ))}
          </div>
        </Specimen>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ forms

function Forms() {
  const [cat, setCat] = useState("outerwear");
  return (
    <Group title="Forms" note="Fields with honest hints">
      <div className="grid gap-4 lg:grid-cols-2">
        <Specimen label="Field · Input · Select · Textarea">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Brand name" hint="As it appears on the tech pack.">
              <Input placeholder="e.g. Maison Nord" />
            </Field>
            <Field label="Target unit cost" optional>
              <Input prefix="€" suffix="per unit" inputMode="decimal" defaultValue="38.00" />
            </Field>
            <Field label="Category">
              <Select value={cat} onChange={(e) => setCat(e.target.value)}>
                <option value="outerwear">Outerwear</option>
                <option value="knitwear">Knitwear</option>
                <option value="tailoring">Tailoring</option>
              </Select>
            </Field>
            <Field label="MOQ" error="Enter a whole number of units.">
              <Input defaultValue="12.5" suffix="units" />
            </Field>
            <Field label="Direction" className="sm:col-span-2" hint="Plain words: what to change, keep or remove.">
              <Textarea rows={3} placeholder="Make it darker, cropped, more Margiela" />
            </Field>
          </div>
        </Specimen>
        <Specimen label="FileDrop">
          <FileDrop
            onFiles={(f) => toast(`${f.length} file${f.length === 1 ? "" : "s"} chosen`, { tone: "info" })}
            accept="image/*,.pdf"
            multiple
            title="Drop mood-board images or a quote PDF"
            hint="PNG, JPG or PDF · up to 10 MB each"
            icon={<IconImage size={18} />}
          />
        </Specimen>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ navigation

function Navigation() {
  const [tab, setTab] = useState("bom");
  const [mode, setMode] = useState("concepts");
  return (
    <Group title="Navigation" note="Tabs, segments, steps">
      <div className="grid gap-4 lg:grid-cols-2">
        <Specimen label="Tabs">
          <Tabs
            label="Tech pack sections"
            value={tab}
            onChange={setTab}
            items={[
              { value: "bom", label: "Bill of materials", count: 7, content: <SkeletonText lines={3} /> },
              { value: "measure", label: "Measurements", content: <p className="text-small text-fg-muted">Graded size chart.</p> },
              { value: "build", label: "Construction", content: <p className="text-small text-fg-muted">Seams and finishes.</p> },
            ]}
          />
        </Specimen>
        <Specimen label="Segmented · Stepper">
          <div className="flex flex-col gap-6">
            <Segmented
              label="Ideation mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: "concepts", label: "Four concepts" },
                { value: "collection", label: "Collection" },
              ]}
            />
            <Stepper
              onSelect={() => undefined}
              steps={[
                { id: "1", numeral: "I", label: "Signal", status: "done" },
                { id: "2", numeral: "II", label: "Concepts", status: "done" },
                { id: "3", numeral: "III", label: "Vibe check", status: "current" },
                { id: "4", numeral: "IV", label: "Production", status: "upcoming" },
              ]}
            />
          </div>
        </Specimen>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ content

function Content() {
  return (
    <Group title="Content" note="Cards, numbers, swatches, tables">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            eyebrow={<Eyebrow>Surface card</Eyebrow>}
            title="Cropped wool bomber"
            description="Default card: white, hairline, e1."
            actions={<Badge status="approved" />}
          />
          <StatGroup>
            <Stat label="Unit cost" value="38.20" unit="EUR" />
            <Stat label="Margin" value="61" unit="%" delta="+4 pts vs floor" deltaTone="ok" />
          </StatGroup>
        </Card>
        <Card variant="inverse">
          <Eyebrow>Inverse · the decision</Eyebrow>
          <p className="mt-4 text-display-m">Approve this look for production?</p>
          <p className="mt-3 text-small text-fg-muted">One per screen: the human&rsquo;s call.</p>
          <div className="mt-6 flex gap-2">
            <Button size="sm">Approve</Button>
            <Button variant="secondary" size="sm">
              Not yet
            </Button>
          </div>
        </Card>
        <Card interactive>
          <Eyebrow>Card · interactive</Eyebrow>
          <p className="mt-4 text-title">Lifts on hover with Scenar&rsquo;s soft shadow.</p>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Specimen label="Swatches · pinked edge · twill">
          <div className="grid grid-cols-3 gap-4 sm:grid-cols-5">
            <Swatch color="#2b2a33" name="Ink navy" code="#2B2A33" />
            <Swatch color="#8a6f5a" name="Tobacco" code="#8A6F5A" />
            <Swatch color="#c9bfae" name="Oat" code="#C9BFAE" />
            <Swatch color="#5d6b4f" name="Moss" code="#5D6B4F" />
            <Swatch color="#a33b2f" name="Madder" code="#A33B2F" />
          </div>
          <SwatchStrip
            className="mt-6"
            colors={[
              { color: "#2b2a33", weight: 4 },
              { color: "#8a6f5a", weight: 3 },
              { color: "#c9bfae", weight: 2 },
              { color: "#5d6b4f", weight: 1 },
              { color: "#a33b2f", weight: 1 },
            ]}
          />
          <div className="mt-5 flex items-center gap-3">
            <Swatch color="#8a6f5a" size="sm" name="Tobacco" code="32%" />
            <Swatch color="#2b2a33" size="xs" />
          </div>
        </Specimen>
        <Specimen label="Stat · large numerals">
          <StatGroup>
            <Stat size="lg" label="Pre-orders" count={128} />
            <Stat size="lg" label="Days to launch" value="14" />
            <Stat size="lg" label="Shopify sales" value="-" caption="Store not connected" />
          </StatGroup>
        </Specimen>
      </div>
      <Table caption="Supplier quotes">
        <THead>
          <Tr>
            <Th>Mill</Th>
            <Th>Country</Th>
            <Th numeric>Unit</Th>
            <Th numeric>MOQ</Th>
            <Th numeric>Lead</Th>
            <Th>Status</Th>
          </Tr>
        </THead>
        <TBody>
          <Tr selected>
            <Td>
              <GarmentTag tone="accent">Lanificio A</GarmentTag>
            </Td>
            <Td>Italy</Td>
            <Td numeric>€36.40</Td>
            <Td numeric>150</Td>
            <Td numeric>42 d</Td>
            <Td>
              <Badge status="received" />
            </Td>
          </Tr>
          <Tr>
            <Td>Fábrica B</Td>
            <Td>Portugal</Td>
            <Td numeric>€33.10</Td>
            <Td numeric>300</Td>
            <Td numeric>35 d</Td>
            <Td>
              <Badge status="unverified" />
            </Td>
          </Tr>
          <Tr muted>
            <Td>Atelier C</Td>
            <Td>Romania</Td>
            <Td numeric>-</Td>
            <Td numeric>-</Td>
            <Td numeric>-</Td>
            <Td>
              <Badge status="unknown" />
            </Td>
          </Tr>
        </TBody>
      </Table>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <Disclosure title="RFQ · Lanificio A (Italian)" leading={<IconMail size={18} />} meta={<Badge status="sent" />} defaultOpen>
            <p className="text-small text-fg-muted">Gentile team, vi chiediamo un preventivo per 150 capi…</p>
          </Disclosure>
          <Disclosure title="Why this number?" meta={<Badge tone="accent">Explained</Badge>}>
            <p className="text-small text-fg-muted">The forecast blends pre-orders so far with last season&rsquo;s sell-through.</p>
          </Disclosure>
        </div>
        <Card>
          <Timeline
            items={[
              { id: "t", title: "Tech pack", status: "done", meta: "1m 12s", description: "BOM, measurements, construction." },
              { id: "r", title: "RFQs to mills", status: "done", meta: "3 sent" },
              { id: "q", title: "Quotes", status: "running", description: "Extracting prices from replies…" },
              { id: "h", title: "Hand-off", status: "waiting", description: "A quote breaks the cost guardrail." },
              { id: "p", title: "Pre-orders", status: "pending" },
              { id: "x", title: "Shopify sync", status: "error", description: "Store returned 401." },
            ]}
          />
        </Card>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ instruments

function Instruments() {
  return (
    <Group title="Instruments" note="Tailoring tools, not dashboards">
      <div className="grid gap-4 lg:grid-cols-2">
        <Specimen label="TapeMeasure · unit cost vs target band">
          <TapeMeasure
            label="Landed unit cost"
            min={20}
            max={60}
            value={36.4}
            format={(n) => `€${n.toFixed(n % 1 ? 2 : 0)}`}
            tickFormat={(n) => String(n)}
            target={{ from: 30, to: 40, label: "Target" }}
            markers={[{ value: 45, label: "Ceiling", tone: "bad" }]}
          />
        </Specimen>
        <Specimen label="TapeMeasure · pre-orders vs MOQ">
          <TapeMeasure
            label="Pre-orders"
            min={0}
            max={200}
            value={128}
            tone="neutral"
            format={(n) => `${Math.round(n)} units`}
            tickFormat={(n) => String(n)}
            markers={[{ value: 150, label: "MOQ 150" }]}
          />
          <TapeMeasure label="No reading yet" min={0} max={200} value={null} className="mt-4" />
        </Specimen>
        <Specimen label="Dial · margin vs guardrail floor">
          <div className="grid grid-cols-1 justify-items-center gap-8 sm:grid-cols-2">
            <Dial
              label="Margin"
              value={61}
              format={(n) => `${Math.round(n)}%`}
              floor={{ value: 55, label: "Floor 55%" }}
              zones={[{ from: 55, to: 100, tone: "ok" }]}
              caption="Quote from Lanificio A"
            />
            <Dial
              label="Margin"
              value={48}
              format={(n) => `${Math.round(n)}%`}
              floor={{ value: 55, label: "Floor" }}
              zones={[{ from: 0, to: 55, tone: "bad" }]}
              caption="Below floor: hand-off"
            />
          </div>
        </Specimen>
        <Specimen label="Ring · confidence · completeness">
          <div className="flex flex-wrap items-center justify-around gap-6">
            <Ring value={0.72} label="Forecast confidence" caption="confidence" />
            <Ring value={0.5} label="Workspace" tone="accent" size={120} caption="3 of 6" display="3/6" />
            <Ring value={null} label="Unknown" size={120} caption="no data yet" />
          </div>
        </Specimen>
        <Specimen label="Radar · customer voice by theme">
          <div className="flex justify-center">
            <Radar
              label="Customer voice by theme"
              axes={["Fit", "Fabric", "Price", "Length", "Care", "Colour"]}
              series={[
                { name: "This drop", values: [0.78, 0.64, 0.42, 0.7, 0.55, 0.81] },
                { name: "Last season", values: [0.6, 0.7, 0.5, 0.45, 0.6, 0.6], dashed: true },
              ]}
            />
          </div>
        </Specimen>
        <Specimen label="FanChart · explained forecast · Sparkline · Progress">
          <FanChart
            label="Pre-order forecast"
            threshold={{ value: 150, label: "MOQ" }}
            points={[
              { x: "W1", p50: 20, actual: 22 },
              { x: "W2", p50: 46, actual: 51 },
              { x: "W3", p50: 80, actual: 84, lo: 80, hi: 84, lo2: 82, hi2: 84 },
              { x: "W4", p50: 110, lo: 92, hi: 130, lo2: 100, hi2: 120 },
              { x: "W5", p50: 138, lo: 104, hi: 172, lo2: 120, hi2: 156 },
              { x: "W6", p50: 162, lo: 114, hi: 210, lo2: 136, hi2: 188 },
            ]}
          />
          <div className="mt-8 grid gap-6 sm:grid-cols-2">
            <div>
              <Label as="p" className="mb-2">
                Pre-orders per day
              </Label>
              <Sparkline label="Pre-orders per day" values={[2, 4, 3, 7, 6, 9, 12, 10, 14]} />
            </div>
            <div className="flex flex-col gap-4">
              <ProgressBar label="Progress to MOQ" detail="128 / 150" value={128 / 150} />
              <ProgressBar label="Planned" value={0.4} stitch tone="accent" />
              <ProgressBar label="Working…" value={null} size="sm" />
            </div>
          </div>
        </Specimen>
      </div>
    </Group>
  );
}

// ------------------------------------------------------------------------------------------------ feedback

function Feedback() {
  const [modal, setModal] = useState(false);
  const [sheet, setSheet] = useState(false);
  return (
    <Group title="Feedback & states" note="Honest when something isn’t there">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <InlineAlert tone="bad" title="Vision model not reachable" hint="Set AMD_VISION_ENDPOINT to your vLLM server" action={<Button size="sm" variant="secondary">Retry</Button>}>
            The trend read needs the vision model. Nothing was generated.
          </InlineAlert>
          <InlineAlert tone="warn" title="Quote breaks the cost guardrail">
            €46.10 per unit is above your €45.00 ceiling. The agent hands this decision to you.
          </InlineAlert>
          <InlineAlert tone="ok" title="Tech pack saved" />
          <InlineAlert tone="info" title="Pre-orders open">
            Share the store link; the forecast updates as orders come in.
          </InlineAlert>
        </div>
        <div className="flex flex-col gap-3">
          <NotConnected service="Shopify dev store" hint="Set SHOPIFY_STORE and SHOPIFY_ADMIN_TOKEN" onRetry={() => undefined}>
            Pre-orders and the live demand tracker appear here once the store is connected.
          </NotConnected>
          <EmptyState icon={<IconMail size={18} />} title="No replies yet" compact actions={<Button size="sm" variant="secondary">Upload a quote</Button>}>
            Mills reply by email; drop a quote PDF here to extract it.
          </EmptyState>
        </div>
        <Specimen label="Skeleton">
          <div className="flex gap-4">
            <Skeleton className="h-28 w-24" rounded="lg" />
            <div className="flex-1">
              <SkeletonText lines={4} />
            </div>
          </div>
        </Specimen>
        <Specimen label="Overlays · Modal · Sheet · Toast (portaled: they follow the page theme)">
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={() => setModal(true)}>
              Open modal
            </Button>
            <Button variant="secondary" onClick={() => setSheet(true)}>
              Open sheet
            </Button>
            <Button variant="secondary" onClick={() => toast("RFQ sent to 3 mills", { description: "Replies arrive by email." })}>
              Show toast
            </Button>
          </div>
        </Specimen>
      </div>
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        eyebrow={<Eyebrow tone="accent">Confirm</Eyebrow>}
        title="Send RFQs to 3 mills?"
        description="Emails go to your real suppliers from the brand address."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModal(false)}>
              Cancel
            </Button>
            <Button variant="accent" onClick={() => setModal(false)}>
              Send
            </Button>
          </>
        }
      />
      <Sheet open={sheet} onClose={() => setSheet(false)} eyebrow={<Eyebrow>Sheet</Eyebrow>} title="Quote evidence">
        <SkeletonText lines={6} />
      </Sheet>
    </Group>
  );
}
