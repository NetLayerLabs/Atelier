# Atelier API Contract (v1)

Single source of truth between `backend/` (FastAPI, port 8787) and `frontend/` (Next.js, port 3100).
All JSON uses camelCase. All IDs are short strings (e.g. `trd_ab12cd`, `dsn_...`, `run_...`).
Image URLs returned by the backend are absolute (e.g. `http://localhost:8000/static/...`) or `data:` URLs.

## Modes

The backend runs in `ATELIER_MODE=mock` (default) or `live`. Each external service can fall back to mock
individually if its env vars are missing, so the demo never hard-fails on stage.

Env vars (backend/.env): `ATELIER_MODE`, `AMD_VLLM_ENDPOINT`, `AMD_VLLM_MODEL`, `AMD_VLLM_API_KEY`,
`AMD_VISION_ENDPOINT`, `AMD_VISION_MODEL`, `AMD_DIFFUSION_ENDPOINT`, `EVOLUS_API_BASE`, `EVOLUS_API_KEY`,
`EVOLUS_WORKSPACE_ID`, `EVOLUS_OUTREACH_WORKFLOW_ID`, `EVOLUS_SHOPIFY_WORKFLOW_ID`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`.

## Types

```ts
type ServiceStatus = { name: string; mode: "mock" | "live"; healthy: boolean; detail?: string };

interface TrendAnalysis {
  id: string;
  trendName: string;
  summary: string;                 // 1-2 sentence editorial description
  garmentType: string;             // e.g. "jacket", "dress", "trousers"
  coreSilhouettes: string[];
  colorPalette: string[];          // hex codes, e.g. "#1F2A44"
  keyFabrics: string[];
  commercialViabilityScore: number; // 1-100
  sourceImageUrls: string[];
  createdAt: string;               // ISO
}

interface Design {
  id: string;
  trendId: string;
  parentDesignId?: string;         // set when produced by /refine
  imageUrl: string;
  prompt: string;                  // diffusion prompt used
  garmentType: string;
  vibe?: string;                   // creative direction text applied
  seed: number;
  createdAt: string;
}

interface TechPack {
  garmentName: string;
  description: string;
  billOfMaterials: { material: string; quantity: string; targetCostPerUnit: number }[];
  measurements: Record<string, string>;
  targetSupplierRegion: string;
  targetRetailPrice: number;       // USD
  productionQuantity: number;
}

interface SupplierEmail {
  supplierName: string;
  region: string;                  // e.g. "Prato, Italy"
  toEmail: string;                 // always a sandbox/test address in mock mode
  subject: string;
  body: string;
  status: "drafted" | "queued" | "sent";
}

interface ShopifyProduct {
  productId: string;
  title: string;
  handle: string;
  url: string;
  price: number;
  status: "preorder";
  imageUrl: string;
}

type StepKey = "techpack" | "supplier_outreach" | "shopify_preorder";
interface PipelineStep {
  key: StepKey;
  label: string;
  status: "pending" | "running" | "done" | "error";
  mode: "mock" | "live";
  startedAt?: string;
  finishedAt?: string;
  log: string[];                   // human-readable agent log lines, appended as the step runs
  error?: string;
}

interface PipelineRun {
  id: string;
  designId: string;
  status: "running" | "completed" | "failed";
  steps: PipelineStep[];           // always 3, in StepKey order above
  techPack?: TechPack;
  supplierEmails?: SupplierEmail[];
  shopifyProduct?: ShopifyProduct;
  createdAt: string;
}
```

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | – | `{ status: "ok", mode: "mock"\|"live", services: ServiceStatus[] }` |
| POST | `/api/trends/analyze` | `multipart/form-data` with `images` (1-6 files) **or** JSON `{ imageUrls: string[] }` **or** JSON `{ preset: string }` | `TrendAnalysis` |
| GET | `/api/trends/presets` | – | `{ id: string; name: string; thumbnailUrl: string }[]` (mood boards; v5 adds `credit`, `images`, see "v5 — Real mood boards") |
| GET | `/api/trends/{trendId}` | – | `TrendAnalysis` |
| POST | `/api/designs/generate` | `{ trendId: string; vibe?: string; count?: number /*default 4*/ }` | `{ designs: Design[] }` |
| POST | `/api/designs/{designId}/refine` | `{ vibe: string; count?: number }` | `{ designs: Design[] }` |
| POST | `/api/designs/{designId}/approve` | `{ productionQuantity?: number }` | `{ runId: string }` (pipeline runs in background) |
| GET | `/api/runs/{runId}` | – | `PipelineRun` (frontend polls every ~800ms until status != "running") |

Errors: non-2xx with `{ detail: string }`.

In mock mode, the pipeline must still feel alive: each step takes ~2-4s and appends log lines progressively,
so the dashboard can animate it on stage.

## v2 — Creative direction & collections

Additive only: every v1 type and endpoint is unchanged, and `/refine` still works.

```ts
// Design gains two optional fields (omitted when unset):
interface Design {
  // ...v1 fields
  directionId?: string;            // set when produced by /direct
  collectionId?: string;           // set on collection looks (and inherited by their /direct children)
}

interface PaletteShift { before: string[]; after: string[]; note: string }   // hex codes, same length

interface CreativeDirection {
  id: string;                      // "dir_..."
  designId: string;                // the design the direction was applied to
  instruction: string;             // what the CD typed or said
  interpretation: string;          // one sentence the agent says back
  promptAdditions: string[];
  promptRemovals: string[];
  paletteShift?: PaletteShift;
  silhouetteChanges: string[];
  techPackHints: string[];         // e.g. "Shorten body length 6cm — crop to the high hip"
  references: string[];            // designer / era refs, "Name — what it means here"
  mode: "mock" | "live";           // which interpreter actually ran
  createdAt: string;
}

interface CollectionLook { designId: string; title: string; caption: string }

interface Collection {
  id: string;                      // "col_..."
  trendId: string;
  name: string;
  story: string;                   // short editorial story
  designs: Design[];               // normal designs: select / direct / approve as usual
  looks: CollectionLook[];         // same order as designs
  mode: "mock" | "live";
  createdAt: string;
}
```

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/designs/{designId}/direct` | `{ instruction: string /*1-500 chars*/; count?: number /*1-8, default 4*/ }` | `{ direction: CreativeDirection; designs: Design[] }` |
| GET | `/api/directions/{directionId}` | – | `CreativeDirection` |
| POST | `/api/collections/generate` | `{ trendId: string; size?: number /*3-5, default 4*/ }` | `Collection` |
| GET | `/api/collections/{collectionId}` | – | `Collection` |

Semantics:

- `/direct` interprets the instruction with the vLLM chat model in live mode, or with a deterministic keyword
  interpreter in mock mode (and on any live failure). It then renders `count` children with `parentDesignId`,
  `vibe = instruction` and `directionId`.
- Directions accumulate along the lineage, so directing a directed design stacks the changes. When a design is
  approved, the tech pack gets the accumulated direction. In mock mode that changes the palette and fabric swaps,
  length and ease measurements (plus a `"Δ vs. base block (creative direction)"` entry), the BOM (added and
  replaced lines, with shell yardage and cost rescaled), the retail price and the description
  (`"Direction applied: …"`). In live mode the hints are added to the LLM brief.
