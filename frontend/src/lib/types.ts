// Mirrors CONTRACT.md (v5) exactly. Do not diverge - the contract is binding.

/** v5: a service is connected, unreachable (configured but failing) or not configured. */
export type ConnectionStatus = "connected" | "unreachable" | "not_configured";

export type ServiceStatus = {
  name: string;
  status: ConnectionStatus;
  /** == (status === "connected"). */
  healthy: boolean;
  detail?: string;
  /** How to set it up / fix it (with not_configured / unreachable). */
  hint?: string;
  /** Not needed right now: an alternative path is connected. Not counted as missing. */
  optional?: boolean;
  /** The endpoint is the local test double - NOT a real service. */
  fake: boolean;
  /** What a probe actually saw. */
  model?: string;
  host?: string;
  latencyMs?: number;
  gpu?: string;
};

export interface HealthResponse {
  status: "ok";
  services: ServiceStatus[];
  /**
   * Which credits may be shown - only for a real (not fake) connected service. `amd` also needs the hardware
   * verified (AMD_GPU_LABEL or the diffusion server naming an AMD device); a model that answers on unverified
   * hardware is `modelConnected` only.
   */
  poweredBy: { amd: boolean; evolus: boolean; modelConnected?: boolean; hardware?: string };
  /** Any configured endpoint is the local test double. */
  fakeUpstreams: boolean;
  /** QA H5: how changes are authorised. */
  security?: SecuritySummary;
}

/** QA H5: ATELIER_ADMIN_TOKEN set -> sign in (or Bearer token) for every change; unset -> only this machine. */
export interface SecuritySummary {
  adminTokenRequired: boolean;
  authenticated: boolean;
  mutations: "admin-token" | "local-only";
  localClient: boolean;
}

/** v5: body of a 503 - a real service is missing or failed. */
export interface ServiceErrorBody {
  detail: string;
  service?: string;
  status?: "not_configured" | "unreachable";
  hint?: string;
}

export interface TrendPreset {
  id: string;
  name: string;
  thumbnailUrl: string;
}

export interface TrendAnalysis {
  id: string;
  trendName: string;
  summary: string;
  garmentType: string;
  coreSilhouettes: string[];
  colorPalette: string[];
  keyFabrics: string[];
  commercialViabilityScore: number;
  sourceImageUrls: string[];
  createdAt: string;
}

export interface Design {
  id: string;
  trendId: string;
  parentDesignId?: string;
  imageUrl: string;
  prompt: string;
  garmentType: string;
  vibe?: string;
  seed: number;
  createdAt: string;
  /** v2: set when the design came from POST /api/designs/{id}/direct. */
  directionId?: string;
  /** v2: set when the design is (or descends from) a look in a generated collection. */
  collectionId?: string;
  /** The designer's own sketch / photo instead of a diffusion render. */
  source?: "designer_upload";
  /** The vision model's reading of the sketch (only what it can see). */
  sketchReading?: SketchReading;
}

export interface SketchReading {
  garmentType: string;
  garmentName?: string;
  description: string;
  details: string[];
  colors: string[];
  fabricsSuggested: string[];
  model?: string;
}

export interface BillOfMaterialsItem {
  material: string;
  quantity: string;
  targetCostPerUnit: number;
}

export interface TechPack {
  garmentName: string;
  description: string;
  billOfMaterials: BillOfMaterialsItem[];
  measurements: Record<string, string>;
  targetSupplierRegion: string;
  targetRetailPrice: number;
  productionQuantity: number;
  /** v2: the effective colourway (hex) - the trend palette after any creative direction re-coloured it. */
  colorway?: string[];
  /** v3: knowledge-library passages the agent followed. */
  citations?: Citation[];
  /** v3: which brain wrote it: "evolus-agent → AMD vLLM" | "direct vLLM". */
  generatedBy?: string;
  /** v5: construction notes written by the brain (seams, finishes, closures). */
  constructionNotes?: string[];
  /** v3: customer-voice changes applied to this tech pack, with their cited evidence. */
  customerEvidence?: CustomerEvidence[];
  /** v4: sizes offered on Shopify (one variant each). Absent -> a "size range" measurement, else XS–XL. */
  sizeRange?: string[];
  /** The brand currency every price on the tech pack is in (BOM target costs, retail). */
  currency?: string;
}

