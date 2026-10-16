// Typed client for the Atelier backend. See CONTRACT.md (v5).
//
// v5: every call goes to the real backend. When a service a request needs is not
// configured or fails, the backend answers 503 `{ detail, service, status, hint }` and this client throws an
// `ApiError` that carries `service`, `serviceStatus` and `hint`, so screens can show "Not connected: …" + the setup
// hint + a Retry button - never made-up output.
import type {
  AnalyzeInput,
  Collection,
  BomAlternatives,
  Design,
  DirectResponse,
  Forecast,
  ForecastRequest,
  Guardrails,
  GuardrailsPatch,
  HealthResponse,
  PipelineRun,
  SecuritySummary,
  ServiceErrorBody,
  TelemetryResponse,
  TechPackPatch,
  TrendAnalysis,
  TrendPreset,
  UnmatchedQuote,
  VoiceApplyResponse,
  VoiceInsights,
  VoiceSample,
} from "./types";

export * from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8787"
).replace(/\/+$/, "");

export class ApiError extends Error {
  /** HTTP status, or 0 when the backend could not be reached at all. */
  readonly status: number;
  readonly isNetwork: boolean;
  /** v5 (503): the service that is missing or failing, e.g. "vision", "diffusion", "brain", "evolus_po". */
  readonly service?: string;
  /** v5 (503): "not_configured" | "unreachable". */
  readonly serviceStatus?: "not_configured" | "unreachable";
  /** v5 (503): how to set the service up / fix it. */
  readonly hint?: string;