- `TechPack` gains an optional `colorway?: string[]` (hex codes): the effective palette after the lineage's
  directions (or the collection look's rotation), i.e. the trend palette when nothing re-coloured it. The PDF's
  colourway chips / table and the dashboard's tech pack read it instead of `TrendAnalysis.colorPalette`.
- Collection looks use different garment types that share the trend's palette and fabrics. Each look leads with
  its own colour and fabric, and the tech pack follows that look.

## v2 — Live infrastructure & inference stats

Additive only: every new field is optional, so v1 clients keep working.

### New / changed types

```ts
type ServiceStatus = {
  name: string; mode: "mock" | "live"; healthy: boolean; detail?: string;
  model?: string;      // v2: model id a live probe saw (GET /v1/models, diffusion /health)
  host?: string;       // v2: endpoint host:port that was probed
  latencyMs?: number;  // v2: probe round-trip
};

type TelemetryService = "llm" | "vision" | "diffusion" | "evolus";

interface InferenceCall {
  id: string;                // "inf_…"
  service: TelemetryService;
  purpose: string;           // "techpack" | "rfq_emails" | "trend_analysis" | "design_render" | "supplier_outreach" | "shopify_preorder" | …
  mode: "mock" | "live";
  simulated: boolean;        // true <=> mode "mock": numbers are SIMULATED, the UI must say so
  ok: boolean;
  fallback: boolean;         // a mock call made because the live call failed
  model?: string;
  endpointHost?: string;     // "simulated" for mock calls
  gpu?: string;              // live: AMD_GPU_LABEL, or the device the diffusion server reports; never guessed
  startedAt: string;         // ISO
  latencyMs: number;         // wall clock, measured
  ttftMs?: number;           // time to first token (streamed calls only)
  promptTokens?: number;     // from the server's OpenAI `usage`; absent if the server sent none
  completionTokens?: number;
  totalTokens?: number;
  tokensPerSec?: number;     // completionTokens / (latency - ttft)
  images?: number;
  imagesPerSec?: number;     // diffusion: 1 / (serverMs ?? latencyMs)
  serverMs?: number;         // compute time reported by the upstream (diffusion server's elapsedMs)
  attempt: number;           // 1, or 2 for the JSON retry
  error?: string;
  detail?: string;
}

interface ServiceTelemetry {   // aggregates per (service, mode); live and simulated are never averaged together
  service: TelemetryService; mode: "mock" | "live";
  calls: number; errors: number; fallbacks: number;
  avgLatencyMs?: number; p95LatencyMs?: number; avgTtftMs?: number;
  promptTokens: number; completionTokens: number;
  avgTokensPerSec?: number; peakTokensPerSec?: number;
  images: number; avgImagesPerSec?: number;
  lastModel?: string; lastEndpointHost?: string; gpu?: string; lastAt?: string;
}

interface TelemetryResponse {
  mode: "mock" | "live";
  gpuLabel?: string;           // AMD_GPU_LABEL; absent when unset
  calls: InferenceCall[];      // newest first
  services: ServiceTelemetry[];
}

interface PipelineStep { /* v1 fields … */ telemetry?: InferenceCall[] }  // calls made by this step, live-updating
```

### New endpoint

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/telemetry` | `limit` (0-500, default 50), `service` (`llm`\|`vision`\|`diffusion`\|`evolus`) | `TelemetryResponse` |

The buffer is in memory (`ATELIER_TELEMETRY_SIZE`, default 300 calls) and resets when the backend restarts.

### Behaviour changes

- `GET /api/health` now **probes** live services instead of just reporting config. It calls vLLM `GET /v1/models`,
  the diffusion server's `GET /health`, and the Evolus `GET {EVOLUS_PROBE_PATH}`. Probes use
  `ATELIER_HEALTH_TIMEOUT` (2.5s) and are cached for `ATELIER_HEALTH_CACHE_SECONDS` (5s); Evolus probes are cached
  for `EVOLUS_PROBE_CACHE_SECONDS` (30s) because of its 60 req/min limit. A failing probe sets `healthy: false`.
  Requests still try the live service and fall back to mock per call.
- Evolus is now called the way the public docs describe (https://evolus.ai/developers):
  - Auth: `X-ApiKey` + `X-Application-Id` (`EVOLUS_WORKSPACE_ID`).
  - `POST /api/v1/workflows/{id}/execute` as multipart, with fields `input` and `parameters`. It returns 202.
  - The backend then polls `GET …/executions/{executionId}` until `Completed` or `Failed`.
  - Workflow parameters must be flat. Nested values are sent as JSON strings.
    - Outreach: `garment_name`, `production_quantity`, `tech_pack`, `image_url`, `rfq_emails`.
    - Shopify: `title`, `description`, `price`, `image_url`, `handle`, `production_quantity`.
- A service is Evolus-live only when `EVOLUS_API_KEY`, `EVOLUS_WORKSPACE_ID` and the workflow id are all set.
- Live pipeline log lines no longer name a model or GPU that wasn't configured. They read
  "Calling <AMD_VLLM_MODEL | the served model> via vLLM @ host · <AMD_GPU_LABEL>", followed by an
  `Inference: …` line with the measured stats. Mock log lines say "(simulated)".

### New env vars (backend/.env, all optional)

`AMD_GPU_LABEL`, `AMD_DIFFUSION_API_KEY`, `ATELIER_VISION_TIMEOUT`, `ATELIER_HEALTH_TIMEOUT`,
`ATELIER_HEALTH_CACHE_SECONDS`, `ATELIER_LLM_STREAM`, `ATELIER_LLM_JSON_MODE`, `ATELIER_LLM_EXTRA_BODY`,
`ATELIER_TELEMETRY_SIZE`, `EVOLUS_EXECUTE_PATH`, `EVOLUS_STATUS_PATH`, `EVOLUS_PROBE_PATH`, `EVOLUS_API_KEY_HEADER`,
`EVOLUS_APP_ID_HEADER`, `EVOLUS_SEND_PARAMETERS`, `EVOLUS_POLL_INTERVAL`, `EVOLUS_POLL_TIMEOUT`,
`EVOLUS_PROBE_CACHE_SECONDS`, `EVOLUS_AGENT_MODEL`.

## v2 — Business loop

Everything after approval: supplier quotes and a recommendation, a pre-order demand window that must clear a
production threshold, a purchase order, plus live tech pack editing and a PDF export. All additions are additive;
v1 fields and endpoints are unchanged.

### Pipeline changes

```ts
type StepKey =
  | "techpack" | "supplier_outreach"
  | "supplier_quotes"      // NEW: mills reply, agent scores and recommends
  | "shopify_preorder"
  | "preorder_demand";     // NEW: 14-day pre-order window -> PO when the threshold is crossed
```

`PipelineRun.steps` now has **5** steps in the order above (clients should render `steps` generically).
`run.status` stays `"running"` until the demand step finishes (threshold crossed and PO issued, or the window
closes), so polling naturally covers the demand simulation. `supplier_quotes.mode` is `"live"` only when the LLM
drafted the rationale; the quotes themselves are **always simulated**. `preorder_demand.mode` is always `"mock"`.

### New types

```ts
interface ScoreBreakdown { price: number; moq: number; leadTime: number }   // 0-100 each (weights: 0-1)

interface SupplierQuote {
  supplierName: string;
  region: string;
  unitPrice: number;        // USD per finished garment, full package, FOB
  moq: number;              // units per colour
  leadTimeWeeks: number;    // after PP-sample approval
  sampleCost: number;       // USD
  paymentTerms: string;
  note: string;             // short reply in the mill's voice
  receivedAt: string;       // ISO
  simulated: true;
  score: number;            // 0-100, weighted
  scoreBreakdown: ScoreBreakdown;
}

interface SupplierRecommendation {
  supplierName: string;            // the agent's pick (highest score)
  rationale: string;
  score: number;
  weights: ScoreBreakdown;         // { price: 0.45, moq: 0.30, leadTime: 0.25 }
  mode: "mock" | "live";           // live = rationale drafted by the LLM
  selectedSupplierName: string;    // == supplierName unless the user overrode it
  overridden: boolean;
}

interface DemandPoint { hour: number; orders: number }   // simulated hours since launch, cumulative orders

interface PurchaseOrder {
  poNumber: string;        // e.g. "PO-2610-4405"
  supplierName: string;
  region: string;
  quantity: number;        // = demand.threshold
  unitPrice: number;       // selected quote's unitPrice
  total: number;
  leadTimeWeeks: number;
  issuedAt: string;        // ISO
  status: "issued";
  simulated: true;
}

interface PreorderDemand {
  status: "collecting" | "unlocked" | "expired";
  simulated: true;
  threshold: number;                       // max(techPack.productionQuantity, selected quote MOQ)
  thresholdBasis: "productionQuantity" | "moq";
  orders: number;                          // cumulative pre-orders (1 unit each)
  revenue: number;                         // USD collected
  visitors: number;
  conversionRate: number;                  // 0..1
  windowHours: number;                     // 336 (14 days)
  elapsedHours: number;                    // simulated
  hoursLeft: number;
  speed: number;                           // "simulate faster" multiplier
  series: DemandPoint[];                   // starts at {hour: 0, orders: 0}, monotonic
  unlockedAtHour?: number;
  purchaseOrder?: PurchaseOrder;
}

interface MaterialOption {
  material: string;           // full BOM material string (placement suffix preserved)
  targetCostPerUnit: number;  // USD per garment for this BOM line
  note: string;
  tag?: string;               // "recycled" | "organic" | "premium" | "lower-impact" | ...
  original: boolean;          // the agent's original choice
}
interface BomAlternatives { index: number; family: string; options: MaterialOption[] }

// PipelineRun gains (all optional on the wire until set):
interface PipelineRun {
  // ...v1 fields...
  originalTechPack?: TechPack;        // the agent's first draft (baseline for "vs original" deltas)
  techPackRevision: number;           // 0 = agent draft; +1 per PATCH
  quotes?: SupplierQuote[];           // grows as replies arrive (a few seconds apart)
  recommendation?: SupplierRecommendation;   // set once all quotes are in
  demand?: PreorderDemand;            // set when the demand step starts
}
```

### New endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| PATCH | `/api/runs/{runId}/techpack` | any subset of `TechPack` fields (`billOfMaterials` min 1 line, costs ≥ 0; `targetRetailPrice` > 0; `productionQuantity` ≥ 1) | `PipelineRun` — bumps `techPackRevision`; until the PO is issued it re-prices quotes, re-scores, refreshes the recommendation (a user override is kept) and syncs the demand threshold; a new retail price also updates `shopifyProduct.price` |
| GET | `/api/runs/{runId}/techpack/alternatives` | – | `{ lines: BomAlternatives[] }` — swappable materials per BOM line (CMT, labels, thread, interlinings, zips are not swappable), costed against `originalTechPack` |
| GET | `/api/runs/{runId}/techpack.pdf` | – | `application/pdf` attachment: cover with design render, BOM & costing, points of measure & construction, colourways (hex + approx. TCX), supplier & quantities, revision date |
| POST | `/api/runs/{runId}/supplier` | `{ supplierName: string }` | `PipelineRun` — creative-director override; `409` before quotes are in or after the PO is issued, `404` for an unknown supplier |
| POST | `/api/runs/{runId}/demand/speed` | `{ speed: number /* 0.25-50 */ }` | `PipelineRun` — "simulate faster" |

`409` for tech pack / PDF / alternatives requests before the tech pack exists; `404` for unknown runs.

### Simulation & pacing

- Quotes arrive ~1.2–2s apart in random order after the RFQs are queued. Price = BOM unit cost × the supplier's
  profile multiple (`data/suppliers.py`) × seeded ±5% variance; MOQ / lead time / terms come from the profile.
- Scoring: price = 100 × cheapest / price; MOQ fit = 100 if MOQ ≤ run else 100 × (run / MOQ)²; lead time = 100 →
  65 across the 10-week production budget (12-week delivery promise − 2-week window), then −20/week.
- Demand: seeded launch-day spike + S-curve, calibrated so the threshold is crossed mid-window and even the
  highest quoted MOQ is reachable before day 14. At 1× and `ATELIER_DELAY_SCALE=1` the threshold is crossed after
  `ATELIER_DEMAND_SECONDS` (default 36) real seconds; `speed` divides that. Tests use `ATELIER_DELAY_SCALE=0`.

## v3 — Explained production forecast

"How many should we make?" Additive only. The forecast is **deterministic statistics with no language model**:
closed forms and exact sums over a probability mass function, with no sampling. The same inputs always give the same
answer. Code: `backend/app/services/forecast.py` (pure), `backend/app/routers/forecast.py`,
`frontend/src/components/ForecastPanel.tsx`.

### Model

| Step | Formula | Learned or assumed |
|---|---|---|
| Launch curve | `F(t) = (1 − e^{−(p+q)t}) / (1 + (q/p)·e^{−(p+q)t})`, `G(t) = F(t)/F(T)` (Bass diffusion, t in days) | shape **assumed** (p, q) |
| Prior | window level `Λ ~ Gamma(α₀ = 1/CV², β₀ = α₀/m₀)` | **assumed** "comparable launch" |
| Posterior | `α = α₀ + U`, `β = β₀ + G(t)` (U = units ordered by t) | **learned** from orders |
| Uncertainty floor | if `α > 1/CV_floor²`, rescale `α, β` to that α, keeping `α/β` | **assumed** |
| Pre-orders by window end | `U + NB(r = α, p = β/(β + 1 − G))` → mean, P10/P50/P90 | — |
| Season demand | `D = U + NB(r = α, p = β/(β + M − G))`, M = season ÷ pre-orders | M **assumed** |
| Critical ratio | `CR = (p − c)/(p − s)`; underage `p − c`, overage `c − s` | price, cost, salvage |
| Newsvendor | `q* = min{q : P(D ≤ q) ≥ CR}`; recommend `max(q*, MOQ)` (with a note when the MOQ binds) | — |
| Outcome | `E[sold] = Σ_{j<q} P(D > j)`, `E[π] = p·E[sold] + s·(q − E[sold]) − c·q − F` | — |
| Size split | `share_s = (n_s + κ·b_s)/(N + κ)`, then largest-remainder rounding (sums exactly to q) | base curve b **assumed** |

Notes: if `s ≥ c`, salvage is capped just below cost. If `p ≤ c`, q* = 0. With zero orders the result is the
prior predictive, labelled `confidence: "prior-only"`. Confidence is `prior-only` (U = 0), `early` (U < 20 or data
weight < 50%), `firming` (80% interval wider than ±25%) or `data-driven`.

Default assumptions (`ForecastAssumptions`, all overridable in `POST /api/forecast`):
`priorMeanPreorders` 250, `priorCv` 0.75, `bassP` 0.06/day, `bassQ` 0.25/day, `seasonMultiplier` 2.5,
`sizeCurve` {XS .08, S .22, M .32, L .24, XL .14}, `sizePriorStrength` κ = 20, `unsoldRiskThreshold` 0.2,
`levelCvFloor` 0.12. `salvageValue` defaults to 50% of unit cost.

## v3 — Customer voice

The merchant uploads their own customer data (product reviews, return reasons, support tickets; CSV/TSV
exports or PDFs). Atelier finds patterns and turns them into concrete, cited tech pack changes. Additive only.

Analysis is **deterministic** (`backend/app/services/voice_taxonomy.py`): an apparel taxonomy of phrase and
proximity rules (fit by point of measure, sizing, fabric, colour vs photo, construction, care, comfort, warmth,
value, returns). It handles negation ("not tight at all" is not tight; "not warm enough" flips to *not warm*),
hedging ("worried it would pill") and body descriptions ("I have broad shoulders"). Polarity comes from the rule,
or from the star rating for ambiguous themes (≤3★ negative, ≥4★ positive). Each record counts at most once per
theme. Every number comes from this pass. In live mode the LLM may only phrase `summary` and each change's
`rationale`; any text containing a number that is not in the deterministic facts is dropped.

### Types

```ts
interface OrderEvent { timestamp: string /*ISO*/; quantity: number /*>=1, default 1*/; size?: string; unitPrice?: number }
interface ForecastEconomics { unitCost: number; retailPrice: number; salvageValue?: number; moq: number /*default 0*/; fixedCosts: number /*default 0*/ }
interface ForecastRequest {
  orders: OrderEvent[]; launchAt: string; asOf?: string /*default now, clamped to the window*/;
  windowHours: number /*default 336*/; economics: ForecastEconomics; assumptions?: Partial<ForecastAssumptions>;
  plannedQuantity?: number /*baseline to compare*/; simulated?: boolean;
}
interface Forecast {
  method: "gamma-poisson-bass-newsvendor"; llmUsed: false; simulated: boolean;
  confidence: "prior-only" | "early" | "firming" | "data-driven"; confidenceNote: string;
  recommendedQuantity: number; unconstrainedQuantity: number /*q* before MOQ*/; moq: number; moqBinding: boolean; moqNote?: string;
  criticalRatio: number; underageCost: number; overageCost: number;
  unitCost: number; retailPrice: number; salvageValue: number; fixedCosts: number;
  preorders: { mean; p10; p50; p90 };  season: { mean; p10; p50; p90 };  observedUnits: number;
  outcome: ForecastOutcome; baseline?: ForecastOutcome /*at plannedQuantity*/; profitDeltaVsBaseline?: number;
  sizes: { size; orders; baseShare; share; units }[];
  projection: { hour; mean; p10; p90 }[];  observed: { hour; units }[];  profitCurve: { quantity; expectedProfit }[];
  posterior: { priorAlpha; priorBeta; alpha; beta; windowLevelMean; dataWeight };
  explanation: { summary; steps: { title; formula; substituted; result }[]; assumptions: { key; label; value; note }[];
                 data: ForecastDataUsed; notes: string[] };
  inputs: ForecastRequest /*normalised echo: POST it back with tweaks*/; asOf: string; launchAt: string;
}
interface ForecastOutcome { quantity; expectedUnitsSold; expectedLeftover; expectedRevenue; expectedSalvage; expectedCost;
  expectedProfit; expectedMargin /*profit ÷ (revenue + salvage)*/; stockoutProbability; fillRate; unsoldRiskProbability }
```

Full TS definitions are in `frontend/src/lib/types.ts`.

interface VoiceQuote {                 // an exact excerpt of one record (never paraphrased)
  recordId: string;                    // sample: "r<dataset row id>", upload: the id column or "row-<n>" (header = row 1), PDF: "p<page>-<n>"
  field: "text" | "title" | "returnReason" | "fitFeedback";
  text: string;                        // exact substring of that field (return reason / fit feedback: the raw cell)
  truncated: boolean;                  // a window of a longer sentence: render with "…"
  matchStart?: number; matchEnd?: number;   // the matched phrase inside `text`
  rating?: number;                     // 1-5
  garmentClass?: string;
}

interface VoiceSource {
  kind: "upload" | "sample";
  filename?: string; datasetKey?: string;
  title?: string;                      // "Your upload: reviews.csv" | "Public review dataset: Jackets & outerwear"
  url?: string; licence?: string; attribution?: string;   // samples only
}

interface VoiceClassCount { garmentClass: string; count: number; total: number; share: number }  // share = 100*count/total

interface VoiceTheme {
  id: string;                          // e.g. "fit.shoulders_tight", "fabric.pilling"
  group: "fit" | "fabric" | "colour" | "construction" | "care" | "comfort" | "warmth" | "value" | "returns";
  groupLabel: string; name: string;
  kind: "problem" | "praise" | "rating";
  polarity: "negative" | "positive" | "mixed";   // >= 60% of mentions one way, else mixed
  count: number;                       // records mentioning it
  share: number;                       // 100 * count / analysedCount, 1 dp
  negativeCount: number; positiveCount: number; neutralCount: number;
  avgRating?: number;                  // of the records that mention it
  returnedCount: number;               // mentions in records that also mention a return / have a return reason
  byClass: VoiceClassCount[];          // top 6
  quotes: VoiceQuote[];                // up to 4, distinct records
  recordIds: string[];                 // up to 200
}

interface ChangeEvidence {
  count: number; base: number; share: number;    // "count of base", scoped to garmentClass when one class carries >= 50%
  garmentClass?: string;
  avgRating?: number; baselineRating?: number;   // supporting records vs. everything in the same scope
  summary: string;                     // "16 of 139 reviews for Jackets (11.5%) mention it running large; they average 4.0★ vs 4.3★"
  recordIds: string[];                 // up to 50
  quotes: VoiceQuote[];                // up to 3; their recordIds are the [refs] in techPackChange
}

interface RecommendedChange {
  id: string;                          // "chg_<theme>", stable per theme, e.g. "chg_fit_shoulders_tight"
  themeId: string;
  title: string;                       // "Add shoulder & bicep ease"
  action: string;                      // the factory instruction
  techPackChange: string;              // "<action> — 23 of 139 reviews for Jackets mention tight shoulders [refs: r12, r40, r77]"
  area: "measurements" | "bom" | "construction" | "testing" | "colour" | "pricing";
  measurements: Record<string, string>;          // point of measure -> change, e.g. { "Across shoulder": "+1.5cm" }
  bomAdditions: BomLine[];                       // costed lines the change adds (anti-pill finish, zip upgrade…)
  confidence: "high" | "medium" | "low";         // high: >= 12 records and >= 5%; medium: >= 6 or >= 3%
  priority: number;                    // count × (1 + rating drop vs scope) × 1.5 if share >= 10%
  evidence: ChangeEvidence;
  rationale?: string;                  // live mode only, LLM-phrased, no numbers of its own
  conflictsWith: string[];             // opposite changes that also have evidence ("runs small" vs "runs large")
}

interface VoiceInsights {
  id: string;                          // "voc_..."
  name: string; source: VoiceSource;
  noun: "reviews" | "returns" | "tickets" | "comments" | "records";
  recordCount: number; analysedCount: number;    // analysed = records with any text
  columns: { text?; title?; rating?; garmentClass?; product?; size?; fitFeedback?; returnReason?; date?; id?; helpful? };  // detected source headers
  avgRating?: number;
  garmentClasses: VoiceClassCount[];
  themes: VoiceTheme[];                // sorted by count desc
  recommendedChanges: RecommendedChange[];       // sorted by priority desc, max 12
  summary: string; method: string; warnings: string[];
  mode: "mock" | "live";               // live = the LLM phrased summary/rationales
  createdAt: string;
}

interface CustomerEvidence {           // a change as applied to a tech pack
  datasetId: string; datasetName: string; source: string;
  changeId: string; title: string;
  techPackChange: string;              // re-phrased for the design's garment kind (inseam vs body length…)
  area: string; count: number; base: number; share: number; garmentClass?: string;
  recordIds: string[]; quotes: VoiceQuote[];
  measurements: Record<string, string>; bomAdditions: BomLine[];
}

interface TechPack { /* … */ customerEvidence?: CustomerEvidence[] }   // omitted when nothing was applied
```

### Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/forecast` | `ForecastRequest` | `Forecast` (stateless; 422 on invalid input) |
| GET | `/api/runs/{runId}/forecast` | – | `Forecast` built from the run: unit cost, MOQ and sample cost (as `fixedCosts`) from the **selected quote** (BOM cost if there are no quotes yet), price = `shopifyProduct.price` or the tech pack retail, `plannedQuantity` = `techPack.productionQuantity`, orders and window via the seam below. 404 for an unknown run, 409 before the tech pack exists |

The dashboard polls the GET every 2.5s while `demand.status == "collecting"`. When the user moves the salvage or
season-multiplier sliders, it POSTs the latest `inputs` with the overrides.

### Integration seam (real orders)

`forecast.py` reads a run's demand data in **only two functions**:

- `orders_for_run(run) -> list[OrderEvent]`
  - **Real orders:** if `run.demand.orders` is a **list** (or `run.demand.events` / `orderEvents` / `order_events`
    is), each item, a dict or a model, is read for:
    - timestamp: `timestamp` | `createdAt` | `created_at` | `processedAt`
    - quantity: `quantity` | `qty` (default 1)
    - size: `size` | `variant` | `variantTitle` | `variant_title` | `option1`
    - price: `unitPrice` | `unit_price` | `price`

    Items without a timestamp are skipped. To feed real Shopify orders, store one entry per line item there.
  - **Simulated (today):** `run.demand.orders` is an int. Each increase in `run.demand.series` becomes one event at
    `launch + hour`, priced at the storefront price, with no size.
- `window_for_run(run) -> (launch, asOf, windowHours)`
  - launch: `demand.launchedAt` | `launchAt` | `startedAt` | `openedAt`, else the `preorder_demand` step's
    `startedAt`, else `run.createdAt`.
  - asOf: `launch + demand.elapsedHours` when that is > 0 or the data is simulated. Otherwise it is now, clamped to
    the window.
  - windowHours: `demand.windowHours`, default 336.

`Forecast.simulated` mirrors `run.demand.simulated`.

## v3 — Real Shopify pre-orders

The pre-order is a **real product in a real Shopify store**, and demand is **real orders**. The simulated listing
and demand curve from v2 remain only behind `ATELIER_ALLOW_SIMULATION=1` (default off), and everything they produce
is labelled SIMULATED. Every change is additive: v2 clients keep parsing, but the default behaviour changed (see
"Not connected"). Setup: [docs/SHOPIFY_SETUP.md](docs/SHOPIFY_SETUP.md).

### Step behaviour

- `shopify_preorder` uses the **Evolus Shopify workflow** when it is configured and its output contains a Shopify
  product id (`gid://shopify/Product/…` or digits). The product is then checked through the Admin API when the
  backend has access. Otherwise Atelier creates it **directly** through the Admin GraphQL API
  (`SHOPIFY_API_VERSION`, default `2026-10`). The direct path is: staged upload of the design as PNG (SVG mock
  renders are rasterised with resvg) → `productCreate` (`<garment> — Pre-order`, tags `pre-order`, `atelier`,
  status `ACTIVE`) → `productVariantsBulkUpdate` (price, `inventoryPolicy: CONTINUE`, untracked) →
  `publishablePublish` to the Online Store. `mode` is `"live"` for either real path.
- `preorder_demand` tracks real orders containing the product:
  - It polls the Admin API `orders` every `SHOPIFY_POLL_INTERVAL` s (default 4). This works from localhost.
  - It also accepts the `orders/create` webhook (below).
  - Both sources de-duplicate by order id. Cancelled orders are ignored. Test-payment orders count when
    `SHOPIFY_COUNT_TEST_ORDERS=true` (default) and are flagged `test`.
  - `mode` is `"live"`.
  - The window is real time (`SHOPIFY_DEMAND_WINDOW_HOURS`, default 336).
  - `run.status` stays `"running"` until the threshold is crossed or the window ends.
- **Threshold.** The production threshold is still `max(techPack.productionQuantity, selected quote MOQ)`.
  `DEMAND_STAGE_THRESHOLD=N` (> 0) makes **N real pre-order units** unlock the PO for a live demo. The UI must
  show it as "stage threshold: N pre-orders (production plan: P units)". The PO is always for the production
  plan (`productionThreshold`). `PurchaseOrder.simulated` stays `true`: no order is sent to a mill.
- **Not connected.** If no Shopify store is configured and simulation is off, the run fails honestly:
  - `shopify_preorder` gets `status: "error"`, and its `error` starts with `"Shopify not connected — "` followed
    by a setup hint.
  - `preorder_demand` gets `status: "error"`.
  - `run.status` is `"failed"`, and `shopifyProduct` / `demand` are absent.
  - The steps before it (tech pack, outreach, quotes) are unaffected.
- **Price edits.** `PATCH /techpack` with `targetRetailPrice` also updates the real variant price (in the
  background, best effort; the result is logged on the Shopify step).
- `POST /api/runs/{id}/demand/speed` returns **409** for real demand.

### Type changes (additive)

```ts
interface ShopifyProduct {
  // ...v1 fields
  source?: "shopify" | "evolus" | "simulated";  // evolus = created by the Evolus workflow
  simulated?: boolean;          // false <=> the product exists in a Shopify store
  adminUrl?: string;            // https://admin.shopify.com/store/<store>/products/<id>
  shopDomain?: string;          // "<store>.myshopify.com"
  shortUrl?: string;            // shown under the QR code (SHOPIFY_SHORT_URL, else host/products/handle)
  qrUrl?: string;               // GET /api/runs/{id}/storefront-qr.svg, encodes `url`
  storefrontPassword?: string;  // only when SHOPIFY_STOREFRONT_PASSWORD is set
  variantId?: string;
  published?: boolean;          // published to the Online Store channel
}

interface PreorderOrder {        // privacy: first name + city only — never surname, email or street
  orderId: string; name: string /* "#1001" */; createdAt: string;
  units: number; amount: number /* this product's lines, after discounts */; currency: string;
  firstName?: string; city?: string; test: boolean; via: "poll" | "webhook" | "simulated";
}

interface PreorderDemand {
  // ...v2 fields; `threshold` is what `units` must reach (the stage threshold when set)
  thresholdBasis: "productionQuantity" | "moq" | "stage";
  source?: "shopify" | "simulated";
  units?: number;                       // real: units across orders (`orders` = number of orders)
  productionThreshold?: number;         // max(productionQuantity, MOQ): the PO quantity
  productionThresholdBasis?: "productionQuantity" | "moq";
  stageThreshold?: number;              // DEMAND_STAGE_THRESHOLD when in effect
  currency?: string;
  recentOrders?: PreorderOrder[];       // newest first, at most 12
  testOrders?: number;
  tracking?: string;                    // e.g. "Admin API poll every 4s + orders/create webhook"
  lastCheckedAt?: string;
  trackingError?: string;               // last poll error, cleared by the next good poll
}
```

For real demand: `simulated: false`, `visitors` and `conversionRate` are `0` (not measured), `speed` is `1`, and
`series` holds cumulative **units** against real hours since launch (one point per order).

### New endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/runs/{runId}/storefront-qr.svg` | – | `image/svg+xml` QR code (generated locally) for `shopifyProduct.url`; `409` before a product URL exists |
| POST | `/api/webhooks/shopify/orders-create` | raw Shopify `orders/create` JSON | `{ ok, order, runs }`; `401` on a missing or invalid `X-Shopify-Hmac-Sha256`; `503` when no secret is configured; other `X-Shopify-Topic` values are ignored |

The signature is `base64(HMAC-SHA256(SHOPIFY_WEBHOOK_SECRET || SHOPIFY_CLIENT_SECRET, raw body))`, compared in
constant time.

`GET /api/health` gains a `shopify` service:
- `live` when a store is configured. It probes `shop` plus the access scopes and is unhealthy if `write_products`
  or `read_orders` is missing.
- Otherwise `mock` and `healthy: false` with "Not connected …". With `ATELIER_ALLOW_SIMULATION=1` it is
  `healthy: true` and says SIMULATED.

### New env vars (backend/.env)

- Store and auth:
  - `SHOPIFY_STORE_DOMAIN`
  - `SHOPIFY_ADMIN_TOKEN`, or `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` (Dev Dashboard client-credentials
    grant; the 24 h token is cached and refreshed)
  - `SHOPIFY_API_VERSION`
- Storefront: `SHOPIFY_STOREFRONT_PASSWORD`, `SHOPIFY_SHORT_URL`, `SHOPIFY_PUBLISH`
- Order tracking: `SHOPIFY_WEBHOOK_SECRET`, `SHOPIFY_POLL_INTERVAL`, `SHOPIFY_COUNT_TEST_ORDERS`,
  `SHOPIFY_DEMAND_WINDOW_HOURS`, `SHOPIFY_TIMEOUT`
- Thresholds and simulation: `DEMAND_STAGE_THRESHOLD`, `ATELIER_ALLOW_SIMULATION`

Shopify doesn't depend on `ATELIER_MODE`: real credentials are the opt-in.

## v3 — Evolus brain & real quotes

Additive: every new field is optional on the wire, and no v1/v2 endpoint changed shape. **One behaviour change:**
supplier quotes are no longer simulated. The `supplier_quotes` step now waits for real quote documents. With
`ATELIER_ALLOW_SIMULATION=1` (the same flag that gates the simulated Shopify listing and demand above) the round
still opens for real documents first; only if none has arrived after `ATELIER_SIMULATED_QUOTES_AFTER` seconds
(default 90, × `ATELIER_DELAY_SCALE`) are quotes simulated, and then they are labelled SIMULATED, as in v2.
Demo mode uploads the role-play quote PDFs inside that window, so even a no-credentials demo shows real extraction.

### The brain (fallback chain)

The tech pack, RFQ drafts, creative-direction interpretation and supplier rationale all go through one chain
(`services/brain.py`):

1. `"evolus-agent → AMD vLLM"`: the Evolus agent `EVOLUS_AGENT_MODEL` (`<spaceId>:<agentId>`) over
   `POST https://api.evolus.ai/v1/chat/completions` (Bearer key). With `EVOLUS_AGENT_TRANSPORT=rest`, it uses
   `POST /api/v1/agents/{agentId}/ask` instead. The agent's model is our AMD vLLM endpoint, connected in the
   workspace.
2. `"direct vLLM"`: `AMD_VLLM_ENDPOINT`, as in v2.
3. `"fallback"`: the deterministic template generator. The UI must label it loudly.

Both live paths get knowledge-library passages (v5: the Brand workspace documents — brand book, generated catalogue and profile) in the
prompt, and return the ones they used as citations.

### New / changed types

```ts
interface Citation {
  source: string;               // "<brand> — Brand Book — Fit blocks" (v5: the brand's own documents)
  snippet?: string;
  library: "evolus" | "local";  // evolus = cited by the Evolus library (REST /ask); local = same docs, retrieved by Atelier
  documentId?: string;
  score?: number;
}

interface TechPack { /* v2 … */ citations?: Citation[]; generatedBy?: string }   // generatedBy = route
interface SupplierEmail { /* v1 … */ rfqRef?: string }                          // "ATL-<runId>", also in the subject
interface PipelineStep { /* v2 … */ route?: string }                            // which brain ran this step
interface SupplierRecommendation { /* v2 … */ citations?: Citation[]; generatedBy?: string }
interface CreativeDirection { /* v2 … */ generatedBy?: string; citations?: Citation[] }
interface InferenceCall { /* v2 … */
  route?: string;  // "evolus-agent → AMD vLLM" | "direct vLLM" | "fallback" (brain calls; simulated LLM calls = "fallback")
                   // | "evolus-extractor" | "evolus-ai-tool" | "amd-llm" | "amd-vlm" | "pdf-text-rules"
}
// New InferenceCall.purpose values: "supplier_rationale", "creative_direction", "quote_extraction", "rfq_polish".

interface ExtractedField { name: string; value: string; confidence?: number /* 0..1 */ }

interface QuoteSource {
  channel: "upload" | "email" | "simulated";
  engine: "evolus-extractor" | "amd-llm" | "amd-vlm" | "pdf-text-rules" | "simulated";
  engineLabel: string;          // "Evolus document extractor", …
  documentUrl?: string;         // the stored PDF/image (absolute; private route, see "Access, uploads and quote integrity")
  filename?: string;
  contentType?: string;
  sender?: string;              // email channel
  confidence?: number;          // 0..1: mean per-field confidence if reported, else share of required fields found
  fields: ExtractedField[];
  warnings: string[];           // e.g. "converted from EUR at approx. FX 1.08", "fell back: Evolus extractor: …"
  extractionId?: string;        // X-AskFile-Execution-Id / workflow execution id
}

interface SupplierQuote {       // v2 fields unchanged; `simulated` is now false for real quotes
  /* … */
  simulated: boolean;           // true ONLY with ATELIER_ALLOW_SIMULATION
  quoteNumber?: string;
  validUntil?: string;
  currency?: string;            // as quoted; unitPrice / sampleCost are always USD
  source?: QuoteSource;
}

interface QuoteRound {
  status: "awaiting" | "complete" | "closed";   // closed = the CD stopped waiting
  rfqRef: string;                               // "ATL-<runId>"
  expected: number;
  received: number;
  awaiting: string[];                           // supplier names still to reply
  simulated: boolean;
  openedAt: string;
  closedAt?: string;
  simulateAt?: string;                          // ATELIER_ALLOW_SIMULATION=1 only: when SIMULATED quotes fill in
                                                // if no real document has arrived by then
}

interface PipelineRun { /* v2 … */ quoteRound?: QuoteRound }
```

`GET /api/health` gains two services:

- `evolus_agent`: live when `EVOLUS_AGENT_MODEL` is set; `model` is the agent string.
- `evolus_extractor`: live when the extractor ids are set.

### New endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/runs/{runId}/quotes` | `multipart/form-data`: `file` (PDF/PNG/JPEG/WebP, ≤ 15 MB), optional `supplierName` | `PipelineRun`. The quote is extracted and added; a mill's second document replaces its first. `422` when the document can't be read or has no unit price, `409` before the RFQs went out. |
| POST | `/api/runs/{runId}/quotes/close` | – | `PipelineRun`. Stops waiting and recommends from the quotes in hand. `409` with no quotes, or when no round is waiting. |
| GET | `/api/runs/{runId}/quotes/sample/{supplier}.pdf` | – | `application/pdf`: a **role-play** quote PDF for that mill (tag, key or name), with the run's garment, quantity, cost basis and RFQ ref. The footer says it is a role-play document. It adds nothing to the run; it still has to be uploaded or emailed. |
| POST | `/api/webhooks/evolus/quote` | any JSON: the extractor output (top level, or under `extraction`/`fields`/`data`/`output`, or as a JSON string), plus optional `from`, `subject`, `runId`, `supplierName`, `filename`, `documentUrl`, `confidence` | `{ ok, runId, supplierName, unitPrice, received, expected }`. Auth: header `X-Atelier-Webhook-Secret: <EVOLUS_WEBHOOK_SECRET>`, or `X-Atelier-Signature: sha256=<hex HMAC-SHA256(secret, raw body)>`, compared in constant time. `401` bad or missing, `503` when no secret is configured, `404` when no run is waiting, `422` unreadable. |

### Quote semantics

- **Extraction engines, in order.**
  1. The Evolus document extractor (`POST /api/v1/agents/{agentId}/json/{extractorId}/ask-file?useWebhook=false`).
  2. The AMD LLM over the PDF text (pypdf), or the AMD VLM for images.
  3. The local PDF text parser.

  Nothing is estimated: a quote without a unit price is rejected. A missing MOQ is treated as fitting the run, and
  a missing lead time is scored at the edge of the budget; both are listed in `warnings`.
- **Matching a reply to a run and a mill.**
  - Run: `runId`, or an `ATL-run_xxxxxx` anywhere in the payload, or else the newest run still waiting for that
    mill.
  - Mill: by name, by the `+tag` / role-play inbox in the sender address, or by `supplierName`.
- **The round.** The quotes step opens a `QuoteRound` and logs "Awaiting replies — n of N received". It finishes
  when every RFQ'd mill has replied (`complete`), when the CD closes it, or after `ATELIER_QUOTE_WAIT_SECONDS`
  (default 0 = no timeout). Scoring and the recommendation are unchanged from v2 and run on the real numbers.
- **After a tech pack edit,** real quotes are re-scored but never re-priced. Only simulated quotes are re-priced.
- **RFQ recipients** are role-play inboxes from `SUPPLIER_INBOX` (+tag per mill) or `SUPPLIER_INBOX_<TAG>`, else
  undeliverable `*.test` addresses. They are never taken from model output and never belong to real companies.
- **The outreach workflow** gets one extra flat parameter: `rfq_ref`.

### New env vars (backend/.env, all optional)

`EVOLUS_AGENT_LABEL`, `EVOLUS_AGENT_TRANSPORT`, `EVOLUS_CHAT_BASE`, `EVOLUS_CHAT_PATH`, `EVOLUS_ASK_PATH`,
`EVOLUS_AGENT_TIMEOUT`, `EVOLUS_LIBRARY_ID`, `EVOLUS_LIBRARY_TOP_K`, `EVOLUS_USER_API_KEY`, `EVOLUS_OWN_MODEL_NAME`,
`EVOLUS_EXTRACTOR_AGENT_ID`, `EVOLUS_EXTRACTOR_ID`, `EVOLUS_EXTRACT_PATH`, `EVOLUS_INBOUND_WORKFLOW_ID`,
`EVOLUS_WEBHOOK_SECRET`, `EVOLUS_WEBHOOK_HEADER`, `EVOLUS_RFQ_AI_TOOL`, `SUPPLIER_INBOX`, `SUPPLIER_INBOX_<TAG>`
(okayama, prato, como, porto, shaoxing, santacroce, tiruppur, treviso, guangzhou), `ATELIER_ALLOW_SIMULATION`,
`ATELIER_QUOTE_WAIT_SECONDS`, `ATELIER_QUOTE_MAX_BYTES`, `ATELIER_SIMULATED_QUOTES_AFTER`. `EVOLUS_AGENT_MODEL` (v2) now drives the brain.

| GET | `/api/voice/samples` | – | `{ key, title, description, records, source: VoiceSource }[]`: the bundled public samples |
| POST | `/api/voice/upload` | `multipart/form-data` with `file` (CSV/TSV/TXT or PDF, ≤ 10 MB, ≤ 25,000 records) | `VoiceInsights` |
| POST | `/api/voice/sample` | `{ datasetKey: "outerwear" \| "knits" \| "dresses_pants" }` | `VoiceInsights` |
| GET | `/api/voice/{datasetId}` | – | `VoiceInsights` |
| GET | `/api/voice/{datasetId}/records/{recordId}` | – | the full record `{ id, text, title?, rating?, garmentClass?, product?, size?, fitFeedback?, returnReason?, date?, helpful? }` |
| POST | `/api/voice/{datasetId}/apply` | `{ changeIds: string[]; designId?: string; trendId?: string }` | `{ datasetId, target: { kind: "design" \| "trend", id }, applied: CustomerEvidence[] }` |

- Upload errors: `413` too large, `415` not CSV/TSV/TXT/PDF, `422` no text column / no records / unreadable PDF.
- CSV column detection: exact (normalised) header matches first, then whole-word containment. Text: `review text`,
  `body`, `review`, `comment`, `content`, `feedback`, `message`, `customer note`… Rating: `rating`, `stars`, `score`
  (`4/5` and `★★★★` are read; 10-point scales are converted to 5). Also title, class/category/product type, product,
  size purchased / variant, fit feedback, return reason (`SIZE_TOO_SMALL` reads as "too small"), date, id, helpful
  votes. Columns that look like PII (email, phone, address, reviewer name) are never mapped. With no recognised text
  header, the column with the longest free text is used.
- PDF: pypdf text, split into records at headers like "Review #12" / "Ticket 4411" / "3." (if the document has ≥ 2),
  else at blank lines, else per line. `Rating: 4/5`, `4 stars` and `★★★★` are read.
- Datasets live in memory (the 40 most recent) and reset when the backend restarts.
- `apply` has set semantics per (target, dataset): the body is the full selection from that dataset, so `[]` clears it.
  `422` for unknown change ids, for contradicting changes in one request, or without a target; `404` for an unknown
  dataset, design or trend. `designId` wins if both are given. Changes applied to a trend reach every design from that
  trend. Changes applied to a design also reach its descendants (directed children).
- At approval, the tech pack step folds the applied changes into the design's creative-direction lineage state (the
  same mechanism as `techPackHints`). The live LLM brief gets them as `creativeDirection.techPackHints`. The mock
  generator writes them into the description, `measurements` and BOM, and reprices retail. The step then makes sure
  every change's points of measure (`"<POM> change (customer evidence)"`) and BOM lines are present, sets
  `techPack.customerEvidence`, and logs `Customer evidence: N change(s) from <dataset> added to the brief`. The PDF
  lists them under **Customer evidence** in "02 — Fit", with counts, source and one cited quote per change.

