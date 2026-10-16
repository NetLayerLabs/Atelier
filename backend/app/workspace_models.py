"""v5: the Brand workspace - everything brand-specific, provided by the merchant (CONTRACT.md "v5").

Nothing here has a brand-specific default: a field is empty until the brand imports or types it. The only
pre-filled values are the supplier scoring weights, shown in the UI as "default weighting" until edited.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from .models import CamelModel, Guardrails

ImportKind = Literal["suppliers", "prices", "sizes", "sales"]


class Provenance(CamelModel):
    """Where a piece of workspace data came from: "Imported from suppliers.csv on 13 Oct 2026"."""

    source: Literal["csv", "xlsx", "form", "upload"]
    filename: Optional[str] = None
    imported_at: str
    rows: Optional[int] = None
    label: str  # human sentence, ready to show


class ColourStandard(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    code: Optional[str] = Field(default=None, max_length=40)  # Pantone / TCX - only if the brand provides it


class PriceArchitecture(CamelModel):
    """Retail price rule: a multiple of landed cost (e.g. 4.0) or a target gross margin % (e.g. 72)."""

    mode: Literal["retail_multiple", "target_margin"]
    value: float = Field(gt=0, le=1000)


class SizePoint(CamelModel):
    """One point of measure of a size block (imported from CSV)."""

    block: str  # e.g. "Women's tops"
    point_of_measure: str  # e.g. "Chest width"
    size: str  # e.g. "M"
    value: float
    unit: str  # cm | in
    tolerance: Optional[float] = None


class BrandProfileInput(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    target_markets: list[str] = Field(default_factory=list, max_length=40)
    voice: str = Field(default="", max_length=4000)  # persona / tone-of-voice notes used in prompts
    default_size_range: list[str] = Field(default_factory=list, max_length=30)
    colours: list[ColourStandard] = Field(default_factory=list, max_length=120)
    price_architecture: Optional[PriceArchitecture] = None
    delivery_promise_weeks: Optional[int] = Field(default=None, ge=1, le=104)
    preorder_window_days: Optional[int] = Field(default=None, ge=1, le=365)


class BrandProfile(BrandProfileInput):
    provenance: Optional[Provenance] = None
    updated_at: Optional[str] = None


class SupplierCertification(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    expires_on: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    document_id: Optional[str] = None  # an uploaded certificate (GET /api/workspace/documents/{id}/file)
    expired: bool = False  # computed on read


class SupplierInput(CamelModel):
    name: str = Field(min_length=1, max_length=160)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")  # ISO 639-1 correspondence language
    emails: list[str] = Field(min_length=1, max_length=10)
    categories: list[str] = Field(default_factory=list, max_length=40)  # "denim", "knitwear", "CMT" …
    capabilities: list[str] = Field(default_factory=list, max_length=40)
    certifications: list[SupplierCertification] = Field(default_factory=list, max_length=40)
    moq: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    lead_time_weeks: Optional[int] = Field(default=None, ge=1, le=104)
    payment_terms: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    # Pilot safety valve: RFQs and counter-offers go to this address instead of the supplier's own contacts.
    rfq_email_override: Optional[str] = Field(default=None, max_length=200)


class Supplier(SupplierInput):
    id: str
    provenance: Optional[Provenance] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    rfq_recipient: str = ""  # where an RFQ to this supplier is really sent (override, else first contact)
    maker: bool = False  # cut-make-trim / full-package factory (category "CMT", "cut-make-trim", "full package")


class MaterialPrice(CamelModel):
    material: str
    category: str
    unit: str  # m | yd | kg | pc | set …
    price: float = Field(gt=0)
    currency: str
    supplier: str = ""
    valid_from: str  # YYYY-MM-DD


class PriceList(CamelModel):
    items: list[MaterialPrice] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    dated: Optional[str] = None  # the latest valid-from date on the list: "price list dated …"


class SalesRecord(CamelModel):
    style: str
    launch_date: str  # YYYY-MM-DD
    week: int = Field(ge=1)  # week since launch, 1-based
    units: int = Field(ge=0)
    size: Optional[str] = None


class SalesHistorySummary(CamelModel):
    rows: int = 0
    styles: int = 0
    provenance: Optional[Provenance] = None


class ScoringWeights(CamelModel):
    """Supplier scoring (sums to 1). `isDefault` = Atelier's default weighting, not set by the brand."""

    price: float = Field(ge=0, le=1)
    moq: float = Field(ge=0, le=1)
    lead_time: float = Field(ge=0, le=1)
    is_default: bool = False
    label: str = ""
    updated_at: Optional[str] = None


class ScoringWeightsInput(CamelModel):
    price: float = Field(ge=0, le=100)
    moq: float = Field(ge=0, le=100)
    lead_time: float = Field(ge=0, le=100)


class EvolusUpload(CamelModel):
    status: Literal["uploaded", "not_configured", "failed"]
    document_id: Optional[str] = None
    library_id: Optional[str] = None
    detail: Optional[str] = None


class BrandDocument(CamelModel):
    id: str
    kind: Literal["brand_book", "certificate"]
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    chars: int = 0  # extracted text length (local grounding)
    passages: int = 0
    supplier_id: Optional[str] = None
    certification: Optional[str] = None
    evolus: Optional[EvolusUpload] = None
    url: str = ""


class SectionStatus(CamelModel):
    key: Literal["profile", "brand_book", "suppliers", "prices", "guardrails", "sales"]
    label: str
    required: bool
    done: bool
    detail: str  # "3 suppliers · contacts confirmed" / "not set"
    provenance: Optional[Provenance] = None


class WorkspaceStatus(CamelModel):
    ready: bool  # the studio can approve designs (profile + ≥1 confirmed supplier + guardrails reviewed)
    missing: list[str] = Field(default_factory=list)  # plain-language list of what blocks approval
    sections: list[SectionStatus] = Field(default_factory=list)


class SupplierConfirmation(CamelModel):
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    suppliers: int = 0


class Workspace(CamelModel):
    profile: Optional[BrandProfile] = None
    size_points: list[SizePoint] = Field(default_factory=list)
    size_provenance: Optional[Provenance] = None
    suppliers: list[Supplier] = Field(default_factory=list)
    supplier_confirmation: SupplierConfirmation = Field(default_factory=SupplierConfirmation)
    price_list: PriceList = Field(default_factory=PriceList)
    guardrails: Guardrails
    scoring: ScoringWeights
    documents: list[BrandDocument] = Field(default_factory=list)
    sales: SalesHistorySummary = Field(default_factory=SalesHistorySummary)
    status: WorkspaceStatus


class ImportIssue(CamelModel):
    row: int  # 1-based data row (the header is row 0); 0 = the whole file
    field: Optional[str] = None
    message: str
    level: Literal["error", "warning"] = "error"


class ImportPreview(CamelModel):
    kind: ImportKind
    filename: str
    columns: list[str] = Field(default_factory=list)  # recognised columns, in file order
    ignored_columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)  # parsed rows (camelCase), for the preview table
    valid_rows: int = 0
    issues: list[ImportIssue] = Field(default_factory=list)
    committed: bool = False
    mode: Literal["replace", "append"] = "replace"
    provenance: Optional[Provenance] = None


class ConfirmSuppliersRequest(CamelModel):
    confirm: bool
    actor: str = Field(default="brand admin (UI)", max_length=80)