/** v3: a knowledge-library source (brand book, supplier catalogue). */
export interface Citation {
  source: string;
  snippet?: string;
  /** "evolus" = returned by the Evolus library; "local" = the same docs retrieved by Atelier for the prompt. */
  library: "evolus" | "local";
  documentId?: string;
  score?: number;
}

export interface SupplierEmail {
  supplierName: string;
  region: string;
  toEmail: string;
  subject: string;
  body: string;
  status: "drafted" | "queued" | "sent";
  /** v3: "ATL-run_…", quoted in the subject so replies can be matched. */
  rfqRef?: string;
  /** v4: written in the mill's language (ISO 639-1); the English version is kept alongside. */
  language?: string;
  languageName?: string;
  subjectEnglish?: string;
  bodyEnglish?: string;
  kind?: "rfq" | "counter_offer";
}

export interface ShopifyProduct {
  productId: string;
  title: string;
  handle: string;
  url: string;
  price: number;
  status: "preorder";
  imageUrl: string;
  // v3 (CONTRACT.md "v3 - Real Shopify pre-orders")
  /** "shopify" = created via the Admin API; "evolus" = created by the Evolus workflow. */
  source?: "shopify" | "evolus";
  adminUrl?: string;
  shopDomain?: string;
  /** What the stage shows under the QR code. */
  shortUrl?: string;
  /** Backend-generated QR code (SVG) that encodes `url`. */
  qrUrl?: string;
  /** Only present when SHOPIFY_STOREFRONT_PASSWORD is configured. */
  storefrontPassword?: string;
  variantId?: string;
  published?: boolean;
  /** v4: one variant per size. Absent = no Size option (e.g. an Evolus listing) - orders carry no size. */
  sizes?: string[];
  /** v4: size -> gid://shopify/ProductVariant/… */
  variantIds?: Record<string, string>;
  /** `price` is in the STORE's currency (absent = not verified). */
  currency?: string;
  /** The tech pack retail in the brand currency. Differs from `price` when the store sells in another currency. */
  priceBrand?: number;
  brandCurrency?: string;
  /** Store-currency units per 1 brand-currency unit (ECB reference rate), when converted. */
  fxRate?: number;
  fxDate?: string;
}

export type StepKey =
  | "techpack"
  | "supplier_outreach"
  | "supplier_quotes"
  | "shopify_preorder"
  | "preorder_demand";

export interface PipelineStep {
  key: StepKey;
  label: string;
  status: "pending" | "running" | "done" | "error";
  startedAt?: string;
  finishedAt?: string;
  log: string[];
  error?: string;
  /** v5: which service is missing / failing ("brain" | "evolus_outreach" | "shopify" | …). */
  service?: string;
  /** v5: how to set it up / fix it. */
  hint?: string;
  /** v5: POST /api/runs/{id}/retry can resume from this step. */
  retryable?: boolean;
  /** v2: inference / Evolus calls this step made (live-updating while it runs). */
  telemetry?: InferenceCall[];
  /** v3: which brain ran: "evolus-agent → AMD vLLM" | "direct vLLM". */
  route?: string;
  /** QA M3: an Evolus workflow started but its outcome is unknown - retrying may e-mail twice (needs a confirm). */
  unknownExecutionId?: string;
}