### Sample data

`backend/app/data/voice_samples/*.csv` are unedited, seeded random samples (200 rows each) of the public
**Women's E-Commerce Clothing Reviews** dataset (Nick Brooks / Kaggle *nicapotato*, mirrored on OpenML 43673),
licensed **CC0 1.0**. See `backend/app/data/voice_samples/LICENSE.md`. `backend/scripts/fetch_voice_dataset.py` downloads
the full 23,486 reviews into the git-ignored `backend/.cache/voice/` and rebuilds the samples.

## v4 — Size variants

Additive; nothing existing changes shape.

- **Product.** The real Shopify product gets a `Size` option and one variant per size (`productCreate` with
  `productOptions`, then `productVariantsBulkCreate` with `strategy: REMOVE_STANDALONE_VARIANT`), each at the retail
  price, inventory policy `CONTINUE`, not tracked (sellable at zero stock), published to the Online Store.
  Sizes: `TechPack.sizeRange` → a `measurements` entry whose key mentions "size" (e.g. `"size range": "S – XXL"`) →
  `XS, S, M, L, XL`. If the variants call fails, the product keeps one priced variant and the step log says so.
- `TechPack.sizeRange?: string[]` (also accepted by `PATCH /api/runs/{id}/techpack`, 1–12 sizes).
- `ShopifyProduct.sizes?: string[]` and `ShopifyProduct.variantIds?: Record<size, variantGid>`. Absent when the
  product has no Size option (e.g. an Evolus-made single-variant product — the step log then says
  `⚠ No size data …`, and the forecast uses the base size curve). A price edit updates every size variant.
