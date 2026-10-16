// v5: the Brand workspace - types and API client (CONTRACT.md "v5").
import { API_BASE, ApiError, notifyAuthRequired, type Guardrails } from "./api";

export interface Provenance {
  source: "csv" | "xlsx" | "form" | "upload";
  filename?: string;
  importedAt: string;
  rows?: number;
  /** Ready to show: "Imported from suppliers.csv on 13 Oct 2026 (12 rows)". */
  label: string;
}

export interface ColourStandard {
  name: string;
  hex: string;
  /** Pantone / TCX - only if the brand provides it. */
  code?: string;
}

export interface PriceArchitecture {
  mode: "retail_multiple" | "target_margin";
  value: number;
}

export interface BrandProfileInput {
  name: string;
  currency: string;
  targetMarkets: string[];
  voice: string;
  defaultSizeRange: string[];
  colours: ColourStandard[];
  priceArchitecture?: PriceArchitecture | null;
  deliveryPromiseWeeks?: number | null;
  preorderWindowDays?: number | null;
}

export interface BrandProfile extends BrandProfileInput {
  provenance?: Provenance;
  updatedAt?: string;
}

export interface SizePoint {
  block: string;
  pointOfMeasure: string;
  size: string;
  value: number;
  unit: string;
  tolerance?: number;
}

export interface SupplierCertification {
  name: string;
  expiresOn?: string | null;
  documentId?: string | null;
  expired?: boolean;
}

export interface SupplierInput {
  name: string;
  city: string;
  country: string;
  language: string;
  emails: string[];
  categories: string[];
  capabilities: string[];
  certifications: SupplierCertification[];
  moq?: number | null;
  leadTimeWeeks?: number | null;
  paymentTerms: string;
  notes: string;
  rfqEmailOverride?: string | null;
}

export interface Supplier extends SupplierInput {
  id: string;
  provenance?: Provenance;
  createdAt?: string;
  updatedAt?: string;
  /** Where an RFQ is really sent: the override, else the first contact. */
  rfqRecipient: string;
  /** Cut-make-trim / full-package maker (category "CMT"). */
  maker: boolean;
}

export interface MaterialPrice {
  material: string;
  category: string;
  unit: string;
  price: number;
  currency: string;
  supplier: string;
  validFrom: string;
}

export interface PriceList {
  items: MaterialPrice[];
  provenance?: Provenance;
  dated?: string;
}

export interface ScoringWeights {
  price: number;
  moq: number;
  leadTime: number;
  isDefault: boolean;
  label: string;
  updatedAt?: string;
}

export interface EvolusUpload {
  status: "uploaded" | "not_configured" | "failed";
  documentId?: string;
  libraryId?: string;
  detail?: string;
}

export interface BrandDocument {
  id: string;
  kind: "brand_book" | "certificate";
  filename: string;
  contentType: string;
  size: number;
  uploadedAt: string;
  chars: number;
  passages: number;
  supplierId?: string;
  certification?: string;
  evolus?: EvolusUpload;
  url: string;
}

export type SectionKey = "profile" | "brand_book" | "suppliers" | "prices" | "guardrails" | "sales";

export interface SectionStatus {
  key: SectionKey;
  label: string;
  required: boolean;
  done: boolean;
  detail: string;
  provenance?: Provenance;
}

export interface WorkspaceStatus {
  ready: boolean;
  missing: string[];
  sections: SectionStatus[];
}

export interface SupplierConfirmation {
  confirmedAt?: string;
  confirmedBy?: string;
  suppliers: number;
}

export interface Workspace {
  profile?: BrandProfile;
  sizePoints: SizePoint[];
  sizeProvenance?: Provenance;
  suppliers: Supplier[];
  supplierConfirmation: SupplierConfirmation;
  priceList: PriceList;
  guardrails: Guardrails;
  scoring: ScoringWeights;
  documents: BrandDocument[];
  sales: { rows: number; styles: number; provenance?: Provenance };
  status: WorkspaceStatus;
}

export type ImportKind = "suppliers" | "prices" | "sizes" | "sales";