export interface PipelineRun {
  id: string;
  designId: string;
  status: "running" | "completed" | "failed";
  steps: PipelineStep[];
  techPack?: TechPack;
  supplierEmails?: SupplierEmail[];
  shopifyProduct?: ShopifyProduct;
  createdAt: string;
  // v2 - business loop
  originalTechPack?: TechPack;
  techPackRevision?: number;
  quotes?: SupplierQuote[];
  recommendation?: SupplierRecommendation;
  demand?: PreorderDemand;
  /** v3: the RFQ round - replies received vs awaited. */
  quoteRound?: QuoteRound;
  /** v4: every quote against the brand guardrails. */
  guardrailReport?: GuardrailReport;
  /** v4: the human hand-off; status pending / negotiating = waiting for a person. */
  decision?: Decision;
  /** v4: who decided what, when, which guardrail, the numbers. */
  audit?: AuditEntry[];
  /** v5: from the persisted per-brand style sequence, assigned with the tech pack. */
  styleNumber?: string;
}

// --- v3: Evolus brain & real quotes (CONTRACT.md "v3") ---

export interface ExtractedField {
  name: string;
  value: string;
  confidence?: number;
  /** QA M10: true = printed in the document text; false = not found ("unverified"); absent = not checkable. */
  verified?: boolean | null;
}

export interface QuoteSource {
  channel: "upload" | "email";
  engine: string;
  engineLabel: string;
  documentUrl?: string;
  filename?: string;
  contentType?: string;
  sender?: string;
  confidence?: number;
  fields: ExtractedField[];
  warnings: string[];
  extractionId?: string;
}

export interface QuoteRound {
  status: "awaiting" | "complete" | "closed";
  rfqRef: string;
  expected: number;
  received: number;
  awaiting: string[];
  openedAt: string;
  closedAt?: string;
}

// --- v2: business loop (CONTRACT.md "v2 - Business loop") ---

/** 0-100 per criterion; null when the quote does not state it (or the price could not be converted). */
export interface ScoreBreakdown {
  price: number | null;
  moq: number | null;
  leadTime: number | null;
}

export interface SupplierQuote {
  supplierName: string;
  region: string;
  /** Brand currency; null = quoted in another currency with no FX rate (see unitPriceQuoted + currency). */
  unitPrice: number | null;
  /** null / absent = not stated on the document. */
  moq?: number | null;
  leadTimeWeeks?: number | null;
  sampleCost?: number | null;
  paymentTerms?: string | null;
  /** The mill's own message, verbatim ("" when none). */
  note: string;
  receivedAt: string;
  /** v5: ECB reference-rate conversion from `currency` to the brand currency. */
  fxRate?: number;
  fxSource?: string;
  fxDate?: string;
  score: number;
  scoreBreakdown: ScoreBreakdown;
  // v3: real quote documents
  quoteNumber?: string;
  validUntil?: string;
  currency?: string;
  source?: QuoteSource;
  // v4: multilingual replies and revised quotes
  language?: string;
  noteEnglish?: string;
  /** Brain route | "phrasebook" | "untranslated". */
  noteTranslation?: string;
  unitPriceQuoted?: number;
  sampleCostQuoted?: number;
  revision?: number;
  revises?: string;
  /** QA M10: numbers not found in the document text ("unitPrice" | "moq" | "leadTime") until a person confirms. */
  unverifiedFields?: string[];
  confirmedBy?: string;
  confirmedAt?: string;
  /** QA M9: identical copies received again and ignored. */
  duplicates?: number;
}

/** LOW: an inbound (email) quote that matched no run, waiting for a person to assign it. */
export interface UnmatchedQuote {
  id: string;
  receivedAt: string;
  sender?: string | null;
  supplierName?: string | null;
  quoteNumber?: string | null;
  subject?: string | null;
  reason: string;
}

export interface SupplierRecommendation {
  supplierName: string;
  /** Drafted by the brain; null when no brain is connected / it failed (see rationaleError). */
  rationale?: string | null;
  rationaleError?: string;
  score: number;
  weights: ScoreBreakdown;
  selectedSupplierName: string;
  overridden: boolean;
  citations?: Citation[];
  generatedBy?: string;
}

export interface DemandPoint {
  hour: number;
  orders: number;
}