  constructor(
    message: string,
    status: number,
    extra: { service?: string; serviceStatus?: "not_configured" | "unreachable"; hint?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.isNetwork = status === 0;
    this.service = extra.service;
    this.serviceStatus = extra.serviceStatus;
    this.hint = extra.hint;
  }

  /** A real service the request needs is not configured / not answering (HTTP 503). */
  get isServiceError(): boolean {
    return this.status === 503;
  }
}

export function isNetworkError(err: unknown): boolean {
  return err instanceof ApiError && err.isNetwork;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

/** The setup hint carried by a 503 (or undefined). */
export function errorHint(err: unknown): string | undefined {
  return err instanceof ApiError ? err.hint : undefined;
}

/** QA H5: fired when the backend answers 401 "admin token required" - the sign-in form (AdminLogin) opens. */
export const AUTH_REQUIRED_EVENT = "atelier:auth-required";

export function notifyAuthRequired(status: number, body: unknown): void {
  if (status !== 401 || typeof window === "undefined") return;
  const auth = (body as { auth?: unknown } | null)?.auth;
  if (auth === "required") window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
}

/** Contract says URLs are absolute; resolve relative ones defensively. */
export function resolveAssetUrl(url: string | undefined | null): string {
  if (!url) return "";
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 60_000, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      credentials: "include", // QA H5: the sign-in cookie (only set when ATELIER_ADMIN_TOKEN is configured)
      signal: controller.signal,
      headers: { Accept: "application/json", ...(rest.headers || {}) },
    });
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        `The backend took longer than ${Math.round(timeoutMs / 1000)}s to respond.`,
        408,
      );
    }
    throw new ApiError(`Can't reach the Atelier backend at ${API_BASE}.`, 0);
  }
  clearTimeout(timer);

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`.trim();
    let extra: ConstructorParameters<typeof ApiError>[2] = {};
    try {
      const body = (await res.json()) as Partial<ServiceErrorBody> & { detail?: unknown };
      notifyAuthRequired(res.status, body);
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
      extra = {
        service: typeof body.service === "string" ? body.service : undefined,
        serviceStatus:
          body.status === "not_configured" || body.status === "unreachable" ? body.status : undefined,
        hint: typeof body.hint === "string" ? body.hint : undefined,
      };
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, extra);
  }
  return (await res.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function withJson(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

const run = (runId: string) => `/api/runs/${encodeURIComponent(runId)}`;

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", { timeoutMs: 8_000, cache: "no-store" });
}

export async function getPresets(): Promise<TrendPreset[]> {
  return request<TrendPreset[]>("/api/trends/presets", { timeoutMs: 15_000 });
}

export async function analyzeTrend(input: AnalyzeInput): Promise<TrendAnalysis> {
  if (input.kind === "files") {
    const form = new FormData();
    input.files.forEach((f) => form.append("images", f, f.name));
    return request<TrendAnalysis>("/api/trends/analyze", {
      method: "POST",
      body: form,
      timeoutMs: 180_000,
    });
  }
  const body =
    input.kind === "urls" ? { imageUrls: input.imageUrls } : { preset: input.preset };
  return request<TrendAnalysis>("/api/trends/analyze", { ...json(body), timeoutMs: 180_000 });
}

export async function getTrend(trendId: string): Promise<TrendAnalysis> {
  return request<TrendAnalysis>(`/api/trends/${encodeURIComponent(trendId)}`);
}

export async function generateDesigns(body: {
  trendId: string;
  vibe?: string;
  count?: number;
}): Promise<{ designs: Design[] }> {
  return request<{ designs: Design[] }>("/api/designs/generate", {
    ...json(body),
    timeoutMs: 240_000,
  });
}

export async function refineDesign(
  designId: string,
  body: { vibe: string; count?: number },
): Promise<{ designs: Design[] }> {
  return request<{ designs: Design[] }>(
    `/api/designs/${encodeURIComponent(designId)}/refine`,
    { ...json(body), timeoutMs: 240_000 },
  );
}

/** QA M2: idempotent - a repeated approve (double click, retried request) returns the run already started
 *  (`existing: true`) instead of e-mailing the suppliers again. */
export async function approveDesign(
  designId: string,
  body: { productionQuantity?: number },
  idempotencyKey?: string,
): Promise<{ runId: string; existing?: boolean }> {
  const init = json(body);
  if (idempotencyKey) init.headers = { ...(init.headers as Record<string, string>), "Idempotency-Key": idempotencyKey };
  return request<{ runId: string; existing?: boolean }>(
    `/api/designs/${encodeURIComponent(designId)}/approve`,
    { ...init, timeoutMs: 30_000 },
  );
}

/** Who approving `designId` would email (the outreach shortlist, with RFQ override inboxes). Read-only. */
export interface RfqRecipient {
  supplierName: string;
  region: string;
  toEmail: string;
  override: boolean;
  language: string;
}

export async function getRfqRecipients(designId: string): Promise<{ recipients: RfqRecipient[]; sends: boolean }> {
  return request(`/api/designs/${encodeURIComponent(designId)}/rfq-recipients`, { timeoutMs: 10_000, cache: "no-store" });
}

export async function getRun(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(run(runId), { timeoutMs: 10_000, cache: "no-store" });
}

/** v5: resume a failed run from its first errored step (e.g. after connecting the missing service).
 *  QA M3: `confirmResend` is required when the step's Evolus execution may already have sent the emails. */
export async function retryRun(runId: string, opts: { confirmResend?: boolean } = {}): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/retry`, {
    ...json({ confirmResend: !!opts.confirmResend }),
    timeoutMs: 30_000,
  });
}

// --- v2: creative direction & collections ----------------------------------

export async function directDesign(
  designId: string,
  body: { instruction: string; count?: number },
): Promise<DirectResponse> {
  return request<DirectResponse>(`/api/designs/${encodeURIComponent(designId)}/direct`, {
    ...json(body),
    timeoutMs: 240_000,
  });
}

export async function generateCollection(body: { trendId: string; size?: number }): Promise<Collection> {
  return request<Collection>("/api/collections/generate", { ...json(body), timeoutMs: 240_000 });
}

/** Recent measured inference calls + per-service aggregates. */
export async function getTelemetry(limit = 40): Promise<TelemetryResponse> {
  return request<TelemetryResponse>(`/api/telemetry?limit=${limit}`, {
    timeoutMs: 5_000,
    cache: "no-store",
  });
}