- `PreorderOrder.lines?: { size?: string; quantity: number; amount: number }[]` — this product's line items. Size comes
  from the variant's `Size` option / `variantTitle` (poll) or a `Size` line-item property / `variant_title` (webhook).
- `DemandOrderEvent` is now **one per line item** (with its `size` and `unitPrice`) plus `orderId?: string`; lines of
  one order share it. An order for an M and an L contributes to both sizes. De-dup is still by order id.
- Forecast: `explanation.data.sizedOrders?: number` (distinct orders with a sized line). Sizes match the base curve
  case-insensitively (`"m"` → `M`). For a run, the base size curve follows the product's sizes
  (`ShopifyProduct.sizes`, else the tech pack's size range): sizes on the default curve keep their weight, others get
  the smallest default weight, renormalised.
- The step log line for an order includes its sizes: `Order #1001 · Giulia, Rome · 2 units (M, L) · …`.

## v4 — Guardrails, hand-off & multilingual sourcing

Additive: every new field is optional on the wire and no v1–v3 endpoint changed shape. **One behaviour change:**
when the agent's pick breaks a brand guardrail, the `supplier_quotes` step stops and waits for a person. The run
stays `status: "running"` (so polling clients keep polling) with `decision.status` `"pending"` or `"negotiating"`;
`shopify_preorder` stays `pending` until the decision is resolved.

### Guardrails (deterministic, no model)

One set per backend (the brand), in memory, starting from env defaults; `PUT /api/guardrails` edits it. Prices are
compared in the brand currency (USD; quotes in another currency were converted on extraction).

| Rule | Check | Default (env) |
|---|---|---|
| `min_margin` | `(retail − unitPrice) / retail ≥ floor` (retail = `techPack.targetRetailPrice`) | 65 % (`GUARDRAIL_MIN_MARGIN_PCT`) |
| `max_unit_cost` | `unitPrice ≤ cap`; cap absolute, or derived per run = costed BOM unit cost × (1 + headroom) | derived, headroom 75 % (`GUARDRAIL_MAX_UNIT_COST=0`, `GUARDRAIL_COST_HEADROOM_PCT`) |
| `max_lead_time` | `leadTimeWeeks ≤ N` | 10 (`GUARDRAIL_MAX_LEAD_TIME_WEEKS`; 0 = off) |
| `max_moq` | `moq ≤ N` | off (`GUARDRAIL_MAX_MOQ`) |
| `certifications` | the mill holds the required certificates (supplier catalogue, case/punctuation-insensitive substring); `all` or `any` | none (`GUARDRAIL_REQUIRED_CERTIFICATIONS`, `GUARDRAIL_CERTIFICATIONS_MODE`) |

Edges: a margin exactly at the floor passes (1e-9 tolerance); a quote above retail has a negative margin; no
retail → the margin check fails ("can't be checked"); a mill not in the catalogue fails a certificate rule.

### The hand-off (decision state machine)

After the recommendation the agent evaluates every quote (`run.guardrailReport`). If the **selected** quote passes,
the step logs `Guardrails ✓` and continues. Otherwise it opens `run.decision` and waits:

```
pending ──approve(note)──────────────────────────────────> resolved (outcome "approved"; override in the audit log)
pending ──switch(mill)───────────────────────────────────> resolved ("switched"; a switch to a breaching mill is
                                                                     also audited as an override)
pending ──negotiate (draft) ──send──> negotiating ──revised quote inside──> resolved ("revised")
                                      negotiating ──revised quote still outside──> pending (ask again)
pending|negotiating ──guardrails edited / retail edited so the pick passes──> resolved ("guardrails_changed" |
                                                                                        "techpack_changed")
```

`POST /api/runs/{id}/supplier` during a hand-off is the "switch" decision; outside one it is recorded in the audit
log (with any guardrail it breaks). A revised quote is any later document from the same mill (upload or email):
it replaces the old one with `revision: n+1` and `revises: <old quote number>`.

**Counter-offer price (shown as `math` lines):** `target = min(retail × (1 − floor), unit-cost cap)`, rounded
**down** to the cent; in the mill's currency `target ÷ FX`, rounded down again, so the mill's answer converted
back can't land above the target. Lead time / MOQ breaches add those asks. Certificates can't be negotiated (409
when they are the only breach). The brain chain (Evolus agent → AMD vLLM → direct vLLM) writes the wording in the
mill's language with an English version; a draft that drops the target price, the quote number or the RFQ ref, or
isn't in the mill's language, is rejected and the deterministic template is used (`template: true`, route
`fallback`). The margin floor itself is never written in the email.

**Sending** goes through `EVOLUS_NEGOTIATION_WORKFLOW_ID` (default: `EVOLUS_OUTREACH_WORKFLOW_ID`) with the
outreach workflow's flat parameters (`garment_name`, `production_quantity`, `rfq_emails` = [the counter-offer as
one email, JSON string], `rfq_ref`) plus `kind: "counter_offer"`, `quote_number`, `target_unit_price`, `currency`.
The recipient is always the mill's role-play inbox (`SUPPLIER_INBOX…`), never model output. Without Evolus the
counter-offer goes to a labelled simulated outbox (`sentVia`), status `queued`. The inbound-quote webhook matches an
email reply to the run that is negotiating with that mill (by RFQ ref, or by mill when there is no ref).