/** v5: a real PO, sent through Evolus. Without Evolus it stays a draft - never "issued". */
export interface PurchaseOrder {
  /** "PO-00001" (persisted sequence). */
  poNumber: string;
  supplierName: string;
  region: string;
  toEmail?: string;
  quantity: number;
  /** The currency the mill quoted in (the PO is placed in it). */
  currency: string;
  /** In `currency`, as quoted. */
  unitPrice: number;
  total: number;
  unitPriceBrand?: number;
  totalBrand?: number;
  /** The currency of unitPriceBrand / totalBrand. */
  brandCurrency?: string;
  /** null / absent = not stated. */
  leadTimeWeeks?: number | null;
  quoteNumber?: string;
  rfqRef?: string;
  /** QA M3: "unknown" = the Evolus workflow started but its outcome couldn't be read - check Evolus. */
  status: "draft" | "sending" | "queued" | "sent" | "failed" | "unknown";
  createdAt: string;
  sentAt?: string;
  sentVia?: string;
  executionId?: string;
  sendError?: string;
  hint?: string;
}

/** v3: one real Shopify order containing the product. Privacy: first name + city only. */
export interface PreorderOrder {
  orderId: string;
  name: string;
  createdAt: string;
  units: number;
  amount: number;
  currency: string;
  firstName?: string;
  city?: string;
  test: boolean;
  via: "poll" | "webhook";
  /** v4: this product's line items (an order for an M and an L has two). */
  lines?: PreorderLine[];
}

/** v3: one product line from a real order, for the forecast. v4: one per line item; lines share `orderId`. */
export interface DemandOrderEvent {
  timestamp: string;
  quantity: number;
  size?: string;
  unitPrice?: number;
  orderId?: string;
}

/** v4: one line item of the product in a real order. */
export interface PreorderLine {
  /** From the variant's Size option; absent when the variant has no size. */
  size?: string;
  quantity: number;
  amount: number;
}

export interface PreorderDemand {
  status: "collecting" | "unlocked" | "expired";
  /** What `units` must reach - the stage threshold when one is in effect. */
  threshold: number;
  thresholdBasis: "productionQuantity" | "moq" | "stage";
  orders: number;
  revenue: number;
  windowHours: number;
  elapsedHours: number;
  hoursLeft: number;
  /** Cumulative units by hour since launch. */
  series: DemandPoint[];
  unlockedAtHour?: number;
  purchaseOrder?: PurchaseOrder;
  // v3: real Shopify orders
  source?: "shopify";
  units?: number;
  /** max(productionQuantity, chosen MOQ): the PO quantity. */
  productionThreshold?: number;
  productionThresholdBasis?: "productionQuantity" | "moq";
  /** DEMAND_STAGE_THRESHOLD when in effect. */
  stageThreshold?: number;
  currency?: string;
  recentOrders?: PreorderOrder[];
  /** Every order line, oldest first (forecast input). v4: one event per line item, with its size. */
  orderEvents?: DemandOrderEvent[];
  /** How many of `orders` are test-mode orders (always labelled "test order"). */
  testOrders?: number;
  testUnits?: number;
  tracking?: string;
  lastCheckedAt?: string;
  trackingError?: string;
}

export type TechPackPatch = Partial<TechPack>;

export interface MaterialOption {
  material: string;
  targetCostPerUnit: number;
  note: string;
  tag?: string;
  original: boolean;
}

export interface BomAlternatives {
  index: number;
  family: string;
  options: MaterialOption[];
}

export type AnalyzeInput =
  | { kind: "files"; files: File[] }
  | { kind: "urls"; imageUrls: string[] }
  | { kind: "preset"; preset: string };

// --- v2: creative direction & collections (CONTRACT.md "v2") ---------------

export interface PaletteShift {
  before: string[];
  after: string[];
  note: string;
}