// --- v2: business loop ------------------------------------------------------

/** Persist creative-director edits to the run’s tech pack (open quotes are re-scored; their prices stay as quoted). */
export async function patchTechPack(runId: string, body: TechPackPatch): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/techpack`, {
    ...withJson("PATCH", body),
    timeoutMs: 15_000,
  });
}

/** v5: `priceListDated` / `priceListSource` describe the brand's price list the options were costed from. */
export async function getTechPackAlternatives(
  runId: string,
): Promise<{ lines: BomAlternatives[]; priceListDated?: string; priceListSource?: string }> {
  return request<{ lines: BomAlternatives[]; priceListDated?: string; priceListSource?: string }>(
    `${run(runId)}/techpack/alternatives`,
    { timeoutMs: 10_000 },
  );
}

/** Override the agent's supplier pick (until the PO is drafted). */
export async function chooseSupplier(runId: string, supplierName: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/supplier`, {
    ...withJson("POST", { supplierName }),
    timeoutMs: 10_000,
  });
}

/** v5: send (or re-send after a failure) the drafted PO through the Evolus PO workflow (503 without Evolus). */
export async function sendPurchaseOrder(runId: string, opts: { confirmResend?: boolean } = {}): Promise<PipelineRun> {
  const q = opts.confirmResend ? "?confirm=resend" : ""; // QA M3: status unknown -> explicit re-send only
  return request<PipelineRun>(`${run(runId)}/purchase-order/send${q}`, { method: "POST", timeoutMs: 120_000 });
}

// --- v3: real supplier quotes -------------------------------------------------

/** Upload a supplier's quote document (PDF / image) -> extractor -> SupplierQuote on the run. */
export async function uploadQuote(runId: string, file: Blob, filename: string, supplierName?: string): Promise<PipelineRun> {
  const form = new FormData();
  form.append("file", file, filename);
  if (supplierName) form.append("supplierName", supplierName);
  return request<PipelineRun>(`${run(runId)}/quotes`, {
    method: "POST",
    body: form,
    // QA M9: covers the whole extraction chain (Evolus extractor, then the AMD model, then the translation).
    timeoutMs: 300_000,
  });
}

/** QA M10: a person checked the document and confirms the numbers that weren't found in its text. */
export async function confirmQuote(runId: string, supplierName: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/quotes/confirm`, {
    ...json({ supplierName }),
    timeoutMs: 15_000,
  });
}

/** LOW: inbound (email) quotes that matched no run, waiting for a person. */
export async function getUnmatchedQuotes(): Promise<UnmatchedQuote[]> {
  return request<UnmatchedQuote[]>("/api/quotes/unmatched", { timeoutMs: 10_000, cache: "no-store" });
}

export async function assignUnmatchedQuote(id: string, runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(
    `/api/quotes/unmatched/${encodeURIComponent(id)}/assign/${encodeURIComponent(runId)}`,
    { method: "POST", timeoutMs: 300_000 },
  );
}

/** Stop waiting for the remaining mills and recommend from the quotes in hand. */
export async function closeQuoteRound(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/quotes/close`, { method: "POST", timeoutMs: 10_000 });
}

// --- v4: guardrails & the human hand-off --------------------------------------------

export async function getGuardrails(): Promise<Guardrails> {
  return request<Guardrails>("/api/guardrails", { timeoutMs: 10_000, cache: "no-store" });
}

export async function putGuardrails(patch: GuardrailsPatch): Promise<Guardrails> {
  return request<Guardrails>("/api/guardrails", { ...withJson("PUT", patch), timeoutMs: 10_000 });
}

export async function resetGuardrails(): Promise<Guardrails> {
  return request<Guardrails>("/api/guardrails/reset", { method: "POST", timeoutMs: 10_000 });
}