export interface ImportIssue {
  /** 1-based data row; 0 = the whole file. */
  row: number;
  field?: string;
  message: string;
  level: "error" | "warning";
}

export interface ImportPreview {
  kind: ImportKind;
  filename: string;
  columns: string[];
  ignoredColumns: string[];
  rows: Record<string, unknown>[];
  validRows: number;
  issues: ImportIssue[];
  committed: boolean;
  mode: "replace" | "append";
  provenance?: Provenance;
}

// --------------------------------------------------------------------------- client

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
      credentials: "include", // QA H5: the sign-in cookie when ATELIER_ADMIN_TOKEN is set
      signal: controller.signal,
      headers: { Accept: "application/json", ...(init.headers || {}) },
    });
  } catch {
    throw new ApiError(`Can't reach the Atelier backend at ${API_BASE}.`, 0);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`.trim();
    try {
      const body = (await res.json()) as { detail?: unknown };
      notifyAuthRequired(res.status, body);
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getWorkspace = () => call<Workspace>("/api/workspace");
export const getWorkspaceStatus = () => call<WorkspaceStatus>("/api/workspace/status", {}, 8_000);
export const putProfile = (p: BrandProfileInput) => call<BrandProfile>("/api/workspace/profile", jsonInit("PUT", p));

export function importTable(
  kind: ImportKind,
  file: File,
  opts: { commit: boolean; mode?: "replace" | "append" },
): Promise<ImportPreview> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("commit", String(opts.commit));
  form.append("mode", opts.mode ?? "replace");
  return call<ImportPreview>(`/api/workspace/${kind}/import`, { method: "POST", body: form }, 120_000);
}

export const templateUrl = (kind: ImportKind) => `${API_BASE}/api/workspace/templates/${kind}.csv`;

export const createSupplier = (s: SupplierInput) => call<Supplier>("/api/workspace/suppliers", jsonInit("POST", s));
export const updateSupplier = (id: string, s: SupplierInput) =>
  call<Supplier>(`/api/workspace/suppliers/${encodeURIComponent(id)}`, jsonInit("PUT", s));
export const deleteSupplier = (id: string) =>
  call<void>(`/api/workspace/suppliers/${encodeURIComponent(id)}`, { method: "DELETE" });
export const confirmSuppliers = () =>
  call<SupplierConfirmation>("/api/workspace/suppliers/confirm", jsonInit("POST", { confirm: true }));

export function uploadCertificate(supplierId: string, certification: string, file: File): Promise<Supplier> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("certification", certification);
  return call<Supplier>(`/api/workspace/suppliers/${encodeURIComponent(supplierId)}/certificates`, {
    method: "POST",
    body: form,
  });
}

export function uploadBrandDocument(file: File): Promise<BrandDocument> {
  const form = new FormData();
  form.append("file", file, file.name);
  return call<BrandDocument>("/api/workspace/documents", { method: "POST", body: form }, 180_000);
}
export const deleteBrandDocument = (id: string) =>
  call<void>(`/api/workspace/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
export const documentUrl = (id: string) => `${API_BASE}/api/workspace/documents/${encodeURIComponent(id)}/file`;

export const clearPrices = () => call<PriceList>("/api/workspace/prices", { method: "DELETE" });
export const clearSales = () => call<unknown>("/api/workspace/sales", { method: "DELETE" });

export const putScoring = (w: { price: number; moq: number; leadTime: number }) =>
  call<ScoringWeights>("/api/workspace/scoring", jsonInit("PUT", w));
export const resetScoring = () => call<ScoringWeights>("/api/workspace/scoring/reset", { method: "POST" });

export const reviewGuardrails = () => call<Guardrails>("/api/guardrails/review", { method: "POST" });

export const LANGUAGES: Record<string, string> = {
  en: "English",
  it: "Italian",
  pt: "Portuguese",
  es: "Spanish",
  fr: "French",
  de: "German",
  nl: "Dutch",
  tr: "Turkish",
  zh: "Chinese",
  ja: "Japanese",
  hi: "Hindi",
};

/** RFQ / counter-offer templates exist in these languages; others get English. */
export const RFQ_LANGUAGES = new Set(["en", "it", "pt"]);

export function fmtDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
