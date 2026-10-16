"""Pydantic models mirroring CONTRACT.md exactly (camelCase on the wire)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# v5: there is no mock mode. A service is "connected" (configured and answering), "unreachable" (configured but
# failing its probe) or "not_configured". Results record which real path produced them (`route` / `generatedBy`).
ConnectionStatus = Literal["connected", "unreachable", "not_configured"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# --- core types --------------------------------------------------------------


class ServiceStatus(CamelModel):
    name: str
    status: ConnectionStatus  # v5 (replaces `mode`)
    healthy: bool  # == (status == "connected")
    detail: Optional[str] = None
    hint: Optional[str] = None  # v5: how to set it up / fix it (shown with not_configured / unreachable)
    fake: bool = False  # v5: the endpoint is the local test double (tests/fake_upstreams.py), NOT a real service
    # v2 (optional): what a probe actually saw
    model: Optional[str] = None
    host: Optional[str] = None
    latency_ms: Optional[float] = None
    gpu: Optional[str] = None  # v5: AMD_GPU_LABEL, or the device the diffusion server reports
    optional: bool = False  # not needed right now (an alternative path is connected); not counted as missing


class PoweredBy(CamelModel):
    """v5: which credits may be shown. True only for a real (not fake) connected service."""

    # A real model endpoint (vLLM / VLM / diffusion) is connected AND its hardware is verifiably AMD: AMD_GPU_LABEL
    # names an AMD device, or the diffusion server reports one. Never inferred from a model merely answering.
    amd: bool = False
    evolus: bool = False  # some Evolus building block is connected
    model_connected: bool = False  # a real model endpoint answers (whatever the hardware)
    hardware: Optional[str] = None  # the verified AMD device label, when `amd`


class HealthResponse(CamelModel):
    status: Literal["ok"] = "ok"
    services: list[ServiceStatus]
    powered_by: PoweredBy = Field(default_factory=PoweredBy)
    fake_upstreams: bool = False  # any configured endpoint is the local test double
    security: Optional["SecuritySummary"] = None  # QA H5: how state-changing requests are authorised


class SecuritySummary(CamelModel):
    """QA H5: ATELIER_ADMIN_TOKEN set -> every change needs the token (or the sign-in cookie); unset -> only this
    machine may change data ("local-only")."""

    admin_token_required: bool
    authenticated: bool = False
    mutations: Literal["admin-token", "local-only"]
    local_client: bool = False


class SourceImage(CamelModel):
    """v5: one image of a mood board, with the attribution its licence requires."""

    url: str
    title: str
    creator: str
    source_url: str
    license: str
    license_url: str
    modifications: Optional[str] = None
    ai_generated: Optional[bool] = None  # a brand's own AI-generated inspiration image, never a photograph


class AnalyzedBy(CamelModel):
    """v5: the live vision call that produced a TrendAnalysis (from its telemetry record)."""

    model: Optional[str] = None
    endpoint_host: Optional[str] = None
    gpu: Optional[str] = None
    latency_ms: Optional[float] = None
    call_id: Optional[str] = None
    # v6: how many images the model actually read (<= ATELIER_VISION_MAX_IMAGES) out of how many were submitted.
    images_analyzed: Optional[int] = None
    images_submitted: Optional[int] = None


class TrendAnalysis(CamelModel):
    id: str
    trend_name: str
    summary: str
    garment_type: str
    core_silhouettes: list[str]
    color_palette: list[str]
    key_fabrics: list[str]
    commercial_viability_score: int = Field(ge=1, le=100)
    source_image_urls: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    # v5: who really analysed it (from the vision call's telemetry) and the attributed images it looked at
    analyzed_by: Optional[AnalyzedBy] = None
    source_images: Optional[list[SourceImage]] = None


class Design(CamelModel):
    id: str
    trend_id: str
    parent_design_id: Optional[str] = None
    image_url: str
    prompt: str
    garment_type: str
    vibe: Optional[str] = None
    seed: int
    created_at: str = Field(default_factory=now_iso)
    # v2 (additive): set when the design came from /direct or a generated collection
    direction_id: Optional[str] = None
    collection_id: Optional[str] = None


class BomLine(CamelModel):
    material: str
    quantity: str
    target_cost_per_unit: float


class Citation(CamelModel):
    """v3: a knowledge-library source the agent used (brand book, supplier catalogue)."""

    source: str  # document title, e.g. "<brand> - Brand Book" (the brand's own document)
    snippet: Optional[str] = None  # the passage that was retrieved / cited
    library: Literal["evolus", "local"] = "evolus"  # evolus = Evolus knowledge library; local = the Brand workspace documents
    document_id: Optional[str] = None
    score: Optional[float] = None


class VoiceQuote(CamelModel):
    """v3: an exact excerpt of one customer record (see services/voice.py)."""

    record_id: str  # the record's id in its voice dataset, e.g. "r1077" (sample) or "row-12" (upload)
    field: str = "text"  # which record field the excerpt comes from: text | title | returnReason | fitFeedback
    text: str  # exact substring of that field
    truncated: bool = False  # the excerpt is a window of a longer sentence
    match_start: Optional[int] = None  # offsets of the matched phrase inside `text`
    match_end: Optional[int] = None
    rating: Optional[float] = None
    garment_class: Optional[str] = None


class CustomerEvidence(CamelModel):
    """v3: a customer-voice change applied to a tech pack, with the evidence behind it."""

    dataset_id: str
    dataset_name: str
    source: str  # "Your upload: reviews.csv" | "Sample: …"
    change_id: str
    title: str
    # The change as it was handed to the tech pack brief: the qualitative action (v5: no rule-of-thumb amounts)
    # plus the evidence. The brain turns it into concrete measurements / BOM lines when it writes the tech pack.
    tech_pack_change: str
    area: str
    count: int  # records that support the change (deterministic)
    base: int  # records it is measured against
    share: float  # 100 * count / base
    garment_class: Optional[str] = None
    record_ids: list[str] = Field(default_factory=list)
    quotes: list[VoiceQuote] = Field(default_factory=list)
    instruction: Optional[str] = None  # v5: concrete instruction drafted by the brain from the evidence
    instruction_by: Optional[str] = None  # brain route that drafted it


class TechPack(CamelModel):
    garment_name: str
    description: str
    bill_of_materials: list[BomLine]
    measurements: dict[str, str]
    target_supplier_region: str
    target_retail_price: float
    production_quantity: int
    # v2 (additive): the effective colourway as hex codes - the trend palette after any creative direction or
    # collection look re-coloured it. The PDF and dashboard read this instead of the trend's original palette.
    colorway: Optional[list[str]] = None
    # v3 (additive): knowledge-library sources the agent cited, and which path wrote this draft
    citations: Optional[list[Citation]] = None
    generated_by: Optional[str] = None  # "evolus-agent → AMD vLLM" | "direct vLLM"
    # v5: construction notes written by the brain (seams, finishes, closures); None when it gave none.
    construction_notes: Optional[list[str]] = None

    # v3 (additive): customer-voice changes applied to this tech pack, with their cited evidence.
    customer_evidence: Optional[list[CustomerEvidence]] = None
    # v4 (additive): the sizes offered on Shopify ("Size" option). None -> read a "size range" measurement, else
    # XS–XL (services/sizes.py).
    size_range: Optional[list[str]] = None
    # The brand currency every price on this tech pack is in (BOM target costs, retail) - from the Brand workspace
    # profile when the tech pack was written. None only on tech packs written before it was recorded.
    currency: Optional[str] = None


class SupplierEmail(CamelModel):
    supplier_name: str
    region: str
    to_email: str
    subject: str
    body: str
    status: Literal["drafted", "queued", "sent"] = "drafted"
    rfq_ref: Optional[str] = None  # v3: "ATL-run_ab12cd", quoted in the subject so replies can be matched
    # v4 (additive): the RFQ goes out in the mill's own language; the English version is kept alongside.
    language: Optional[str] = None  # ISO 639-1, e.g. "it" | "pt" | "en"
    language_name: Optional[str] = None  # "Italian"
    subject_english: Optional[str] = None  # only when language != "en"
    body_english: Optional[str] = None
    kind: Optional[Literal["rfq", "counter_offer"]] = None  # counter_offer = the negotiation email (v4)


class ShopifyProduct(CamelModel):
    product_id: str
    title: str
    handle: str
    url: str
    price: float
    status: Literal["preorder"] = "preorder"
    image_url: str
    # v3 (additive): where the listing really lives (v5: always a real store)
    source: Literal["shopify", "evolus"] = "shopify"  # evolus = created by the Evolus workflow
    admin_url: Optional[str] = None  # https://admin.shopify.com/store/<handle>/products/<id>
    shop_domain: Optional[str] = None  # "<store>.myshopify.com"
    short_url: Optional[str] = None  # what the stage shows under the QR code
    qr_url: Optional[str] = None  # GET /api/runs/{id}/storefront-qr.svg (encodes `url`)
    storefront_password: Optional[str] = None  # only when SHOPIFY_STOREFRONT_PASSWORD is set
    variant_id: Optional[str] = None
    published: Optional[bool] = None  # published to the Online Store sales channel
    # v4 (additive): one variant per size. `sizes` is None when the product has no Size option (single variant,
    # e.g. an Evolus-created listing) - then orders carry no size and the forecast uses the base size curve.
    sizes: Optional[list[str]] = None
    variant_ids: Optional[dict[str, str]] = None  # size -> gid://shopify/ProductVariant/…
    # Currencies: `price` is what the store lists, in the STORE's currency (`currency`, from the shop query; None when
    # it could not be read). `price_brand` is the tech pack's retail in the brand currency. When the two currencies
    # differ the listing price is the brand retail converted at the ECB reference rate (`fx_rate`, `fx_date`).
    currency: Optional[str] = None
    price_brand: Optional[float] = None
    brand_currency: Optional[str] = None
    fx_rate: Optional[float] = None  # store-currency units per 1 brand-currency unit
    fx_date: Optional[str] = None


StepKey = Literal["techpack", "supplier_outreach", "supplier_quotes", "shopify_preorder", "preorder_demand"]


class PipelineStep(CamelModel):
    key: StepKey
    label: str
    status: Literal["pending", "running", "done", "error"] = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    log: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    # v5: error states are honest and actionable - which service is missing / failing, how to set it up,
    # and whether POST /api/runs/{id}/retry can resume from this step.
    service: Optional[str] = None  # "brain" | "evolus_outreach" | "shopify" | …
    hint: Optional[str] = None
    retryable: bool = False
    telemetry: Optional[list["InferenceCall"]] = None  # v2: inference calls this step made
    route: Optional[str] = None  # v3: which brain ran: "evolus-agent → AMD vLLM" | "direct vLLM"
    # QA M3: an Evolus workflow was started (execution id) but its outcome is unknown (status poll failed). The
    # emails may have gone out: retrying needs an explicit confirmation (POST /retry {"confirmResend": true}).
    unknown_execution_id: Optional[str] = None


# --- v2: business loop (quotes -> recommendation -> pre-order demand -> PO) ------


class ScoreBreakdown(CamelModel):
    # 0-100 per criterion; v5: None when the quote does not state it (or the price could not be converted).
    # The total score is then the weighted mean over the criteria that are known.
    price: Optional[float] = None
    moq: Optional[float] = None
    lead_time: Optional[float] = None


class ExtractedField(CamelModel):
    """v3: one field the extractor read off the quote document."""

    name: str  # e.g. "unitPrice"
    value: str  # as printed / extracted
    confidence: Optional[float] = None  # 0..1 when the engine reports one
    # QA M10: True = the number is printed in the document text; False = it is not ("unverified"); None = no text
    # to check against (image / email without text). Only set on unitPrice / moq / leadTime.
    verified: Optional[bool] = None


class QuoteSource(CamelModel):
    """v3: where a quote came from and how it was read."""

    channel: Literal["upload", "email"]
    engine: str  # "evolus-extractor" | "amd-llm" | "amd-vlm" | "pdf-text-rules"
    engine_label: str  # human label, e.g. "Evolus document extractor"
    document_url: Optional[str] = None  # the stored PDF / image (served by the backend)
    filename: Optional[str] = None
    content_type: Optional[str] = None
    sender: Optional[str] = None  # email sender (email channel)
    confidence: Optional[float] = None  # overall 0..1
    fields: list[ExtractedField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extraction_id: Optional[str] = None  # Evolus extraction / workflow execution id


class SupplierQuote(CamelModel):
    """A quote read off a real document. v5: a field the document does not state stays None ("not stated")."""

    supplier_name: str
    region: str
    # Per finished garment in the brand currency (Guardrails.currency). None when the quote is in another
    # currency and no FX rate could be loaded - then only `unit_price_quoted` (in `currency`) is known.
    unit_price: Optional[float]
    moq: Optional[int] = None  # pieces per colour; None = not stated on the document
    lead_time_weeks: Optional[int] = None  # None = not stated
    sample_cost: Optional[float] = None  # brand currency; None = not stated (or not convertible)
    payment_terms: Optional[str] = None  # None = not stated
    note: str = ""  # the mill's own message, verbatim ("" when the document has none)
    received_at: str = Field(default_factory=now_iso)
    # v5: currency conversion (ECB daily reference rates). fx_rate converts `currency` -> brand currency.
    fx_rate: Optional[float] = None
    fx_source: Optional[str] = None  # "ECB euro foreign exchange reference rates"
    fx_date: Optional[str] = None  # the rates' reference date
    score: float = 0.0  # 0-100 weighted
    score_breakdown: ScoreBreakdown = Field(default_factory=lambda: ScoreBreakdown(price=0, moq=0, lead_time=0))
    # v3 (additive): real quote documents
    quote_number: Optional[str] = None
    valid_until: Optional[str] = None
    currency: Optional[str] = None  # currency as quoted; unit_price / sample_cost are in the brand currency
    source: Optional[QuoteSource] = None
    # v4 (additive): multilingual replies and revised quotes
    language: Optional[str] = None  # language of the document / note, ISO 639-1
    note_english: Optional[str] = None  # the note translated to English (absent when the note is English)
    note_translation: Optional[str] = None  # who translated: brain route | "phrasebook" | "untranslated"
    unit_price_quoted: Optional[float] = None  # unit price in `currency`, as printed
    sample_cost_quoted: Optional[float] = None  # v5: sample cost in `currency`, as printed
    revision: int = 0  # 0 = first quote; n = the mill's n-th revised quote (after a counter-offer)
    revises: Optional[str] = None  # quote number this one replaces
    # QA M10: extracted numbers that are not printed in the document text ("unitPrice" | "moq" | "leadTime").
    # An unverified price is left out of the automatic pick, unverified MOQ / lead time out of the score, until a
    # person confirms them (POST /api/runs/{id}/quotes/confirm).
    unverified_fields: list[str] = Field(default_factory=list)
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    duplicates: int = 0  # QA M9: identical copies received again (webhook replay / re-upload) and ignored


class QuoteRound(CamelModel):
    """v3: the RFQ round - who has replied, who we are still waiting for."""

    status: Literal["awaiting", "complete", "closed"] = "awaiting"  # closed = the CD stopped waiting
    rfq_ref: str  # "ATL-run_ab12cd"
    expected: int
    received: int = 0
    awaiting: list[str] = Field(default_factory=list)  # supplier names
    opened_at: str = Field(default_factory=now_iso)
    closed_at: Optional[str] = None


class SupplierRecommendation(CamelModel):
    supplier_name: str  # the agent's pick (deterministic weighted score)
    # Drafted by the brain from the quotes. v5: None when no brain is connected or it failed - then
    # `rationale_error` says why; the scores themselves are always shown.
    rationale: Optional[str] = None
    rationale_error: Optional[str] = None
    score: float
    weights: ScoreBreakdown
    selected_supplier_name: str  # == supplier_name unless the user overrode it
    overridden: bool = False
    citations: Optional[list[Citation]] = None  # v3: library sources behind the rationale
    generated_by: Optional[str] = None  # v3: which brain wrote the rationale


# --- v4: brand guardrails, human hand-off & audit trail ----------------------------

GuardrailRule = Literal["min_margin", "max_unit_cost", "max_lead_time", "max_moq", "certifications"]


class Guardrails(CamelModel):
    """The brand's hard limits for a supplier quote. v5: set by the brand in the Brand workspace (persisted);
    there are no invented defaults - a rule left empty is not checked, and `unset` lists those rules."""

    min_gross_margin_pct: Optional[float] = Field(default=None, ge=0, lt=100)  # (retail - unit) / retail
    # Absolute cap in the brand currency. Without one, a cap can be derived per run from the tech pack costing
    # + `cost_headroom_pct` - only if the brand set a headroom.
    max_unit_cost: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    cost_headroom_pct: Optional[float] = Field(default=None, ge=0, le=1000)  # derived cap = costing x (1 + headroom)
    max_lead_time_weeks: Optional[int] = Field(default=None, ge=1, le=104)  # None = not set (not checked)
    max_moq: Optional[int] = Field(default=None, ge=1, le=1_000_000)  # None = not set (not checked)
    required_certifications: list[str] = Field(default_factory=list)  # e.g. ["GOTS", "OEKO-TEX"]
    certifications_mode: Literal["all", "any"] = "all"
    currency: str = "USD"  # the brand currency; quotes are converted to it
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None  # "brand admin (UI)" | "creative director (UI)" | "not set"
    # v5
    reviewed_at: Optional[str] = None  # the brand looked at the guardrails (even if it left rules empty)
    unset: list[str] = Field(default_factory=list)  # rules not set, so not checked: min_margin, max_unit_cost, …


class GuardrailsPatch(CamelModel):
    """PUT /api/guardrails: any subset; send `null` to clear a rule (it is then not checked)."""

    min_gross_margin_pct: Optional[float] = Field(default=None, ge=0, lt=100)
    max_unit_cost: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    cost_headroom_pct: Optional[float] = Field(default=None, ge=0, le=1000)
    max_lead_time_weeks: Optional[int] = Field(default=None, ge=1, le=104)
    max_moq: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    required_certifications: Optional[list[str]] = Field(default=None, max_length=12)
    certifications_mode: Optional[Literal["all", "any"]] = None


class GuardrailCheck(CamelModel):
    rule: GuardrailRule
    label: str  # "Gross margin"
    ok: bool
    actual: str  # "58.2%"
    limit: str  # "≥ 65%"
    actual_value: Optional[float] = None
    limit_value: Optional[float] = None
    message: str  # plain language, with the numbers


class QuoteEvaluation(CamelModel):
    supplier_name: str
    ok: bool
    unit_price: Optional[float]  # brand currency; None = not convertible (see the quote's fx fields)
    margin_pct: Optional[float] = None
    checks: list[GuardrailCheck] = Field(default_factory=list)
    quote_number: Optional[str] = None
    revision: int = 0

    @property
    def breaches(self) -> list[GuardrailCheck]:
        return [c for c in self.checks if not c.ok]


class GuardrailReport(CamelModel):
    """Every quote on the run measured against the guardrails in force (deterministic, no model)."""

    guardrails: Guardrails  # the limits used (with the derived unit-cost cap filled in)
    max_unit_cost_derived: bool = False
    costed_unit_cost: Optional[float] = None  # the tech pack's BOM unit cost the derived cap is based on
    retail_price: Optional[float] = None
    evaluations: list[QuoteEvaluation] = Field(default_factory=list)
    selected_supplier_name: Optional[str] = None
    selected_ok: Optional[bool] = None
    evaluated_at: str = Field(default_factory=now_iso)


class DecisionOption(CamelModel):
    kind: Literal["approve", "negotiate", "switch"]
    label: str  # "Switch to <supplier>"
    detail: str  # "71% margin · 7 wks · MOQ 600"
    supplier_name: Optional[str] = None


class CounterOffer(CamelModel):
    """The negotiation email to the mill (in its language, English alongside) and the maths behind the ask."""

    supplier_name: str
    region: str = ""
    to_email: str
    language: str = "en"
    language_name: str = "English"
    subject: str
    body: str
    subject_english: str
    body_english: str
    rfq_ref: str
    quote_number: Optional[str] = None
    currency: str = "USD"  # the currency the mill quoted in (the ask is made in it)
    brand_currency: Optional[str] = None  # the currency of quoted_unit_price / target_unit_price
    quoted_unit_price: Optional[float] = None  # brand currency (None = not convertible)
    quoted_unit_price_local: Optional[float] = None  # in `currency`
    target_unit_price: Optional[float] = None  # brand currency - the highest price that keeps every guardrail
    target_unit_price_local: Optional[float] = None  # in `currency`
    reduction_pct: float  # 100 * (quoted - target) / quoted
    math: list[str] = Field(default_factory=list)  # the deterministic calculation, line by line
    generated_by: str  # brain route that drafted the wording (v5: there is no template)
    edited: bool = False  # the human changed the text before sending
    # QA M2/M3: "sending" while the workflow runs (a second send is refused); "unknown" when the workflow started
    # but its outcome could not be read (re-sending needs an explicit confirmation)
    status: Literal["draft", "sending", "queued", "sent", "unknown"] = "draft"
    sent_at: Optional[str] = None
    sent_via: Optional[str] = None  # "Evolus workflow <id>"
    send_error: Optional[str] = None  # v5: the last send attempt failed (the draft is kept)
    execution_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class AuditEntry(CamelModel):
    at: str = Field(default_factory=now_iso)
    actor: Literal["agent", "human", "system"]
    action: str  # guardrail_breach | handoff | approved_override | switched | counter_offer_drafted |
    # counter_offer_sent | revised_quote | resolved | guardrails_updated | supplier_override
    summary: str  # one plain-language line
    supplier_name: Optional[str] = None
    guardrail: Optional[str] = None  # rule id(s), comma-separated
    values: dict[str, str] = Field(default_factory=dict)  # the numbers behind it
    note: Optional[str] = None  # the human's note


class Decision(CamelModel):
    """v4: the agent stopped and handed the case to a person. The pipeline does not continue until resolved."""

    id: str
    status: Literal["pending", "negotiating", "resolved"] = "pending"
    supplier_name: str  # the quote in question (the agent's selected pick)
    headline: str  # "<supplier>'s quote breaks a guardrail"
    explanation: str  # plain language with the numbers and the options
    breaches: list[GuardrailCheck] = Field(default_factory=list)
    all_quotes_breach: bool = False
    options: list[DecisionOption] = Field(default_factory=list)
    counter_offer: Optional[CounterOffer] = None
    negotiation_rounds: int = 0  # counter-offers sent
    # approved = override recorded · switched = another mill · revised = a revised quote came back inside the
    # guardrails · guardrails_changed / techpack_changed = the limits or the tech pack (retail) were edited
    outcome: Optional[Literal["approved", "switched", "revised", "guardrails_changed", "techpack_changed"]] = None
    resolved_supplier_name: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class DecisionApproveRequest(CamelModel):
    note: Optional[str] = Field(default=None, max_length=500)
    actor: Optional[str] = Field(default=None, max_length=80)


class DecisionSwitchRequest(CamelModel):
    supplier_name: str = Field(min_length=1)
    note: Optional[str] = Field(default=None, max_length=500)
    actor: Optional[str] = Field(default=None, max_length=80)


class CounterOfferSendRequest(CamelModel):
    subject: Optional[str] = Field(default=None, min_length=1, max_length=300)
    body: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    actor: Optional[str] = Field(default=None, max_length=80)


class DemandPoint(CamelModel):
    hour: float
    orders: int


class PurchaseOrder(CamelModel):
    """v5: a real PO. Numbered from a persisted per-brand sequence and sent to the mill's address from the supplier
    directory through an Evolus workflow. Without Evolus it stays a draft ("draft - not sent"), never "issued"."""

    po_number: str  # "PO-00042"
    supplier_name: str
    region: str
    to_email: Optional[str] = None  # from the supplier directory
    quantity: int
    currency: str  # the currency the mill quoted in (the PO is placed in it)
    unit_price: float  # in `currency`, as quoted
    total: float  # quantity x unit_price, in `currency`
    unit_price_brand: Optional[float] = None  # brand-currency equivalent when an FX rate was available
    brand_currency: Optional[str] = None  # the currency of unit_price_brand / total_brand
    total_brand: Optional[float] = None
    lead_time_weeks: Optional[int] = None  # None = the quote did not state one
    quote_number: Optional[str] = None
    rfq_ref: Optional[str] = None
    # QA M3: "unknown" = the Evolus workflow started (executionId) but its outcome could not be read - check Evolus;
    # re-sending needs ?confirm=resend
    status: Literal["draft", "sending", "queued", "sent", "failed", "unknown"] = "draft"
    created_at: str = Field(default_factory=now_iso)
    sent_at: Optional[str] = None
    sent_via: Optional[str] = None  # "Evolus workflow <id>"
    execution_id: Optional[str] = None
    send_error: Optional[str] = None  # why the last send failed / could not be attempted
    hint: Optional[str] = None  # setup hint when Evolus is not connected


class PreorderLine(CamelModel):
    """v4: one line item of this product in a real order (an order with M and L has two)."""

    size: Optional[str] = None  # from the variant's Size option / variant title; None when unknown
    quantity: int
    amount: float  # after discounts, shop currency


class PreorderOrder(CamelModel):
    """v3: one real Shopify order containing the product. Privacy: first name + city only."""

    order_id: str  # gid://shopify/Order/…
    name: str  # "#1001"
    created_at: str
    units: int
    amount: float  # this product's lines, after discounts, shop currency
    currency: str = "USD"
    first_name: Optional[str] = None
    city: Optional[str] = None
    test: bool = False  # Bogus Gateway / test-mode order - always labelled "test order" in the UI
    via: Literal["poll", "webhook"] = "poll"
    lines: list[PreorderLine] = Field(default_factory=list)  # v4: this product's line items, with sizes


class DemandOrderEvent(CamelModel):
    """v3: one product line from a real order, for the forecast (every order, not just the recent feed)."""

    timestamp: str
    quantity: int
    size: Optional[str] = None
    unit_price: Optional[float] = None
    order_id: Optional[str] = None  # v4: one event per line item; lines of one order share this id


class PreorderDemand(CamelModel):
    """Real Shopify orders for the pre-order product (v5: there is no simulated demand)."""

    status: Literal["collecting", "unlocked", "expired"] = "collecting"
    threshold: int  # what `units` must reach (the stage threshold when one is set)
    threshold_basis: Literal["productionQuantity", "moq", "stage"]
    orders: int = 0
    revenue: float = 0.0
    window_hours: int = 336
    elapsed_hours: float = 0.0
    hours_left: float = 336.0
    series: list[DemandPoint] = Field(default_factory=list)  # cumulative units by hour since launch
    unlocked_at_hour: Optional[float] = None
    purchase_order: Optional[PurchaseOrder] = None
    source: Literal["shopify"] = "shopify"
    units: int = 0  # units of this product across `orders`
    production_threshold: Optional[int] = None  # max(productionQuantity, chosen MOQ) - the PO quantity
    production_threshold_basis: Optional[Literal["productionQuantity", "moq"]] = None
    stage_threshold: Optional[int] = None  # DEMAND_STAGE_THRESHOLD when it is in effect
    currency: str = "USD"
    recent_orders: list[PreorderOrder] = Field(default_factory=list)  # newest first, at most 12
    order_events: list[DemandOrderEvent] = Field(default_factory=list)  # every order, oldest first (forecast input)
    launched_at: Optional[str] = None  # when the real pre-order went live
    test_orders: int = 0  # how many of `orders` are test-mode orders (always labelled "test order")
    test_units: int = 0  # v5: units in those test orders
    tracking: Optional[str] = None  # e.g. "Admin API poll every 4s + orders/create webhook"
    last_checked_at: Optional[str] = None
    tracking_error: Optional[str] = None  # last poll error (cleared on the next good poll)


class PipelineRun(CamelModel):
    id: str
    design_id: str
    status: Literal["running", "completed", "failed"] = "running"
    steps: list[PipelineStep]
    tech_pack: Optional[TechPack] = None
    supplier_emails: Optional[list[SupplierEmail]] = None
    shopify_product: Optional[ShopifyProduct] = None
    created_at: str = Field(default_factory=now_iso)
    # v2
    original_tech_pack: Optional[TechPack] = None  # the agent's first draft, for "vs original" deltas
    tech_pack_revision: int = 0  # bumped on every PATCH /techpack
    quotes: Optional[list[SupplierQuote]] = None
    recommendation: Optional[SupplierRecommendation] = None
    demand: Optional[PreorderDemand] = None
    quote_round: Optional[QuoteRound] = None  # v3
    style_number: Optional[str] = None  # v5: from the persisted per-brand style sequence, assigned with the tech pack
    # v4: guardrails, human hand-off and the audit trail
    guardrail_report: Optional[GuardrailReport] = None
    decision: Optional[Decision] = None  # status pending/negotiating = the run is awaiting a human decision
    audit: list[AuditEntry] = Field(default_factory=list)


# --- request / response wrappers ----------------------------------------------


class PresetSummary(CamelModel):
    """A preset mood board (v5: real, openly licensed photos, or the pilot brand's own AI-generated inspiration; `name` is the board's factual title)."""

    id: str
    name: str
    thumbnail_url: str  # the board's first image
    # v5
    credit: Optional[str] = None  # e.g. "Photos: Masaki-H · CC BY 2.0 · via Wikimedia Commons"
    images: list[SourceImage] = Field(default_factory=list)
    ai_generated: Optional[bool] = None  # the pilot brand's own AI-generated inspiration board (labelled in the UI)


class AnalyzeJsonRequest(CamelModel):
    image_urls: Optional[list[str]] = None
    preset: Optional[str] = None


MAX_VIBE_CHARS = 500  # LOW: creative-direction text is a prompt fragment, not a document


class GenerateRequest(CamelModel):
    trend_id: str = Field(max_length=64)
    vibe: Optional[str] = Field(default=None, max_length=MAX_VIBE_CHARS)
    count: int = Field(default=4, ge=1, le=8)


class RefineRequest(CamelModel):
    vibe: str = Field(min_length=1, max_length=MAX_VIBE_CHARS)
    count: int = Field(default=4, ge=1, le=8)


class DesignsResponse(CamelModel):
    designs: list[Design]


class ApproveRequest(CamelModel):
    production_quantity: Optional[int] = Field(default=None, ge=1, le=1_000_000)


class ApproveResponse(CamelModel):
    run_id: str
    # QA M2: true when this approve returned the run already active for the design (double click / retried request /
    # same Idempotency-Key) instead of starting a second one that would e-mail the suppliers again
    existing: bool = False


# --- v2: creative direction & collections -------------------------------------


class PaletteShift(CamelModel):
    before: list[str]
    after: list[str]
    note: str  # e.g. "deepened toward ink"


class CreativeDirection(CamelModel):
    id: str
    design_id: str  # the design the direction was applied to
    instruction: str  # what the creative director typed or said
    interpretation: str  # one sentence the agent "says back"
    prompt_additions: list[str] = Field(default_factory=list)
    prompt_removals: list[str] = Field(default_factory=list)
    palette_shift: Optional[PaletteShift] = None
    silhouette_changes: list[str] = Field(default_factory=list)
    tech_pack_hints: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    fabrics_after: Optional[list[str]] = None  # v5: fabric swaps the brain made (shell first)
    created_at: str = Field(default_factory=now_iso)
    generated_by: Optional[str] = None  # v3: "evolus-agent → AMD vLLM" | "direct vLLM"
    citations: Optional[list[Citation]] = None  # v3: brand-book passages the interpreter followed


class DirectRequest(CamelModel):
    instruction: str = Field(min_length=1, max_length=500)
    count: int = Field(default=4, ge=1, le=8)


class DirectResponse(CamelModel):
    direction: CreativeDirection
    designs: list[Design]


class CollectionLook(CamelModel):
    design_id: str
    title: str  # e.g. "Look 02 - Wide-leg trousers"
    caption: str


class Collection(CamelModel):
    id: str
    trend_id: str
    name: str
    story: str
    designs: list[Design]
    looks: list[CollectionLook]
    generated_by: Optional[str] = None  # v5: brain route that planned it
    created_at: str = Field(default_factory=now_iso)


class CollectionRequest(CamelModel):
    trend_id: str
    size: int = Field(default=4, ge=3, le=5)


# --- v2: live infrastructure & inference stats -----------------------------------

TelemetryService = Literal["llm", "vision", "diffusion", "evolus"]


class InferenceCall(CamelModel):
    """One real upstream call, measured (v5: there are no simulated calls)."""

    id: str
    service: TelemetryService
    purpose: str  # e.g. "techpack", "rfq_emails", "trend_analysis", "design_render", "outreach"
    ok: bool = True
    fake: bool = False  # v5: the endpoint is the local test double, not a real service
    model: Optional[str] = None
    endpoint_host: Optional[str] = None
    gpu: Optional[str] = None  # from AMD_GPU_LABEL (or the diffusion server's reported device); never guessed
    started_at: str = Field(default_factory=now_iso)
    latency_ms: float = 0.0
    ttft_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_per_sec: Optional[float] = None  # completion tokens / decode time (after first token if streamed)
    images: Optional[int] = None
    images_per_sec: Optional[float] = None
    server_ms: Optional[float] = None  # compute time reported by the upstream server, if any
    attempt: int = 1
    error: Optional[str] = None
    detail: Optional[str] = None
    # v3: which path produced this call - "evolus-agent → AMD vLLM" | "direct vLLM"
    # (brain calls), or "evolus-extractor" | "evolus-library" | "amd-llm" | "pdf-text-rules" (quotes / RAG)
    route: Optional[str] = None


class ServiceTelemetry(CamelModel):
    """Aggregates over the ring buffer for one service (measured calls only)."""

    service: TelemetryService
    calls: int
    errors: int
    avg_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    avg_ttft_ms: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    avg_tokens_per_sec: Optional[float] = None
    peak_tokens_per_sec: Optional[float] = None
    images: int = 0
    avg_images_per_sec: Optional[float] = None
    last_model: Optional[str] = None
    last_endpoint_host: Optional[str] = None
    gpu: Optional[str] = None
    last_at: Optional[str] = None


class TelemetryResponse(CamelModel):
    gpu_label: Optional[str] = None  # AMD_GPU_LABEL as configured; None when unset
    calls: list[InferenceCall]  # newest first
    services: list[ServiceTelemetry]


PipelineStep.model_rebuild()
HealthResponse.model_rebuild()


# --- v2 request / response wrappers ----------------------------------------------


class TechPackPatch(CamelModel):
    garment_name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    bill_of_materials: Optional[list[BomLine]] = Field(default=None, min_length=1)
    measurements: Optional[dict[str, str]] = None
    target_supplier_region: Optional[str] = None
    target_retail_price: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    production_quantity: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    colorway: Optional[list[str]] = Field(default=None, min_length=1, max_length=8)
    size_range: Optional[list[str]] = Field(default=None, min_length=1, max_length=12)  # v4


class SelectSupplierRequest(CamelModel):
    supplier_name: str = Field(min_length=1)


class MaterialOption(CamelModel):
    material: str
    target_cost_per_unit: float
    note: str
    tag: Optional[str] = None  # e.g. "recycled", "organic", "premium"
    original: bool = False  # the agent's original choice for this line


class BomAlternatives(CamelModel):
    index: int  # BOM line index in the tech pack
    family: str
    options: list[MaterialOption]


class AlternativesResponse(CamelModel):
    lines: list[BomAlternatives]
    # v5: the brand's material price list the alternatives were costed from ("price list dated …")
    price_list_dated: Optional[str] = None
    price_list_source: Optional[str] = None