export interface CreativeDirection {
  id: string;
  designId: string;
  instruction: string;
  interpretation: string;
  promptAdditions: string[];
  promptRemovals: string[];
  paletteShift?: PaletteShift;
  silhouetteChanges: string[];
  techPackHints: string[];
  references: string[];
  /** v5: fabric swaps the brain made (shell first). */
  fabricsAfter?: string[];
  createdAt: string;
  generatedBy?: string;
  citations?: Citation[];
}

export interface DirectResponse {
  direction: CreativeDirection;
  designs: Design[];
}

export interface CollectionLook {
  designId: string;
  title: string;
  caption: string;
}

export interface Collection {
  id: string;
  trendId: string;
  name: string;
  story: string;
  designs: Design[];
  looks: CollectionLook[];
  /** v5: brain route that planned it. */
  generatedBy?: string;
  createdAt: string;
}

// --- v2: live infrastructure & inference stats (CONTRACT.md v2) -------------------

export type TelemetryService = "llm" | "vision" | "diffusion" | "evolus";

/** One real upstream call, measured. `fake` = the endpoint is the local test double, not a real service. */
export interface InferenceCall {
  id: string;
  service: TelemetryService;
  purpose: string;
  ok: boolean;
  fake: boolean;
  model?: string;
  endpointHost?: string;
  gpu?: string;
  startedAt: string;
  latencyMs: number;
  ttftMs?: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  tokensPerSec?: number;
  images?: number;
  imagesPerSec?: number;
  serverMs?: number;
  attempt: number;
  error?: string;
  detail?: string;
  /** v3: "evolus-agent → AMD vLLM" | "direct vLLM" | "evolus-extractor" | "amd-llm" | … */
  route?: string;
}

/** Aggregates for one service (measured calls only). */
export interface ServiceTelemetry {
  service: TelemetryService;
  calls: number;
  errors: number;
  avgLatencyMs?: number;
  p95LatencyMs?: number;
  avgTtftMs?: number;
  promptTokens: number;
  completionTokens: number;
  avgTokensPerSec?: number;
  peakTokensPerSec?: number;
  images: number;
  avgImagesPerSec?: number;
  lastModel?: string;
  lastEndpointHost?: string;
  gpu?: string;
  lastAt?: string;
}

export interface TelemetryResponse {
  gpuLabel?: string;
  calls: InferenceCall[];
  services: ServiceTelemetry[];
}

// --- v3: explained production forecast (CONTRACT.md "v3 - Explained production forecast") ---

export interface OrderEvent {
  timestamp: string;
  quantity: number;
  size?: string;
  unitPrice?: number;
}

export interface ForecastEconomics {
  unitCost: number;
  retailPrice: number;
  salvageValue?: number;
  moq: number;
  fixedCosts: number;
  /** ISO code the prices are in (the brand currency). */
  currency?: string;
}

export interface ForecastAssumptions {
  priorMeanPreorders: number;
  priorCv: number;
  bassP: number;
  bassQ: number;
  seasonMultiplier: number;
  sizeCurve: Record<string, number>;
  sizePriorStrength: number;
  unsoldRiskThreshold: number;
  levelCvFloor: number;
  /** Early-window exposure floor g_min: G(t) counts as at least this share of a window. */
  minExposure: number;
  /** Evidence threshold: share of the window (time) that must pass before recommending. */
  minWindowShareElapsed: number;
  /** Evidence threshold: orders needed before recommending. */
  minOrders: number;
}

export interface ForecastRequest {
  orders: OrderEvent[];
  launchAt: string;
  asOf?: string;
  windowHours: number;
  economics: ForecastEconomics;
  assumptions?: Partial<ForecastAssumptions>;
  plannedQuantity?: number;
}