/** Proceed despite the breach - recorded as an override in the audit log. */
export async function approveDecision(runId: string, note?: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/decision/approve`, {
    ...withJson("POST", { note: note || undefined }),
    timeoutMs: 10_000,
  });
}

export async function switchDecision(runId: string, supplierName: string, note?: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/decision/switch`, {
    ...withJson("POST", { supplierName, note: note || undefined }),
    timeoutMs: 10_000,
  });
}

/** Draft the counter-offer (deterministic target price; wording by the brain - 503 without one). */
export async function negotiateDecision(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`${run(runId)}/decision/negotiate`, { method: "POST", timeoutMs: 120_000 });
}

/** Send the (optionally edited) counter-offer to the mill through the Evolus workflow (503 without Evolus). */
export async function sendCounterOffer(
  runId: string,
  edits: { subject?: string; body?: string } = {},
  opts: { confirmResend?: boolean } = {},
): Promise<PipelineRun> {
  const q = opts.confirmResend ? "?confirm=resend" : ""; // QA M3
  return request<PipelineRun>(`${run(runId)}/decision/counter-offer/send${q}`, {
    ...withJson("POST", edits),
    timeoutMs: 120_000,
  });
}

export function techPackPdfUrl(runId: string, revision = 0): string {
  return `${API_BASE}${run(runId)}/techpack.pdf?rev=${revision}`;
}

// --- v3: explained production forecast -----------------------------------------

/** "How many should we make?" for a run - built from its selected quote, price and pre-orders. */
export async function getRunForecast(runId: string): Promise<Forecast> {
  return request<Forecast>(`${run(runId)}/forecast`, { timeoutMs: 10_000, cache: "no-store" });
}

/** Stateless recompute, e.g. with edited assumptions (POST a forecast's `inputs` back). */
export async function postForecast(body: ForecastRequest): Promise<Forecast> {
  return request<Forecast>("/api/forecast", { ...withJson("POST", body), timeoutMs: 10_000 });
}

// --- v3: customer voice -----------------------------------------------------

export async function getVoiceSamples(): Promise<VoiceSample[]> {
  return request<VoiceSample[]>("/api/voice/samples", { timeoutMs: 10_000 });
}

/** Upload a CSV/TSV export or a PDF of reviews, returns or tickets; returns the analysed insights. */
export async function uploadVoice(file: File): Promise<VoiceInsights> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<VoiceInsights>("/api/voice/upload", { method: "POST", body: form, timeoutMs: 120_000 });
}

export async function analyseVoiceSample(datasetKey: string): Promise<VoiceInsights> {
  return request<VoiceInsights>("/api/voice/sample", { ...json({ datasetKey }), timeoutMs: 120_000 });
}

export async function applyVoiceChanges(
  datasetId: string,
  body: { changeIds: string[]; designId?: string; trendId?: string },
): Promise<VoiceApplyResponse> {
  return request<VoiceApplyResponse>(`/api/voice/${encodeURIComponent(datasetId)}/apply`, {
    ...json(body),
    timeoutMs: 15_000,
  });
}

// --- QA H5: optional admin token ----------------------------------------------------

export async function getAuthStatus(): Promise<SecuritySummary> {
  return request<SecuritySummary>("/api/auth/status", { timeoutMs: 8_000, cache: "no-store" });
}

export async function signIn(token: string): Promise<SecuritySummary> {
  return request<SecuritySummary>("/api/auth/login", { ...json({ token }), timeoutMs: 10_000 });
}

export async function signOut(): Promise<SecuritySummary> {
  return request<SecuritySummary>("/api/auth/logout", { method: "POST", timeoutMs: 10_000 });
}

// --- v5: real mood boards ------------------------------------------------------

/** The backend answers 503 "Vision model not connected …" when no vision model is configured;
 *  it never invents an analysis. The store keeps only the message, so match on it. */
export function isVisionNotConnected(message: string | undefined): boolean {
  return !!message && /vision model not connected/i.test(message);
}