### Multilingual sourcing

Each mill has a correspondence language (`data/suppliers.py`): Italian — Prato, Como, Santa Croce, Treviso;
European Portuguese — Porto; English — Okayama, Shaoxing, Guangzhou, Tiruppur (export desks; no machine-guessed
Japanese/Chinese templates). RFQs and counter-offers are written in it (brain, or per-language templates labelled
fallback), the English version alongside. Role-play quote PDFs are written in it by default. Quote notes in
another language are translated by the brain (`noteTranslation` = route); fallback: the role-play phrasebook
(`"phrasebook"`), else `"untranslated"` with no `noteEnglish`. The PDF parser and the fake extractor read English,
Italian and Portuguese labels (`Prezzo unitario`, `Minimo d'ordine`, `Tempi di consegna`, `Preço unitário`,
`Prazo de entrega`, …; `1.000` = 1000 pieces; `settimane` / `semanas` / `giorni` / `dias`).

### New / changed types

```ts
interface SupplierEmail { /* v3 … */
  language?: string;            // ISO 639-1: "it" | "pt" | "en"
  languageName?: string;        // "Italian"
  subjectEnglish?: string;      // only when language != "en"
  bodyEnglish?: string;
  kind?: "rfq" | "counter_offer";
}

interface SupplierQuote { /* v3 … */
  language?: string;            // of the document / note
  noteEnglish?: string;
  noteTranslation?: string;     // brain route | "phrasebook" | "untranslated"
  unitPriceQuoted?: number;     // in `currency`, as printed
  revision?: number;            // 0 = first quote; n = n-th revision
  revises?: string;             // the quote number it replaces
}

interface Guardrails {
  minGrossMarginPct: number; maxUnitCost?: number /* absent = derived */; costHeadroomPct: number;
  maxLeadTimeWeeks?: number; maxMoq?: number /* absent = no limit */;
  requiredCertifications: string[]; certificationsMode: "all" | "any"; currency: string;
  updatedAt?: string; updatedBy?: string;
}

type GuardrailRule = "min_margin" | "max_unit_cost" | "max_lead_time" | "max_moq" | "certifications";
interface GuardrailCheck { rule: GuardrailRule; label: string; ok: boolean; actual: string; limit: string;
                           actualValue?: number; limitValue?: number; message: string /* plain language */ }
interface QuoteEvaluation { supplierName: string; ok: boolean; unitPrice: number; marginPct?: number;
                            checks: GuardrailCheck[]; quoteNumber?: string; revision: number }
interface GuardrailReport { guardrails: Guardrails /* derived cap filled in */; maxUnitCostDerived: boolean;
                            costedUnitCost?: number; retailPrice?: number; evaluations: QuoteEvaluation[];
                            selectedSupplierName?: string; selectedOk?: boolean; evaluatedAt: string }

interface DecisionOption { kind: "approve" | "negotiate" | "switch"; label: string; detail: string; supplierName?: string }

interface CounterOffer {
  supplierName: string; region: string; toEmail: string; language: string; languageName: string;
  subject: string; body: string; subjectEnglish: string; bodyEnglish: string;
  rfqRef: string; quoteNumber?: string; currency: string;
  quotedUnitPrice: number; quotedUnitPriceLocal?: number;    // USD / mill currency
  targetUnitPrice: number; targetUnitPriceLocal?: number;    // USD / mill currency
  reductionPct: number; math: string[];
  generatedBy: string; template: boolean; edited: boolean;
  status: "draft" | "queued" | "sent"; sentAt?: string; sentVia?: string; executionId?: string; createdAt: string;
}

interface AuditEntry {
  at: string; actor: "agent" | "human" | "system";
  action: string;   // guardrail_breach | handoff | guardrails_passed | approved_override | switched |
                    // counter_offer_drafted | counter_offer_sent | quote_received | revised_quote | resolved |
                    // guardrails_updated | supplier_override
  summary: string; supplierName?: string; guardrail?: string /* rule ids, comma-separated */;
  values: Record<string, string>; note?: string;
}

interface Decision {
  id: string; status: "pending" | "negotiating" | "resolved";
  supplierName: string; headline: string; explanation: string /* the numbers and the options */;
  breaches: GuardrailCheck[]; allQuotesBreach: boolean; options: DecisionOption[];
  counterOffer?: CounterOffer; negotiationRounds: number;
  outcome?: "approved" | "switched" | "revised" | "guardrails_changed" | "techpack_changed";
  resolvedSupplierName?: string; resolvedBy?: string; resolvedAt?: string; note?: string; createdAt: string;
}

interface PipelineRun { /* v3 … */ guardrailReport?: GuardrailReport; decision?: Decision; audit: AuditEntry[] }
// New InferenceCall.purpose values: "counter_offer", "note_translation".
```

### New endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/guardrails` | – | `Guardrails` |
| PUT | `/api/guardrails` | any subset of `Guardrails` fields; `null` clears `maxUnitCost` (→ derived), `maxLeadTimeWeeks`, `maxMoq` | `Guardrails`. Open hand-offs are re-evaluated (a pick that now passes continues) and the change is audited. `422` for an empty body or out-of-range values. |
| POST | `/api/guardrails/reset` | – | `Guardrails` (env defaults) |
| POST | `/api/runs/{runId}/decision/approve` | `{ note?: string, actor?: string }` | `PipelineRun`; `409` when no decision is open |
| POST | `/api/runs/{runId}/decision/switch` | `{ supplierName: string, note?: string, actor?: string }` | `PipelineRun`; `404` unknown quote, `409` no decision |
| POST | `/api/runs/{runId}/decision/negotiate` | – | `PipelineRun` with `decision.counterOffer` (draft); `409` no decision or nothing negotiable |
| POST | `/api/runs/{runId}/decision/counter-offer/send` | `{ subject?: string, body?: string, actor?: string }` (edits) | `PipelineRun`, `decision.status = "negotiating"`; `409` without a draft, or when the Evolus workflow failed (the draft is kept) |

`GET /api/runs/{runId}/quotes/sample/{supplier}.pdf` gains `?lang=native|en|it|pt` (default `native`, the mill's
language) and `?scenario=handoff|revised` (role-play scripts for rehearsal and demo mode):

- `handoff`: the round's lead mill (first Italian fabric mill, else first Italian, else first non-English) quotes
  3 points under the margin floor, saying raw-material prices rose. The others keep their price but ask for a
  2× MOQ, so the compliant alternatives have a trade-off.
- `revised`: that mill's revised quote at the counter-offer's target (or the guardrail target), numbered
  `<old>-R<n>`, with "replaces <old>".

`422` for an unknown `lang` / `scenario`.

### New env vars (backend/.env, all optional)