export interface ForecastInterval {
  mean: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface ForecastProjectionPoint {
  hour: number;
  mean: number;
  p10: number;
  p90: number;
}

export interface ForecastSizeLine {
  size: string;
  orders: number;
  baseShare: number;
  share: number;
  units: number;
}

export interface ForecastOutcome {
  quantity: number;
  expectedUnitsSold: number;
  expectedLeftover: number;
  expectedRevenue: number;
  expectedSalvage: number;
  expectedCost: number;
  expectedProfit: number;
  expectedMargin: number;
  stockoutProbability: number;
  fillRate: number;
  unsoldRiskProbability: number;
}

export interface ForecastExplainStep {
  title: string;
  formula: string;
  substituted: string;
  result: string;
}

export interface ForecastAssumptionItem {
  key: string;
  label: string;
  value: string;
  note: string;
}

export interface ForecastDataUsed {
  orderEvents: number;
  units: number;
  sizedUnits: number;
  /** v4: distinct orders with at least one sized line. */
  sizedOrders?: number;
  firstOrderAt?: string;
  lastOrderAt?: string;
  spanHours: number;
  elapsedHours: number;
  windowHours: number;
  windowShareElapsed: number;
  avgOrderPrice?: number;
}

export interface ForecastEvidence {
  ready: boolean;
  orders: number;
  minOrders: number;
  windowShareElapsed: number;
  minWindowShareElapsed: number;
  note: string;
}

export interface Forecast {
  method: string;
  llmUsed: false;
  confidence: "prior-only" | "early" | "firming" | "data-driven";
  confidenceNote: string;
  /** "too_early": not enough evidence yet - recommendedQuantity is the planned quantity. */
  recommendationStatus?: "too_early" | "recommended";
  evidence?: ForecastEvidence;
  /** The currency of every money figure (the brand currency). */
  currency?: string;
  recommendedQuantity: number;
  /** What the newsvendor maths says on the evidence so far (= recommendedQuantity once ready). */
  newsvendorQuantity?: number;
  unconstrainedQuantity: number;
  moq: number;
  moqBinding: boolean;
  moqNote?: string;
  criticalRatio: number;
  underageCost: number;
  overageCost: number;
  unitCost: number;
  retailPrice: number;
  salvageValue: number;
  fixedCosts: number;
  preorders: ForecastInterval;
  season: ForecastInterval;
  observedUnits: number;
  outcome: ForecastOutcome;
  baseline?: ForecastOutcome;
  profitDeltaVsBaseline?: number;
  sizes: ForecastSizeLine[];
  projection: ForecastProjectionPoint[];
  observed: { hour: number; units: number }[];
  profitCurve: { quantity: number; expectedProfit: number }[];
  posterior: {
    priorAlpha: number;
    priorBeta: number;
    alpha: number;
    beta: number;
    windowLevelMean: number;
    dataWeight: number;
  };
  explanation: {
    summary: string;
    steps: ForecastExplainStep[];
    assumptions: ForecastAssumptionItem[];
    data: ForecastDataUsed;
    notes: string[];
  };
  inputs: ForecastRequest;
  asOf: string;
  launchAt: string;
}

// --- v3: customer voice (CONTRACT.md "v3 - Customer voice") -----------------

export interface VoiceQuote {
  recordId: string;
  field: "text" | "title" | "returnReason" | "fitFeedback";
  /** Exact excerpt of the record - never paraphrased. */
  text: string;
  truncated: boolean;
  matchStart?: number;
  matchEnd?: number;
  rating?: number;
  garmentClass?: string;
}

export interface VoiceSource {
  kind: "upload" | "sample";
  filename?: string;
  datasetKey?: string;
  title?: string;
  url?: string;
  licence?: string;
  attribution?: string;
}

export interface VoiceClassCount {
  garmentClass: string;
  count: number;
  total: number;
  share: number;
}

export type VoicePolarity = "negative" | "positive" | "mixed";

export interface VoiceTheme {
  id: string;
  group: string;
  groupLabel: string;
  name: string;
  kind: "problem" | "praise" | "rating";
  polarity: VoicePolarity;
  count: number;
  share: number;
  negativeCount: number;
  positiveCount: number;
  neutralCount: number;
  avgRating?: number;
  returnedCount: number;
  byClass: VoiceClassCount[];
  quotes: VoiceQuote[];
  recordIds: string[];
}

export interface ChangeEvidence {
  count: number;
  base: number;
  share: number;
  garmentClass?: string;
  avgRating?: number;
  baselineRating?: number;
  summary: string;
  recordIds: string[];
  quotes: VoiceQuote[];
}

export interface RecommendedChange {
  id: string;
  themeId: string;
  title: string;
  action: string;
  techPackChange: string;
  area: "measurements" | "bom" | "construction" | "testing" | "colour" | "pricing";
  /** Which points of measure the change concerns (names, no values). */
  pointsOfMeasure: string[];
  /** v5: concrete tech-pack instruction drafted by the brain from the evidence. */
  instruction?: string;
  instructionBy?: string;
  confidence: "high" | "medium" | "low";
  priority: number;
  evidence: ChangeEvidence;
  rationale?: string;
  conflictsWith: string[];
}

export interface VoiceInsights {
  id: string;
  name: string;
  source: VoiceSource;
  noun: string;
  recordCount: number;
  analysedCount: number;
  columns: Record<string, string>;
  avgRating?: number;
  garmentClasses: VoiceClassCount[];
  themes: VoiceTheme[];
  recommendedChanges: RecommendedChange[];
  summary: string;
  method: string;
  warnings: string[];
  /** v5: brain route that phrased the summary / rationales / instructions. */
  phrasedBy?: string;
  /** v5: why the brain didn't (not connected / failed). */
  phrasingError?: string;
  createdAt: string;
}

export interface VoiceSample {
  key: string;
  title: string;
  description: string;
  records: number;
  source: VoiceSource;
}

export interface CustomerEvidence {
  datasetId: string;
  datasetName: string;
  source: string;
  changeId: string;
  title: string;
  techPackChange: string;
  area: string;
  count: number;
  base: number;
  share: number;
  garmentClass?: string;
  recordIds: string[];
  quotes: VoiceQuote[];
  /** v5: concrete instruction drafted by the brain from the evidence. */
  instruction?: string;
  instructionBy?: string;
}

export interface VoiceApplyResponse {
  datasetId: string;
  target: { kind: "design" | "trend"; id: string };
  applied: CustomerEvidence[];
}

// --- v4: guardrails, human hand-off & multilingual sourcing (CONTRACT.md "v4") ---

export type GuardrailRule = "min_margin" | "max_unit_cost" | "max_lead_time" | "max_moq" | "certifications";

/** v5: set by the brand in the Brand workspace; an absent rule is not set (and not checked). */
export interface Guardrails {
  minGrossMarginPct?: number;
  /** Absent = derived per run from the tech pack costing + `costHeadroomPct` (when a headroom is set). */
  maxUnitCost?: number;
  costHeadroomPct?: number;
  maxLeadTimeWeeks?: number;
  maxMoq?: number;
  requiredCertifications: string[];
  certificationsMode: "all" | "any";
  currency: string;
  updatedAt?: string;
  updatedBy?: string;
  /** v5: the brand reviewed the guardrails (even leaving rules empty). */
  reviewedAt?: string;
  /** v5: rules not set, so not checked: min_margin, max_unit_cost, max_lead_time, max_moq, certifications. */
  unset?: string[];
}

/** PUT /api/guardrails: any subset; `null` clears a rule (then it is not checked). */
export type GuardrailsPatch = Partial<{
  minGrossMarginPct: number | null;
  maxUnitCost: number | null;
  costHeadroomPct: number | null;
  maxLeadTimeWeeks: number | null;
  maxMoq: number | null;
  requiredCertifications: string[];
  certificationsMode: "all" | "any";
}>;

export interface GuardrailCheck {
  rule: GuardrailRule;
  label: string;
  ok: boolean;
  actual: string;
  limit: string;
  actualValue?: number;
  limitValue?: number;
  message: string;
}

export interface QuoteEvaluation {
  supplierName: string;
  ok: boolean;
  /** Brand currency; null = not convertible. */
  unitPrice: number | null;
  marginPct?: number;
  checks: GuardrailCheck[];
  quoteNumber?: string;
  revision: number;
}

export interface GuardrailReport {
  guardrails: Guardrails;
  maxUnitCostDerived: boolean;
  costedUnitCost?: number;
  retailPrice?: number;
  evaluations: QuoteEvaluation[];
  selectedSupplierName?: string;
  selectedOk?: boolean;
  evaluatedAt: string;
}

export interface DecisionOption {
  kind: "approve" | "negotiate" | "switch";
  label: string;
  detail: string;
  supplierName?: string;
}

export interface CounterOffer {
  supplierName: string;
  region: string;
  toEmail: string;
  language: string;
  languageName: string;
  subject: string;
  body: string;
  subjectEnglish: string;
  bodyEnglish: string;
  rfqRef: string;
  quoteNumber?: string;
  currency: string;
  /** The currency of quotedUnitPrice / targetUnitPrice. */
  brandCurrency?: string;
  quotedUnitPrice?: number | null;
  quotedUnitPriceLocal?: number;
  targetUnitPrice?: number | null;
  targetUnitPriceLocal?: number;
  reductionPct: number;
  math: string[];
  /** Brain route that wrote the wording. */
  generatedBy: string;
  edited: boolean;
  /** QA M2/M3: "sending" while in flight; "unknown" = started, outcome unknown. */
  status: "draft" | "sending" | "queued" | "sent" | "unknown";
  sentAt?: string;
  sentVia?: string;
  executionId?: string;
  /** v5: the last send attempt failed (the draft is kept). */
  sendError?: string;
  createdAt: string;
}

export interface AuditEntry
 {
  at: string;
  actor: "agent" | "human" | "system";
  action: string;
  summary: string;
  supplierName?: string;
  guardrail?: string;
  values: Record<string, string>;
  note?: string;
}

export interface Decision {
  id: string;
  /** pending / negotiating = the run is waiting for a person; nothing reaches Shopify until resolved. */
  status: "pending" | "negotiating" | "resolved";
  supplierName: string;
  headline: string;
  explanation: string;
  breaches: GuardrailCheck[];
  allQuotesBreach: boolean;
  options: DecisionOption[];
  counterOffer?: CounterOffer;
  negotiationRounds: number;
  outcome?: "approved" | "switched" | "revised" | "guardrails_changed" | "techpack_changed";
  resolvedSupplierName?: string;
  resolvedBy?: string;
  resolvedAt?: string;
  note?: string;
  createdAt: string;
}

// --- v5: real mood boards (openly licensed photos, analysed live) -------------

/** One mood-board image with the attribution its licence requires. */
export interface SourceImage {
  url: string;
  title: string;
  creator: string;
  sourceUrl: string;
  license: string;
  licenseUrl: string;
  modifications?: string;
  /** The pilot brand's own AI-generated inspiration image, never a photograph. */
  aiGenerated?: boolean;
}

/** The live vision call that produced a TrendAnalysis (from its telemetry record). */
export interface AnalyzedBy {
  model?: string;
  endpointHost?: string;
  gpu?: string;
  latencyMs?: number;
  callId?: string;
  /** v6: images the model actually read (max per prompt, default 4) out of those submitted. */
  imagesAnalyzed?: number;
  imagesSubmitted?: number;
}

// Declaration merging: v5 fields on the existing interfaces (all optional, additive).
export interface TrendPreset {
  /** e.g. "Photos: Masaki-H · CC BY 2.0 · via Wikimedia Commons" */
  credit?: string;
  images?: SourceImage[];
  /** The pilot brand's own AI-generated inspiration board: labelled as such, never shown as photos. */
  aiGenerated?: boolean;
}

export interface TrendAnalysis {
  analyzedBy?: AnalyzedBy;
  sourceImages?: SourceImage[];
}