`GUARDRAIL_MIN_MARGIN_PCT`, `GUARDRAIL_MAX_UNIT_COST`, `GUARDRAIL_COST_HEADROOM_PCT`, `GUARDRAIL_MAX_LEAD_TIME_WEEKS`,
`GUARDRAIL_MAX_MOQ`, `GUARDRAIL_REQUIRED_CERTIFICATIONS`, `GUARDRAIL_CERTIFICATIONS_MODE`,
`EVOLUS_NEGOTIATION_WORKFLOW_ID`, `ATELIER_TRANSLATE_NOTES`.

## v5 — Real mood boards

No invented data. The preset mood boards are real, openly licensed photographs, and analysing one sends those
photos to the live vision model every time, by the same path as an upload. There are no curated trend templates,
no generated SVG thumbnails and no artificial delay.

### The boards

`backend/static/moodboards/<boardId>/NN.jpg` (downscaled to a 1200 px long edge), described by
`backend/static/moodboards/manifest.json` and credited in `backend/static/moodboards/ATTRIBUTION.md`. A board is
only images, a factual title and per-image attribution. Rebuild with `backend/scripts/build_moodboards.py` (it
checks each file's licence at the source).

| Board id | Title | Images | Source · licence |
|---|---|---|---|
| `michael-kors-fw2010` | Michael Kors — Fall/Winter 2010 runway, New York | 4 | Wikimedia Commons, Masaki-H · CC BY 2.0 |
| `max-azria-fw2010` | Max Azria — Fall/Winter 2010 runway, New York | 4 | Wikimedia Commons, Masaki-H · CC BY 2.0 |
| `lacoste-fw2010` | Lacoste — Fall/Winter 2010 runway, New York | 3 | Wikimedia Commons, Masaki-H · CC BY 2.0 |
| `jill-stuart-fw2010` | Jill Stuart — Fall/Winter 2010 runway, New York | 3 | Wikimedia Commons, Masaki-H · CC BY 2.0 |
| `met-19c-outerwear` | 19th-century coats & jackets — The Met Costume Institute | 4 | The Met Open Access · CC0 1.0 |

### New / changed types (additive)

```ts
interface SourceImage {
  url: string;            // absolute, served from /static/moodboards/…
  title: string;
  creator: string;        // photographer / institution, as the licence requires
  sourceUrl: string;      // the file page (Commons) or object page (The Met)
  license: string;        // e.g. "CC BY 2.0", "CC0 1.0 (Met Open Access)"
  licenseUrl: string;
  modifications?: string; // e.g. "Downscaled from 2832×4256 to 798×1200 px and re-encoded as JPEG …"
}

interface AnalyzedBy {    // from the vision call's telemetry record; absent fields were not reported
  model?: string;         // e.g. "google/gemma-4-26B-A4B-it"
  endpointHost?: string;  // e.g. "localhost:18000"
  gpu?: string;           // AMD_GPU_LABEL, never guessed
  latencyMs?: number;
  callId?: string;        // InferenceCall.id in /api/telemetry
  imagesAnalyzed?: number;  // v6: images the model read (<= ATELIER_VISION_MAX_IMAGES, default 4)
  imagesSubmitted?: number; // v6: images submitted (uploads allow up to 6)
}

interface TrendPreset {   // GET /api/trends/presets: a mood board
  id: string;
  name: string;           // the board's factual title
  thumbnailUrl: string;   // its first image (was a generated SVG)
  credit?: string;        // v5, e.g. "Photos: Masaki-H · CC BY 2.0 · via Wikimedia Commons"
  images?: SourceImage[]; // v5, 3-4 per board
}

interface TrendAnalysis {
  // …v1 fields…
  analyzedBy?: AnalyzedBy;       // v5: set on every analysis (preset, upload or URLs)
  sourceImages?: SourceImage[];  // v5: preset boards only; the attributed images that were analysed
}
```

Optional fields are omitted from the JSON when absent (not `null`).

### Behaviour

- `POST /api/trends/analyze {preset}` accepts a board id or its exact title. It reads the board's files and sends
  them as image bytes to the vision model (up to 4 per prompt, as for uploads). `sourceImageUrls` holds the boards'
  static URLs. Every call is a new model call.
- Unknown board: `404 "unknown mood board '<x>'"`.
- No vision model configured (`AMD_VISION_ENDPOINT` empty): **`503`**
  `{"detail": "Vision model not connected — see docs/AMD_SETUP.md", "service": "vision", "status":
  "not_configured", "hint": "…"}` for presets, uploads and URLs alike (the "Errors" shape of "v5 — No mock mode"
  below). The dashboard shows this as "Vision model not connected" with the hint and Retry.
- The vision call fails or returns unusable output (after one retry): **`503`** `"Vision model call failed at
  <host>: …"` with `service: "vision"`, `status: "unreachable"`. Nothing is substituted.
- `/static/presets/*.svg` no longer exists.

## v5 — Brand workspace

Atelier runs on a **real brand's data**. Everything brand-specific — profile, brand book, supplier directory,
material price list, guardrails, sales history — is provided by the merchant through the Brand workspace (UI:
`/workspace`, linked from the header), validated, stored with its provenance, and read by the rest of the backend.
Nothing brand-specific is bundled any more: the fictional house, its brand book / supplier catalogue
(`docs/knowledge/`), the nine fictional mills and their quote profiles, the curated material list and the
guardrail / promise defaults are gone.

**Storage.** One workspace per backend (one brand), SQLite (stdlib `sqlite3`) at `$ATELIER_DATA_DIR/atelier.sqlite3`
plus uploaded files in `$ATELIER_DATA_DIR/files/`. `ATELIER_DATA_DIR` defaults to `backend/var/` (git-ignored); in
Docker it is `/data` on the `atelier-data` volume (`docker-compose.yml`).

**Supersedes in v3/v4:** the env vars `SUPPLIER_INBOX`, `SUPPLIER_INBOX_<TAG>` and `GUARDRAIL_*` are removed
(contacts, RFQ overrides and guardrails live in the workspace). Guardrails have **no defaults**: every rule starts
unset, an unset rule is not checked, and `POST /api/guardrails/reset` now clears every rule.

### Readiness (approve gate)

`POST /api/designs/{designId}/approve` → `409 {detail}` until the workspace is ready:

1. a brand profile (name + currency);
2. at least one supplier, **and** the brand confirmed the contacts (`POST /api/workspace/suppliers/confirm`) — any
   import, or a change to a supplier's name / emails / RFQ override, asks for a new confirmation;
3. the guardrails reviewed (any `PUT /api/guardrails`, or `POST /api/guardrails/review` to keep rules unset).

The `detail` names what is missing, e.g. "The brand workspace isn't set up yet. Add at least one supplier; a review
of the guardrails in Brand workspace before approving a design."

### Endpoints

| Method & path | Body | Returns |
|---|---|---|
| `GET /api/workspace` | — | `Workspace` (everything + `status`) |
| `GET /api/workspace/status` | — | `WorkspaceStatus` |
| `DELETE /api/workspace?confirm=DELETE` | — | `Workspace` (erased; `422` without the confirm) |
| `PUT /api/workspace/profile` | `BrandProfileInput` | `BrandProfile` (`422` on invalid currency / hex …) |
| `POST /api/workspace/{suppliers\|prices\|sizes\|sales}/import` | multipart `file` (CSV/TSV/XLSX), `commit` (bool, default false), `mode` (`replace`\|`append`) | `ImportPreview`; nothing is stored unless `commit=true` **and** no row has an error |
| `GET /api/workspace/templates/{suppliers\|prices\|sizes\|sales}.csv` | — | CSV, header row only (no example rows) |
| `GET /api/workspace/suppliers` | — | `Supplier[]` |
| `POST /api/workspace/suppliers` | `SupplierInput` | `201 Supplier` |
| `PUT /api/workspace/suppliers/{id}` | `SupplierInput` | `Supplier` (`404`) |
| `DELETE /api/workspace/suppliers/{id}` | — | `204` |
| `POST /api/workspace/suppliers/confirm` | `{confirm: true, actor?}` | `SupplierConfirmation` (`409` with no suppliers) |
| `POST /api/workspace/suppliers/{id}/certificates` | multipart `file` (PDF/image), `certification` | `Supplier` (document attached; certification added if missing) |
| `GET /api/workspace/prices` · `DELETE /api/workspace/prices` | — | `PriceList` |
| `GET /api/workspace/sales` · `DELETE /api/workspace/sales` | — | `{rows, styles, provenance?}` |
| `GET /api/workspace/scoring` · `PUT /api/workspace/scoring` · `POST /api/workspace/scoring/reset` | `{price, moq, leadTime}` (any scale, normalised) | `ScoringWeights` |
| `POST /api/workspace/documents` | multipart `file` (PDF / DOCX / MD) | `201 BrandDocument` (text extracted; sent to the Evolus library when configured) |
| `GET /api/workspace/documents` | — | `BrandDocument[]` |
| `GET /api/workspace/documents/{id}/file` | — | the stored file |
| `DELETE /api/workspace/documents/{id}` | — | `204` (local copy + passages; an Evolus copy is removed in the library UI) |
| `POST /api/guardrails/review` | — | `Guardrails` (marked reviewed as they are) |

`GET/PUT /api/guardrails` keep their shape; `PUT` accepts `null` for any rule (= not set) and marks the guardrails
reviewed. `GET /api/runs/{id}/techpack/alternatives` adds `priceListDated?` and `priceListSource?`.

### Models (camelCase on the wire)

```ts
interface Provenance { source: "csv" | "xlsx" | "form" | "upload"; filename?: string; importedAt: string;
                       rows?: number; label: string }   // "Imported from suppliers.csv on 13 Oct 2026 (12 rows)"
interface ColourStandard { name: string; hex: string /* #RRGGBB */; code?: string /* Pantone/TCX, only if given */ }
interface BrandProfileInput {
  name: string; currency: string /* ISO 4217 */; targetMarkets: string[]; voice: string;  // voice -> prompts
  defaultSizeRange: string[]; colours: ColourStandard[];
  priceArchitecture?: { mode: "retail_multiple" | "target_margin"; value: number } | null;
  deliveryPromiseWeeks?: number | null; preorderWindowDays?: number | null;
}
interface BrandProfile extends BrandProfileInput { provenance?: Provenance; updatedAt?: string }
interface SizePoint { block: string; pointOfMeasure: string; size: string; value: number; unit: string; tolerance?: number }
interface SupplierCertification { name: string; expiresOn?: string /* YYYY-MM-DD */; documentId?: string;
                                  expired: boolean /* computed */ }
interface SupplierInput {
  name: string; city: string; country: string; language: string /* ISO 639-1 */; emails: string[] /* ≥ 1 */;
  categories: string[] /* "CMT" | "cut-make-trim" | "full package" = maker */; capabilities: string[];
  certifications: SupplierCertification[]; moq?: number; leadTimeWeeks?: number; paymentTerms: string; notes: string;
  rfqEmailOverride?: string;  // RFQs + counter-offers go here instead of the supplier (e.g. the brand's pilot inbox)
}
interface Supplier extends SupplierInput { id: string; provenance?: Provenance; createdAt?: string; updatedAt?: string;
                                           rfqRecipient: string; maker: boolean }
interface MaterialPrice { material: string; category: string; unit: string; price: number; currency: string;
                          supplier: string; validFrom: string }
interface PriceList { items: MaterialPrice[]; provenance?: Provenance; dated?: string /* latest validFrom */ }
interface ScoringWeights { price: number; moq: number; leadTime: number; isDefault: boolean;
                           label: string /* "default weighting" | "set by the brand" */; updatedAt?: string }
interface BrandDocument { id: string; kind: "brand_book" | "certificate"; filename: string; contentType: string;
  size: number; uploadedAt: string; chars: number; passages: number; supplierId?: string; certification?: string;
  evolus?: { status: "uploaded" | "not_configured" | "failed"; documentId?: string; libraryId?: string; detail?: string };
  url: string }
interface SectionStatus { key: "profile" | "brand_book" | "suppliers" | "prices" | "guardrails" | "sales";
  label: string; required: boolean; done: boolean; detail: string; provenance?: Provenance }
interface WorkspaceStatus { ready: boolean; missing: string[]; sections: SectionStatus[] }
interface Workspace { profile?: BrandProfile; sizePoints: SizePoint[]; sizeProvenance?: Provenance;
  suppliers: Supplier[]; supplierConfirmation: { confirmedAt?: string; confirmedBy?: string; suppliers: number };
  priceList: PriceList; guardrails: Guardrails; scoring: ScoringWeights; documents: BrandDocument[];
  sales: { rows: number; styles: number; provenance?: Provenance }; status: WorkspaceStatus }
interface ImportIssue { row: number /* 1-based data row; 0 = file */; field?: string; message: string;
                        level: "error" | "warning" }
interface ImportPreview { kind: "suppliers" | "prices" | "sizes" | "sales"; filename: string; columns: string[];
  ignoredColumns: string[]; rows: Record<string, unknown>[] /* template columns, camelCase; _row, _error */;
  validRows: number; issues: ImportIssue[]; committed: boolean; mode: "replace" | "append"; provenance?: Provenance }
// Guardrails (v4) changes: minGrossMarginPct?, costHeadroomPct? are optional (unset = not checked);
// + reviewedAt?: string; unset: ("min_margin" | "max_unit_cost" | "max_lead_time" | "max_moq" | "certifications")[]
```

### CSV / XLSX columns (headers matched case/punctuation-insensitively, with aliases; * = required)

- **suppliers**: `name`*, `city`, `country`, `language` (ISO code or English name), `contact_emails`* (`;`-separated),
  `categories`, `capabilities`, `certifications` (`;`), `certificate_expiry` (`CERT=YYYY-MM-DD; …`), `moq`,
  `lead_time_weeks`, `payment_terms`, `notes`, `rfq_email_override`.
- **prices**: `material`*, `category`*, `unit`*, `price`* (> 0), `currency`* (ISO), `supplier` (warning if not in
  the directory), `valid_from`* (`YYYY-MM-DD` or a spreadsheet date).
- **sizes**: `block`*, `point_of_measure`*, `size`*, `value`*, `unit`*, `tolerance`.
- **sales**: `style`*, `launch_date`*, `week`* (≥ 1, week since launch), `units`* (≥ 0), `size`.

Row errors (bad email, non-numeric MOQ, unknown language, duplicate supplier, missing required value …) block the
commit; warnings (unknown supplier on a price, expired certificate …) don't.

### What reads the workspace (stable interfaces)

- `data/suppliers.py`: `ALL_SUPPLIERS` (live sequence), `shortlist(fabrics, max_mills=2)` (categories/capabilities
  matched against the fabrics + one maker, preferring the mills' country), `find_supplier(name, email)`,
  `inbox_for(supplier)` (RFQ override, else first contact), `language_of`, `specialty_in` — same dict shape as
  before (the directory's MOQ / lead time / payment terms are on each supplier dict; there are no quote profiles).
- `data/materials.py`: `alternatives(bom)`, `alternatives_for(index, line)`, `family_for(material)` from the price list.
- `services/guardrails.py`: `current()` / `replace()` / `defaults()` (empty) — persisted; unset rules skipped;
  expired certificates don't count.
- `services/sourcing.py`: `WEIGHTS`, `DELIVERY_PROMISE_WEEKS`, `PREORDER_WINDOW_WEEKS`, `LEAD_BUDGET_WEEKS` stay
  readable as module attributes but are live workspace values (`weights()`, `delivery_promise_weeks()`,
  `lead_budget_weeks()`; budget = promise − window, else the max-lead-time guardrail, else lead time is scored
  relative to the fastest quote).
- Prompts (`llm.py`, `sourcing.py`, `direction.py`, `decisions.py`) use `workspace.persona(role)` /
  `workspace.brand_prompt(role)`: the brand's name, voice notes and facts (currency, markets, sizes, colours, price
  architecture, size blocks). Without a profile no brand is named.
- `services/knowledge.py`: grounding passages from the uploaded brand book(s) + a supplier catalogue and brand
  profile generated from the workspace (no contact addresses in the catalogue).
- `services/workspace.py`: `launch_curves(max_weeks=26)` → `{style: [units week 1, 2, …]}` and `size_mix()` →
  `{size: share}` from the sales history, for fitting forecast priors (not yet called by `forecast.py`).

### New env vars

`ATELIER_DATA_DIR` (default `backend/var/`; Docker `/data`). The same directory also holds the per-brand PO / style
number sequences (`sequences.json`, see "v5 — No mock mode"). Removed: `GUARDRAIL_*` defaults and the
`SUPPLIER_INBOX` / `SUPPLIER_INBOX_<TAG>` role-play inboxes (supplier contacts and RFQ overrides live in the
workspace).

## v5 — No mock mode

The owner's rule: **no mocked, simulated or invented data anywhere in the shipped app.** Every model, workflow and
store call goes to the real service that is configured. If a service is not configured or fails, the client gets an
honest error with a setup hint and a retry — never a fallback that produces made-up output. This section supersedes
every "mock" / "simulated" / "fallback" statement in the sections above (the "Modes" section at the top included).

### Removed

- Env vars: `ATELIER_MODE`, `ATELIER_ALLOW_SIMULATION`, `ATELIER_SIMULATED_QUOTES_AFTER`, `ATELIER_DELAY_SCALE`,
  `ATELIER_DEMAND_SECONDS`. There are no artificial delays.
- Fields: `mode` (on `ServiceStatus`, `HealthResponse`, `PipelineStep`, `CreativeDirection`, `Collection`,
  `SupplierRecommendation`, `InferenceCall`, `ServiceTelemetry`, `TelemetryResponse`, voice `VoiceInsights`);
  `simulated` (on `InferenceCall`, `ShopifyProduct`, `SupplierQuote`, `QuoteRound`, `PurchaseOrder`,
  `PreorderDemand`, forecast `ForecastRequest` / `Forecast` / `DataUsed`); `fallback` / `fallbacks` (telemetry);
  `QuoteRound.simulateAt`; `PreorderDemand.visitors`, `.conversionRate`, `.speed`; `CounterOffer.template`;
  `PurchaseOrder.issuedAt` and status `"issued"`; `CustomerEvidence.measurements` / `.bomAdditions` and voice
  `RecommendedChange.measurements` / `.bomAdditions` (rule-of-thumb amounts and invented BOM costs).
  Enum values: route `"fallback"`, quote channel / engine `"simulated"`, order `via: "simulated"`, demand
  `source: "simulated"`, Shopify product `source: "simulated"`.
- Endpoints: `POST /api/runs/{runId}/demand/speed`, `GET /api/runs/{runId}/quotes/sample/{supplier}.pdf`
  (role-play quote PDFs, `scripts/make_sample_quote_pdfs.py` and `docs/sample-quotes/` are gone).
- Behaviour: curated-template trend analysis, SVG concept renders, the template tech pack, the keyword creative
  direction interpreter and its fixed cm / cost effects, the template collection planner, template RFQs and
  counter-offers, the note phrasebook, the template supplier rationale, simulated telemetry, simulated listings,
  demand curves and quotes, the hard-coded FX table, assumed MOQ / lead time, random PO numbers, seed-based style
  numbers, and in the tech pack PDF the "simulated" footer, invented tolerances / grading, hand-written construction
  notes, TCX matches, a fixed size ratio and season labels.

### Connection states

```ts
type ConnectionStatus = "connected" | "unreachable" | "not_configured";

type ServiceStatus = {
  name: string;          // vision | diffusion | llm | evolus_agent | evolus_extractor | evolus_outreach |
                         // evolus_po (NEW) | evolus_shopify | shopify
  status: ConnectionStatus;
  healthy: boolean;      // == status === "connected"
  detail?: string;       // starts with "FAKE UPSTREAM — not real · " when fake
  hint?: string;         // how to set it up / fix it
  fake: boolean;         // the endpoint is the local test double (tests/fake_upstreams.py)
  model?: string; host?: string; latencyMs?: number;
  gpu?: string;          // AMD_GPU_LABEL, or the device the diffusion server reports (never guessed)
};

interface HealthResponse {
  status: "ok";
  services: ServiceStatus[];
  poweredBy: { amd: boolean; evolus: boolean };  // credits may be shown only for real, connected services
  fakeUpstreams: boolean;
}
```

The test doubles set `X-Atelier-Fake-Upstream: 1` on every response; any endpoint that answers with it is reported
`fake: true` and never counts towards `poweredBy`. Telemetry calls to it carry `InferenceCall.fake = true`.

### Errors

A request whose service is missing or fails returns **503**:

```json
{ "detail": "Diffusion model not connected — no concepts can be rendered", "service": "diffusion",
  "status": "not_configured", "hint": "Set AMD_DIFFUSION_ENDPOINT to the diffusion server … docs/AMD_SETUP.md." }
```

`service` is one of `vision`, `diffusion`, `brain`, `llm`, `evolus_outreach`, `evolus_negotiation`, `evolus_po`,
`shopify`. Affected endpoints: `POST /api/trends/analyze`, `/api/designs/generate`, `/api/designs/{id}/refine`,
`/api/designs/{id}/direct`, `/api/collections/generate`, `/api/runs/{id}/decision/negotiate`,
`/api/runs/{id}/decision/counter-offer/send`, `/api/runs/{id}/purchase-order/send`. Brain output is validated
against a schema with one retry before it becomes an error. Concept generation renders all `count` images or
fails as a whole.

Pipeline steps fail the same way: `PipelineStep` gains `service?`, `hint?` and `retryable: boolean`; the run stops
at the failed step (`run.status = "failed"`, later steps stay `pending`).

| Method | Path | Returns |
|---|---|---|
| POST | `/api/runs/{runId}/retry` | `PipelineRun`; resumes from the first errored step (e.g. after connecting the missing service). Drafted RFQs are re-used when only sending failed. `409` unless the run failed. |

### Brain-written content

`TechPack.constructionNotes?: string[]` (the brain's own notes; the PDF omits the section without them);
`TechPack.generatedBy`, `CreativeDirection.generatedBy`, `Collection.generatedBy` (NEW), `CounterOffer.generatedBy`
are routes (`"evolus-agent → AMD vLLM" | "direct vLLM"`). `CreativeDirection.fabricsAfter?` (NEW). The collection
planner uses the brain chain (the Evolus agent alone is enough). `SupplierRecommendation.rationale` is optional and
`rationaleError?` (NEW) says why there is none; the deterministic pick and scores are always present.

Customer voice: the deterministic counts, shares and exact quotes stay. `RecommendedChange` keeps the qualitative
`action` (no amounts) and gains `pointsOfMeasure: string[]`, `instruction?` and `instructionBy?` — the concrete
instruction drafted by the brain from the evidence. `VoiceInsights` gains `phrasedBy?` / `phrasingError?`.
`CustomerEvidence` gains `instruction?` / `instructionBy?`.

### Quotes and FX

`SupplierQuote`: `unitPrice: number | null` (brand currency), `moq`, `leadTimeWeeks`, `sampleCost`, `paymentTerms`
are omitted when the document does not state them ("not stated" in the UI; never assumed). NEW `fxRate?`
(brand-currency units per 1 unit of `currency`), `fxSource?` (`"ECB euro foreign exchange reference rates"`),
`fxDate?`, `sampleCostQuoted?`. Rates come from https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
(`ATELIER_FX_URL`), cached for `ATELIER_FX_CACHE_HOURS` (24); cross rates go through the euro. When no rate is
available the quote keeps its own currency, `unitPrice` is null and a warning says it was not converted.
`ScoreBreakdown` fields are nullable: a quote is scored over the criteria it states (weights renormalised); the pick
prefers quotes with a comparable price. Guardrail checks on an unstated lead time / MOQ or an unconverted price fail
with `actual: "not stated"` / `"can't be checked"`, so a person decides.

### Demand and purchase orders

`PreorderDemand` counts real Shopify orders only; NEW `testUnits`; test orders stay counted and are always labelled.
When the window closes below the threshold no PO is drafted and the orders stay open in Shopify (Atelier issues no
refunds).

```ts
interface PurchaseOrder {
  poNumber: string;            // "PO-00001": the brand's persisted sequence (ATELIER_DATA_DIR/sequences.json)
  supplierName: string; region: string;
  toEmail?: string;            // the mill's address from the supplier directory
  quantity: number;
  currency: string;            // as quoted
  unitPrice: number; total: number;            // in `currency`, as quoted
  unitPriceBrand?: number; totalBrand?: number; // brand-currency equivalents when an FX rate exists
  leadTimeWeeks?: number;      // only when the quote stated one
  quoteNumber?: string; rfqRef?: string;
  status: "draft" | "sending" | "queued" | "sent" | "failed";   // never "issued"
  createdAt: string; sentAt?: string; sentVia?: string; executionId?: string;
  sendError?: string; hint?: string;
}
```

The PO is sent through the Evolus workflow `EVOLUS_PO_WORKFLOW_ID` (else the outreach workflow) with the outreach
parameters (one email in `rfq_emails`) plus `kind=purchase_order`, `po_number`, `supplier_name`, `to_email`,
`quantity`, `unit_price`, `currency`, `total`, `rfq_ref`, `quote_number`. Without Evolus it stays `draft` with
`sendError` + `hint`.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/runs/{runId}/purchase-order/send` | `PipelineRun`; sends (or re-sends after a failure) the drafted PO. `503` (`service: "evolus_po"`) without Evolus, `409` before a PO is drafted or once it was sent. |

`PipelineRun.styleNumber?` (NEW): `"ST-00001"`, from the brand's persisted style sequence, assigned with the tech
pack and printed on the PDF.

### Telemetry and forecast

`GET /api/telemetry` holds measured calls only and is empty until a real call happens. Forecast: with no orders the
confidence note reads "No orders yet."; every assumption stays labelled and is editable via `POST /api/forecast`
(`inputs.assumptions`), with a note that they should be fitted to the brand's own past launches.

### New env vars (backend/.env, all optional)

`EVOLUS_PO_WORKFLOW_ID`, `ATELIER_FX_URL`, `ATELIER_FX_TIMEOUT`, `ATELIER_FX_CACHE_HOURS`, `ATELIER_BRAND_ID`
(default `default`: whose sequence in `sequences.json`). The sequences live in `ATELIER_DATA_DIR`, next to the
Brand workspace (one data dir / volume for both).

## v6 — Gemma 4 on AMD

The default model plan is **one** open model, `google/gemma-4-26B-A4B-it` (Gemma 4, Google, Apache-2.0), served by our
own vLLM (ROCm, ≥ 0.19.1) on an AMD Instinct MI300X: it is the direct-vLLM brain, the vision model and the Evolus
workspace model (`own/<name>`). Setup: `docs/AMD_SETUP.md`; Evolus: `docs/EVOLUS_SETUP.md`. No API shape changes
except two optional fields.

- **Same endpoint for text and vision.** `AMD_VISION_ENDPOINT` / `AMD_VISION_MODEL` default (in docs and
  `.env.example`) to the `AMD_VLLM_*` values. A separate vision server stays possible (`deploy/serve_vlm.sh` with
  `VLM_MODEL`). Diffusion is unchanged (FLUX).
- **Thinking off for JSON.** `ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}` (the key
  Gemma 4's chat template reads). JSON parsing tolerates leaked reasoning / tool markup (`<|channel>thought…<channel|>`,
  `<think>…</think>`, stray `<|…|>` tags) before or after the JSON.
- **Vision requests.** OpenAI `image_url` parts (base64 `data:` URLs for uploads and boards), images before the text,
  at most `ATELIER_VISION_MAX_IMAGES` (new, default 4 = the server's `--limit-mm-per-prompt`) per prompt, on the
  retry too. Uploads still accept 1–6 images; the first 4 are analysed.
- `AnalyzedBy.imagesAnalyzed?: number`, `AnalyzedBy.imagesSubmitted?: number` (NEW, optional): the UI shows "read the
  first 4 of 6 images" when they differ.
- **Honest labels.** The landing's "Under the hood" shows the served model id from `/api/health` and, only when that id
  contains `gemma-4` and the endpoint is not a fake, the family label "Gemma 4 (Google, open)" — with "on AMD
  Instinct" only when the reported GPU label says Instinct. Another served model is shown by its own id.
- `scripts/check_amd.py`: model id check (`WARN` unless `gemma-4`), JSON with thinking off, a tool-call round trip
  (`--tool-call-parser gemma4`), one-image vision; prints model, latency and tokens/s.
- Test double: `tests/fake_upstreams.py`'s vLLM reports `fake/gemma-4-26B-A4B-it` and supports tool calls.

## v5 — Brand currency, supplier-safe emails, forecast evidence (additive)

**Brand currency end to end.** Every price the brand owns is in the brand currency (`BrandProfile.currency`); nothing
assumes USD. `TechPack.currency?` records it when the tech pack is written (the prompt asks for prices in it).
RFQs ask for quotes in it; a mill may still answer in its own currency and the quote is converted to the brand
currency with the ECB rates (as before). Guardrail messages, the counter-offer maths, the forecast and the tech pack
PDF format money in the brand currency. Additive fields: `CounterOffer.brandCurrency?`,
`PurchaseOrder.brandCurrency?` (the currency of `unitPriceBrand` / `totalBrand`), `Forecast.currency?`,
`ForecastRequest.economics.currency?` (ISO; without it numbers carry no symbol).

**Shopify store currency.** The store has its own currency (read from the shop query). `ShopifyProduct.price` is the
listing price in `ShopifyProduct.currency?` (the store's; absent = not verified, e.g. Evolus-only without Admin API);
`priceBrand?` / `brandCurrency?` are the tech pack retail. When the two currencies differ the listing price is the
retail converted at the ECB rate (`fxRate?` = store units per 1 brand unit, `fxDate?`), and both are shown. If a
conversion is needed and no rate is available the Shopify step fails (503-style step error, retryable) — nothing is
listed in the wrong currency. A retail edit re-converts.

**What reaches a mill.** RFQ prompts and the outreach workflow's `tech_pack` parameter carry a supplier-safe view
(specification, BOM materials and consumption, measurements, construction notes, colourway, sizes, quantity, required
lead time) — never target costs, the retail price or the margin. `image_url` / the design link are only sent when
the render URL is public https (not localhost / private / plain http); otherwise the email offers the render on
request. The PO email says the specification is the one sent with the RFQ (nothing is attached).

**Forecast evidence threshold.** `ForecastAssumptions` gains `minExposure` (0.05), `minWindowShareElapsed` (0.10) and
`minOrders` (5). Until both evidence conditions hold, `Forecast.recommendationStatus = "too_early"`,
`recommendedQuantity` = the planned quantity and `newsvendorQuantity` is what the maths would say so far;
`Forecast.evidence = {ready, orders, minOrders, windowShareElapsed, minWindowShareElapsed, note}`. The exposure floor
tempers the posterior mean early in the window (E[Λ] = (α₀ + U + m₀·max(0, g_min − G)) / (β₀ + max(G, g_min)), shape
α₀ + U), so a few launch-day orders can't be extrapolated across the window. Both appear in "How this was calculated".

**Credits.** `HealthResponse.poweredBy` gains `modelConnected` and `hardware?`; `amd` is true only when a real model
endpoint is connected **and** its hardware is verified AMD (`AMD_GPU_LABEL`, or the diffusion server's device, naming
an AMD GPU). Otherwise the header says "Model connected — hardware not verified".

| Method | Path | Returns |
|---|---|---|
| GET | `/api/designs/{designId}/rfq-recipients` | `{recipients: [{supplierName, region, toEmail, override, language}], sends}` — who approving would email (RFQ override inboxes marked); read-only. The guided tour shows it and waits for the presenter to press Approve. |

**422s** read as plain sentences ("The direction is too long — keep it to 500 characters (this one has 612).").

## v5 — Access, uploads and quote integrity (QA fixes)

### Who may change data

- **Origin check.** Every `POST` / `PUT` / `PATCH` / `DELETE` under `/api/` (except `/api/webhooks/*`, which are
  authenticated by Shopify's HMAC / the Evolus shared secret) is rejected with `403 {detail, auth: "forbidden"}` when
  its `Origin` — or, without one, its `Referer` — is not in `CORS_ORIGINS` (or `PUBLIC_BASE_URL`). Requests with
  neither header (curl, scripts) are judged by the next rule.
- **`ATELIER_ADMIN_TOKEN` set:** those requests need `Authorization: Bearer <token>` or the session cookie from
  `POST /api/auth/login`; otherwise `401 {detail, auth: "required"}` (the dashboard opens a sign-in form).
- **Not set:** only this machine may change data — loopback clients, plus `ATELIER_TRUSTED_NETWORKS` (CIDRs;
  docker-compose adds Docker's bridge because its ports are published on `127.0.0.1` only). Others get `403`.
- Private files (`GET /api/runs/{id}/quotes/documents/{name}`, `GET /api/workspace/documents/{id}/file`,
  `GET /api/quotes/unmatched`) follow the same rule for reads. With a token set, `GET /api/runs/{id}` omits
  customers' `firstName` / `city` from `demand.recentOrders` unless signed in; step logs never contain them.
- Every response carries `X-Content-Type-Options: nosniff`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/auth/status` | — | `SecuritySummary` |
| POST | `/api/auth/login` | `{token}` | `SecuritySummary` + HttpOnly `atelier_session` cookie (SameSite=Lax, 12 h); `401` wrong token, `409` none configured |
| POST | `/api/auth/logout` | — | `SecuritySummary` |

```ts
interface SecuritySummary { adminTokenRequired: boolean; authenticated: boolean;
                            mutations: "admin-token" | "local-only"; localClient: boolean }
// HealthResponse gains `security?: SecuritySummary`.
```

### Uploads

Quote documents, certificates and mood-board uploads are accepted only when their **bytes** are PDF / PNG / JPEG /
WebP (brand books: a real PDF, a real `.docx`, or UTF-8 Markdown / text); otherwise `422` (`415` for mood-board
images). The uploader's name and `Content-Type` are never used for storage or serving. Quote documents are stored
**only after a quote was read from them**, under `ATELIER_DATA_DIR/quotes/<runId>/` (not `/static`);
`QuoteSource.documentUrl` is now `/api/runs/{runId}/quotes/documents/{name}` (inline, real type, private).

`POST /api/trends/analyze {imageUrls}`: `https` only, port 443, no credentials; every DNS answer must be a public
address (no private / loopback / link-local / CGNAT / multicast / reserved, IPv4 or IPv6, also after each redirect —
at most 3); the backend fetches the image itself (10 s, 12 MB, PNG / JPEG / WebP by magic bytes) and sends the
bytes to the vision model — a user URL is never passed to vLLM. Rejections are `422 "image URL rejected: …"`.
`503` (vision not connected) is checked before any image.

### Quotes

- **PO lock.** Once `demand.purchaseOrder` exists, `POST /api/runs/{id}/quotes`, the inbound webhook and
  `assign` answer `409` ("… quotes that arrive now are not used"): a late quote never changes the supplier.
- **Duplicates.** The same file again, the same `extractionId` / `executionId`, or the same mill + quote number +
  unit price + currency is a duplicate: no new revision; upload returns the run unchanged (`200`), the webhook
  `200 {ok, duplicate: true, …}`. `SupplierQuote.duplicates` counts them.
- **Verification.** `unitPrice`, `moq` and `leadTime` must be printed in the document's text.
  `ExtractedField.verified`: `true` / `false` (not found) / absent (no text: image, email without `documentText`).
  `SupplierQuote.unverifiedFields: ("unitPrice" | "moq" | "leadTime")[]` — such values are left out of the score, an
  unverified price is never picked automatically, confidence is halved and a warning is added. When every comparable
  price is unverified, the quotes step waits for a person. `POST /api/runs/{id}/quotes/confirm {supplierName, actor?}`
  → `PipelineRun` (sets `confirmedBy`, `confirmedAt`; audit `quote_confirmed`; `409` when nothing to confirm).
- **Currency.** `€`, `Euro`, `eur` → `EUR`; `$`, `US$` → `USD`; `£` → `GBP`; `RMB` → `CNY`; `CHF`, `Fr.` → `CHF`;
  `HK$`, `C$`, `A$` …; `¥` / `kr` are ambiguous and kept as printed with a warning (not converted). An unrecognised
  value is kept as printed with a warning — never read as the brand currency.
- **Numbers.** Negative prices are rejected (`422 "… negative …"`); a negative MOQ / sample cost is ignored with a
  warning. `1.250` is 1250 for quantities and 1.25 for prices (with an "ambiguous separator" warning).
- **Inbound matching.** An emailed quote is attached only by `runId` / RFQ ref, by a known sender (contact address
  or the supplier's company domain) that one open run waits for, or when exactly one run is open. Otherwise the
  webhook answers `202 {ok, parked: true, unmatchedId}`; `GET /api/quotes/unmatched` lists them and
  `POST /api/quotes/unmatched/{id}/assign/{runId}` → `PipelineRun` attaches one.

### Sends whose outcome is unknown

When an Evolus workflow was started (it has an execution id) but its status can't be read, nothing is reported as
"not sent": `PipelineStep.unknownExecutionId` (RFQs), `PurchaseOrder.status = "unknown"`,
`CounterOffer.status = "unknown"` with the execution id. Re-sending needs a confirmation:
`POST /api/runs/{id}/retry {"confirmResend": true}` (else `409`), `POST …/purchase-order/send?confirm=resend`,
`POST …/decision/counter-offer/send?confirm=resend`. `CounterOffer.status` also has `"sending"`: a second send while
one is in flight, or after it was sent, is `409`.

### Other

- `POST /api/designs/{id}/approve` is idempotent: while a run for the design is `running` or `failed` it returns that
  run with `existing: true`; the `Idempotency-Key` header returns the same run for the same key.
- Shopify: a transport error / timeout is a Shopify error like any other; the order poll keeps going with backoff.
  A product created before a later setup call failed is kept (its id on the run) and **Retry** repairs it — no
  duplicate. "Pre-order live" is only logged when the product is published.
- Failures fail fast: timeouts / connection / 5xx errors are not retried (an invalid answer still gets one retry).
  Defaults: `ATELIER_LLM_TIMEOUT=45`, `ATELIER_VISION_TIMEOUT=45`, `EVOLUS_AGENT_TIMEOUT=60`,
  `ATELIER_EXTRACTOR_TIMEOUT=60` (new).
- `vibe` (generate / refine) is limited to 500 characters (`422 "The vibe is too long — keep it to 500 characters (this one has 612)."`).

New env vars: `ATELIER_ADMIN_TOKEN`, `ATELIER_TRUSTED_NETWORKS`, `ATELIER_EXTRACTOR_TIMEOUT`; compose:
`BACKEND_BIND`, `FRONTEND_BIND` (default `127.0.0.1`).
