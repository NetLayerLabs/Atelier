"""v3: Customer voice - the merchant's own reviews, returns and support tickets drive the tech pack.

Pipeline (see CONTRACT.md, "v3 - Customer voice"):

1. Ingest a CSV/TSV (column auto-detection for review text/body/comment, rating, title, product/class, size,
   fit feedback, return reason, date, id) or a PDF (pypdf text split into records). Records keep the
   merchant's own ids where there is an id column, else the CSV row number, so every citation is traceable.
2. Analyse deterministically with the apparel taxonomy in `voice_taxonomy` (keyword/phrase/proximity rules,
   negation, hedging, rating-aware polarity): per-theme counts and shares, per garment class, the mean rating
   of the reviews that mention the theme, and representative quotes that are exact substrings of real records.
3. Map problem themes to the change they call for, stated QUALITATIVELY (v5: no rule-of-thumb amounts and no
   invented BOM costs), each carrying its evidence: "Add shoulder & bicep ease - 23 of 200 reviews for Jackets
   mention tight shoulders".
4. When a brain is connected (Evolus agent -> AMD vLLM, or direct vLLM), it phrases the summary, a one-line
   rationale per change (numbers must come from the facts) and the concrete tech-pack instruction per change from
   the evidence - labelled with the route that wrote it. Without a brain the qualitative action stands.
5. The merchant applies selected changes to a design (or to a trend: every design from it inherits them).
   At approval the pipeline folds them into the design's creative-direction hints; the brain writes them into the
   tech pack's measurements / BOM, and `finalize_techpack` attaches `customerEvidence`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import statistics
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field

from ..models import CamelModel, CustomerEvidence, Design, TechPack, VoiceQuote, now_iso
from ..store import DesignMeta, new_id, store
from .colors import garment_kind
from .voice_taxonomy import GROUP_LABELS, THEME_BY_ID, THEMES, find_mentions

log = logging.getLogger("atelier.voice")

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "voice_samples"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 25_000
MAX_DATASETS = 40
MAX_TEXT_CHARS = 5_000  # per field; longer cells are cut (the cut is what gets analysed and quoted)


# --------------------------------------------------------------------------- API models


class VoiceSource(CamelModel):
    kind: Literal["upload", "sample"]
    filename: Optional[str] = None
    dataset_key: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    licence: Optional[str] = None
    attribution: Optional[str] = None


class VoiceClassCount(CamelModel):
    garment_class: str
    count: int  # records of this class that mention the theme (or, at dataset level, records of the class)
    total: int
    share: float


class VoiceTheme(CamelModel):
    id: str
    group: str
    group_label: str
    name: str
    kind: Literal["problem", "praise", "rating"]
    polarity: Literal["negative", "positive", "mixed"]
    count: int  # records mentioning the theme (after negation)
    share: float  # 100 * count / analysedCount
    negative_count: int
    positive_count: int
    neutral_count: int
    avg_rating: Optional[float] = None  # mean rating of the records that mention it
    returned_count: int = 0  # mentions in records that also mention a return / carry a return reason
    by_class: list[VoiceClassCount] = Field(default_factory=list)
    quotes: list[VoiceQuote] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)  # up to 200 supporting record ids


class ChangeEvidence(CamelModel):
    count: int
    base: int
    share: float
    garment_class: Optional[str] = None
    avg_rating: Optional[float] = None  # of the supporting records
    baseline_rating: Optional[float] = None  # of all records in the same scope
    summary: str
    record_ids: list[str] = Field(default_factory=list)  # up to 50
    quotes: list[VoiceQuote] = Field(default_factory=list)


class RecommendedChange(CamelModel):
    id: str
    theme_id: str
    title: str
    action: str  # what to change, qualitatively (v5: no rule-of-thumb amounts)
    tech_pack_change: str  # action + evidence + refs, as it reaches the tech pack brief
    area: Literal["measurements", "bom", "construction", "testing", "colour", "pricing"]
    points_of_measure: list[str] = Field(default_factory=list)  # which POMs the change concerns (names, no values)
    instruction: Optional[str] = None  # v5: concrete tech-pack instruction drafted by the brain from the evidence
    instruction_by: Optional[str] = None  # brain route that drafted it
    confidence: Literal["high", "medium", "low"]
    priority: float
    evidence: ChangeEvidence
    rationale: Optional[str] = None  # one sentence from the brain (only numbers from the facts)
    conflicts_with: list[str] = Field(default_factory=list)  # opposite changes also backed by evidence


class VoiceColumns(CamelModel):
    text: Optional[str] = None
    title: Optional[str] = None
    rating: Optional[str] = None
    garment_class: Optional[str] = None
    product: Optional[str] = None
    size: Optional[str] = None
    fit_feedback: Optional[str] = None
    return_reason: Optional[str] = None
    date: Optional[str] = None
    id: Optional[str] = None
    helpful: Optional[str] = None


class VoiceInsights(CamelModel):
    id: str
    name: str
    source: VoiceSource
    noun: str  # "reviews" | "returns" | "tickets" | "records"
    record_count: int
    analysed_count: int  # records with any text to analyse
    columns: VoiceColumns
    avg_rating: Optional[float] = None
    garment_classes: list[VoiceClassCount] = Field(default_factory=list)
    themes: list[VoiceTheme] = Field(default_factory=list)
    recommended_changes: list[RecommendedChange] = Field(default_factory=list)
    summary: str
    method: str
    warnings: list[str] = Field(default_factory=list)
    phrased_by: Optional[str] = None  # v5: brain route that phrased the summary / rationales / instructions
    phrasing_error: Optional[str] = None  # why the brain didn't (not connected / failed)
    created_at: str = Field(default_factory=now_iso)


class VoiceRecord(CamelModel):
    id: str
    text: str = ""
    title: Optional[str] = None
    rating: Optional[float] = None
    garment_class: Optional[str] = None
    product: Optional[str] = None
    size: Optional[str] = None
    fit_feedback: Optional[str] = None
    return_reason: Optional[str] = None
    date: Optional[str] = None
    helpful: Optional[int] = None


class VoiceSample(CamelModel):
    key: str
    title: str
    description: str
    records: int
    source: VoiceSource


class SampleRequest(CamelModel):
    dataset_key: str = Field(min_length=1, max_length=64)


class ApplyRequest(CamelModel):
    change_ids: list[str] = Field(default_factory=list, max_length=30)
    design_id: Optional[str] = None
    trend_id: Optional[str] = None


class ApplyTarget(CamelModel):
    kind: Literal["design", "trend"]
    id: str


class ApplyResponse(CamelModel):
    dataset_id: str
    target: ApplyTarget
    applied: list[CustomerEvidence]  # everything now applied to the target, from every dataset


class VoiceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------------- samples (real, CC0)

_SAMPLE_SOURCE = dict(
    kind="sample",
    url="https://www.kaggle.com/datasets/nicapotato/womens-ecommerce-clothing-reviews",
    licence="CC0 1.0 (public domain)",
    attribution="Women's E-Commerce Clothing Reviews, Nick Brooks (nicapotato), 2018. Mirrored on OpenML "
                "(dataset 43673). Real, anonymised reviews; seeded random sample of 200.",
)
SAMPLES: dict[str, dict[str, str]] = {
    "outerwear": {"title": "Jackets & outerwear",
                  "description": "200 real reviews of jackets and outerwear from a women's fashion e-tailer."},
    "knits": {"title": "Knits & sweaters",
              "description": "200 real reviews of knit tops, sweaters and fine-gauge knitwear."},
    "dresses_pants": {"title": "Dresses & pants",
                      "description": "200 real reviews of dresses and pants."},
}


def sample_source(key: str) -> VoiceSource:
    return VoiceSource(dataset_key=key, title=f"Public review dataset: {SAMPLES[key]['title']}", **_SAMPLE_SOURCE)


def list_samples() -> list[VoiceSample]:
    out = []
    for key, meta in SAMPLES.items():
        path = SAMPLES_DIR / f"{key}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            n = sum(1 for _ in csv.DictReader(f))
        out.append(VoiceSample(key=key, title=meta["title"], description=meta["description"], records=n,
                               source=sample_source(key)))
    return out


# --------------------------------------------------------------------------- ingest: CSV


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (h or "").lower()).strip()


# Field -> header candidates in priority order (normalised: lower case, punctuation -> space).
_CANDIDATES: dict[str, list[str]] = {
    "id": ["review id", "record id", "ticket id", "return id", "id", "case id", "comment id", "order id",
           "order number", "order name", "order"],
    "text": ["review text", "review body", "body", "review", "review content", "comment", "comments", "content",
             "text", "feedback", "message", "customer comment", "customer comments", "return reason note",
             "return note", "return comment", "customer note", "note", "notes", "description", "details",
             "ticket body", "ticket description", "complaint", "verbatim", "response", "answer"],
    "title": ["review title", "title", "subject", "headline", "summary", "review headline"],
    "rating": ["rating", "review rating", "star rating", "stars", "score", "review score", "product rating",
               "overall rating", "overall", "rating value"],
    "garment_class": ["class name", "class", "product type", "category", "product category", "department name",
                      "department", "garment", "garment type", "item type", "type"],
    "product": ["product title", "product name", "product", "item", "item name", "product handle", "handle",
                "style", "style name", "sku title", "lineitem name"],
    "size": ["size purchased", "size ordered", "size bought", "size", "variant title", "variant", "variant size"],
    "fit_feedback": ["fit feedback", "fit", "fit rating", "how did it fit", "how does it fit", "sizing feedback",
                     "sizing"],
    "return_reason": ["return reason", "reason for return", "returns reason", "reason", "return type",
                      "return reason code"],
    "date": ["review date", "date", "created at", "created", "submitted at", "published at", "return date",
             "requested at", "order date", "timestamp"],
    "helpful": ["positive feedback count", "helpful votes", "helpful count", "helpful", "upvotes", "likes",
                "thumbs up"],
}
_NEVER = re.compile(r"\b(email|e mail|phone|address|name of reviewer|reviewer name|customer name|ip)\b")


def detect_columns(headers: list[str], rows: list[list[str]] | None = None) -> VoiceColumns:
    """Map raw headers to voice fields: exact (normalised) match first, then whole-word containment."""
    norm = {h: _norm_header(h) for h in headers}
    taken: set[str] = set()
    found: dict[str, str] = {}
    order = ["text", "return_reason", "fit_feedback", "rating", "title", "id", "garment_class", "product", "size",
             "date", "helpful"]
    # Pass 1: exact (normalised) header matches for every field; pass 2: whole-word containment
    # ("Review Body (text)" -> text) for fields still open. Ids are exact-only ("product_id" is not a record id).
    for exact in (True, False):
        for fld in order:
            if fld in found or (fld == "id" and not exact):
                continue
            for cand in _CANDIDATES[fld]:
                if exact:
                    hit = next((h for h in headers if h not in taken and norm[h] == cand
                                and not _NEVER.search(norm[h])), None)
                else:
                    hit = next((h for h in headers if h not in taken and not _NEVER.search(norm[h])
                                and re.search(rf"(^| ){re.escape(cand)}( |$)", norm[h])), None)
                if hit is not None:
                    found[fld] = hit
                    taken.add(hit)
                    break
    if "text" not in found and rows:
        # Fallback: the free-text column = the one with the longest average cell.
        best, best_len = None, 0.0
        for i, h in enumerate(headers):
            if h in taken or _NEVER.search(norm[h]):
                continue
            vals = [r[i] for r in rows[:200] if i < len(r) and r[i].strip()]
            if not vals:
                continue
            avg = sum(len(v) for v in vals) / len(vals)
            if avg > best_len and avg >= 25 and sum(1 for v in vals if " " in v) >= len(vals) * 0.6:
                best, best_len = h, avg
        if best:
            found["text"] = best
    return VoiceColumns(**found)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


_STARS = re.compile(r"^\s*(★+)")


def parse_rating(v: str | None) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = _STARS.match(s)
    if m:
        return float(len(m.group(1)))
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:/\s*(\d+))?", s)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    if m.group(2):
        scale = float(m.group(2))
        return round(val / scale * 5, 2) if scale > 0 else None
    return val


def _fit_text(v: str) -> str:
    """Normalise fit-feedback values ("small", "Runs large", "fit") into phrases the taxonomy reads."""
    s = v.strip()
    low = s.lower().replace("_", " ")
    mapping = {"small": "runs small", "large": "runs large", "big": "runs large", "fit": "true to size",
               "true": "true to size", "perfect": "true to size"}
    return mapping.get(low, low)


def _reason_text(v: str) -> str:
    """Return reasons like SIZE_TOO_SMALL / 'Too big' -> lower-case phrases."""
    low = v.strip().replace("_", " ").replace("-", " ").lower()
    mapping = {"size too small": "too small", "size too large": "too large", "not as described": "not as described",
               "color": "colour different from the photos", "colour": "colour different from the photos",
               "defective": "defective", "damaged": "defective"}
    return mapping.get(low, low)


def _clip(s: str | None) -> str:
    return (s or "").strip()[:MAX_TEXT_CHARS]


def parse_csv(data: bytes, filename: str = "upload.csv") -> tuple[list[VoiceRecord], VoiceColumns, list[str]]:
    text = _decode(data)
    warnings: list[str] = []
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if filename.lower().endswith(".tsv") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        headers = next(reader)
    except StopIteration:
        raise VoiceError(422, "the file is empty")
    headers = [h.strip() or f"column {i + 1}" for i, h in enumerate(headers)]
    rows: list[list[str]] = []
    row_nos: list[int] = []  # the data row number as a spreadsheet shows it (header = row 1)
    for i, r in enumerate(reader, start=2):
        if any(c.strip() for c in r):
            rows.append(r)
            row_nos.append(i)
        if len(rows) > MAX_RECORDS:
            break
    if len(rows) > MAX_RECORDS:
        rows = rows[:MAX_RECORDS]
        warnings.append(f"Only the first {MAX_RECORDS:,} rows were analysed.")
    cols = detect_columns(headers, rows)
    if not (cols.text or cols.return_reason or cols.fit_feedback or cols.title):
        raise VoiceError(422, "couldn't find a text column (e.g. 'review', 'body', 'comment', 'return reason') "
                              f"in: {', '.join(headers[:12])}")
    idx = {h: i for i, h in enumerate(headers)}

    def get(r: list[str], col: str | None) -> str | None:
        if not col:
            return None
        i = idx[col]
        return r[i] if i < len(r) else None

    records: list[VoiceRecord] = []
    seen: set[str] = set()
    is_sample_ids = cols.id == "review_id"
    for n, r in zip(row_nos, rows):
        raw_id = (get(r, cols.id) or "").strip()
        rid = (f"r{raw_id}" if is_sample_ids else raw_id) if raw_id else f"row-{n}"
        if rid in seen:
            rid = f"{rid}~row-{n}"
        seen.add(rid)
        helpful = get(r, cols.helpful)
        rating = parse_rating(get(r, cols.rating))
        records.append(VoiceRecord(
            id=rid[:80], text=_clip(get(r, cols.text)), title=_clip(get(r, cols.title)) or None, rating=rating,
            garment_class=_clip(get(r, cols.garment_class)) or None, product=_clip(get(r, cols.product)) or None,
            size=_clip(get(r, cols.size)) or None, fit_feedback=_clip(get(r, cols.fit_feedback)) or None,
            return_reason=_clip(get(r, cols.return_reason)) or None, date=_clip(get(r, cols.date)) or None,
            helpful=int(helpful) if helpful and helpful.strip().isdigit() else None,
        ))
    ratings = [x.rating for x in records if x.rating is not None]
    if ratings and max(ratings) > 5:
        scale = 10.0 if max(ratings) <= 10 else 100.0
        for x in records:
            if x.rating is not None:
                x.rating = round(x.rating / scale * 5, 2)
        warnings.append(f"Ratings look like a 0–{scale:g} scale; converted to 5 stars.")
    return records, cols, warnings


# --------------------------------------------------------------------------- ingest: PDF

_PDF_HEADER = re.compile(
    r"^\s*(?:(?:review|ticket|case|return|comment|feedback|complaint|order)\s*(?:#|no\.?|number|id)?\s*[:#-]?\s*[\w-]+"
    r"|#\s*\d+|\d{1,5}[.)]\s+)", re.I)
_PDF_RATING = re.compile(r"(?:rating|stars?|score)\s*[:=]?\s*(\d(?:[.,]\d)?)\s*(?:/\s*(5|10))?|(\d)\s*(?:/\s*5|stars?)\b|(★{1,5})",
                         re.I)


def parse_pdf(data: bytes) -> tuple[list[VoiceRecord], VoiceColumns, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise VoiceError(415, "PDF support is not installed (pypdf)") from e
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages[:200])]
    except Exception as e:  # noqa: BLE001
        raise VoiceError(422, f"couldn't read the PDF ({e.__class__.__name__})") from e
    warnings: list[str] = []
    if not any(t.strip() for _, t in pages):
        raise VoiceError(422, "the PDF has no extractable text (scanned images need OCR first)")

    # Split into records: explicit record headers ("Review #12", "Ticket 4411", "3.") when there are at least two,
    # else blank-line paragraphs, else one record per substantial line.
    blocks: list[tuple[int, str]] = []
    by_headers = sum(1 for _, txt in pages for ln in txt.splitlines() if _PDF_HEADER.match(ln)) >= 2
    for pno, txt in pages:
        lines = [ln.rstrip() for ln in txt.splitlines()]
        heads = [i for i, ln in enumerate(lines) if _PDF_HEADER.match(ln)]
        if by_headers and heads:
            preamble = "\n".join(lines[:heads[0]]).strip()
            if len(preamble) >= 40:  # a title line above the first record is not a record
                blocks.append((pno, preamble))
            for a, b in zip(heads, heads[1:] + [len(lines)]):
                blocks.append((pno, "\n".join(lines[a:b])))
        elif re.search(r"\n\s*\n", txt):
            blocks += [(pno, p) for p in re.split(r"\n\s*\n", txt)]
        else:
            blocks += [(pno, ln) for ln in lines]
    records: list[VoiceRecord] = []
    per_page: Counter = Counter()
    for pno, block in blocks:
        body = re.sub(r"[ \t]+", " ", block).strip()
        if len(body) < 15:
            continue
        per_page[pno] += 1
        rating = None
        m = _PDF_RATING.search(body)
        if m:
            if m.group(4):
                rating = float(len(m.group(4)))
            else:
                val = float((m.group(1) or m.group(3)).replace(",", "."))
                rating = round(val / 2, 2) if m.group(2) == "10" else val
                rating = rating if 0 < rating <= 5 else None
        records.append(VoiceRecord(id=f"p{pno}-{per_page[pno]}", text=_clip(body), rating=rating))
        if len(records) >= MAX_RECORDS:
            warnings.append(f"Only the first {MAX_RECORDS:,} records were analysed.")
            break
    if not records:
        raise VoiceError(422, "no records found in the PDF")
    warnings.append("PDF: records were split from the document layout; ids are page-record (p2-3 = page 2, 3rd).")
    return records, VoiceColumns(text="(pdf text)"), warnings


# --------------------------------------------------------------------------- analysis


@dataclass
class _Hit:
    record: VoiceRecord
    field: str
    value: str
    start: int
    end: int
    polarity: str  # negative | positive | neutral


@dataclass
class Dataset:
    insights: VoiceInsights
    records: dict[str, VoiceRecord]
    hits: dict[str, list[_Hit]] = field(default_factory=dict)  # theme id -> hits (one per record)


_FIELDS = (("text", "text"), ("title", "title"), ("returnReason", "return_reason"), ("fitFeedback", "fit_feedback"))


def _field_value(rec: VoiceRecord, attr: str) -> str:
    v = getattr(rec, attr) or ""
    if attr == "return_reason" and v:
        return _reason_text(v)
    if attr == "fit_feedback" and v:
        return _fit_text(v)
    return v


def _polarity(kind: str, rating: float | None) -> str:
    if kind == "problem":
        return "negative"
    if kind == "praise":
        return "positive"
    if rating is None:
        return "neutral"
    return "negative" if rating <= 3 else "positive"


def _sentence_window(value: str, start: int, end: int, limit: int = 240) -> tuple[int, int, bool]:
    """The sentence around [start, end) in `value`, cut to `limit` chars around the hit if longer."""
    s = max(value.rfind(c, 0, start) for c in ".!?\n") + 1
    ends = [i for i in (value.find(c, end) for c in ".!?\n") if i >= 0]
    e = (min(ends) + 1) if ends else len(value)
    while s < start and value[s] in " \t\"'":
        s += 1
    truncated = False
    if e - s > limit:
        truncated = True
        half = max(0, (limit - (end - start)) // 2)
        s2 = max(s, start - half)
        e2 = min(e, end + half)
        # snap to word boundaries
        if s2 > s:
            sp = value.find(" ", s2, start)
            s2 = sp + 1 if sp >= 0 else s2
        if e2 < e:
            sp = value.rfind(" ", end, e2)
            e2 = sp if sp >= 0 else e2
        s, e = s2, e2
    return s, e, truncated


def _quote(hit: _Hit) -> VoiceQuote:
    s, e, trunc = _sentence_window(hit.value, hit.start, hit.end)
    field_name = hit.field
    text = hit.value[s:e].rstrip()
    if hit.field in ("returnReason", "fitFeedback"):
        # quote the merchant's raw cell, not our normalised phrase
        raw = getattr(hit.record, "return_reason" if hit.field == "returnReason" else "fit_feedback") or ""
        return VoiceQuote(record_id=hit.record.id, field=field_name, text=raw, rating=hit.record.rating,
                          garment_class=hit.record.garment_class)
    return VoiceQuote(record_id=hit.record.id, field=field_name, text=text, truncated=trunc,
                      match_start=hit.start - s, match_end=min(hit.end - s, len(text)),
                      rating=hit.record.rating, garment_class=hit.record.garment_class)


def _pick_quotes(hits: list[_Hit], kind: str, polarity: str, n: int = 4) -> list[VoiceQuote]:
    want = {"negative": "negative", "positive": "positive"}.get(polarity)

    def key(h: _Hit):
        pol_rank = 0 if (want is None or h.polarity == want) else 1
        r = h.record.rating if h.record.rating is not None else 3.0
        rating_rank = r if polarity != "positive" else -r
        s, e, trunc = _sentence_window(h.value, h.start, h.end)
        length = e - s
        len_rank = 0 if 35 <= length <= 220 else 1
        field_rank = 0 if h.field == "text" else 1
        return (pol_rank, field_rank, len_rank, rating_rank, -(h.record.helpful or 0), h.record.id)

    out, seen = [], set()
    for h in sorted(hits, key=key):
        if h.record.id in seen:
            continue
        seen.add(h.record.id)
        out.append(_quote(h))
        if len(out) >= n:
            break
    return out


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 2) if xs else None


def _share(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def analyse(records: list[VoiceRecord]) -> tuple[list[VoiceTheme], dict[str, list[_Hit]], dict[str, Any]]:
    """Deterministic pass: one hit per (record, theme), counts and shares, per class, quotes."""
    hits: dict[str, list[_Hit]] = defaultdict(list)
    analysed = [r for r in records if any(_field_value(r, a).strip() for _, a in _FIELDS)]
    for rec in analysed:
        per_theme: dict[str, _Hit] = {}
        for fname, attr in _FIELDS:
            value = _field_value(rec, attr)
            if not value.strip():
                continue
            for m in find_mentions(value):
                if m.theme_id in per_theme:
                    continue
                th = THEME_BY_ID[m.theme_id]
                per_theme[m.theme_id] = _Hit(rec, fname, value, m.start, m.end, _polarity(th.kind, rec.rating))
        if rec.return_reason and "returns.returned" not in per_theme:
            per_theme["returns.returned"] = _Hit(rec, "returnReason", _field_value(rec, "return_reason"), 0,
                                                 len(_field_value(rec, "return_reason")), "negative")
        for tid, h in per_theme.items():
            hits[tid].append(h)

    base = len(analysed)
    class_totals = Counter(r.garment_class for r in analysed if r.garment_class)
    returned_ids = {h.record.id for h in hits.get("returns.returned", [])}
    themes: list[VoiceTheme] = []
    for th in THEMES:
        hs = hits.get(th.id, [])
        if not hs:
            continue
        neg = sum(1 for h in hs if h.polarity == "negative")
        pos = sum(1 for h in hs if h.polarity == "positive")
        neu = len(hs) - neg - pos
        polarity = "negative" if neg >= 0.6 * len(hs) else "positive" if pos >= 0.6 * len(hs) else "mixed"
        by_cls = Counter(h.record.garment_class for h in hs if h.record.garment_class)
        themes.append(VoiceTheme(
            id=th.id, group=th.group, group_label=GROUP_LABELS[th.group], name=th.name, kind=th.kind,
            polarity=polarity, count=len(hs), share=_share(len(hs), base), negative_count=neg, positive_count=pos,
            neutral_count=neu, avg_rating=_mean([h.record.rating for h in hs if h.record.rating is not None]),
            returned_count=sum(1 for h in hs if h.record.id in returned_ids) if th.id != "returns.returned" else len(hs),
            by_class=[VoiceClassCount(garment_class=c, count=n, total=class_totals[c], share=_share(n, class_totals[c]))
                      for c, n in by_cls.most_common(6)],
            quotes=_pick_quotes(hs, th.kind, polarity),
            record_ids=[h.record.id for h in hs[:200]],
        ))
    themes.sort(key=lambda t: (-t.count, t.id))
    facts = {
        "base": base,
        "class_totals": class_totals,
        "avg_rating": _mean([r.rating for r in analysed if r.rating is not None]),
        "class_avg": {c: _mean([r.rating for r in analysed if r.garment_class == c and r.rating is not None])
                      for c in class_totals},
    }
    return themes, dict(hits), facts


# --------------------------------------------------------------------------- change templates


@dataclass
class Template:
    title: str
    action: str  # qualitative: what to change, never by how much
    area: str
    poms: list[str] = field(default_factory=list)  # points of measure concerned (names only)


def _length_pom(kind: str) -> str:
    return {"trousers": "Inseam", "dress": "Length (HPS to hem)", "skirt": "Skirt length"}.get(kind, "Body length (HPS)")


def template(theme_id: str, kind: str) -> Template | None:
    """The change a problem theme calls for, in qualitative tech-pack language, for a garment kind. The amounts are
    for the brain (from the evidence) or the technical designer to set - they are never assumed here."""
    lower_body = kind in ("trousers", "skirt")
    L = _length_pom(kind)
    t: dict[str, Template] = {
        "fit.shoulders_tight": Template("Add shoulder & bicep ease", "Add across-shoulder and bicep ease; review "
                                        "armhole depth", "measurements", ["Across shoulder", "Bicep", "Armhole depth"]),
        "fit.shoulders_wide": Template("Narrow the shoulder", "Reduce across-shoulder so the seam sits on the shoulder "
                                       "point; consider shoulder stay tape", "measurements", ["Across shoulder"]),
        "fit.chest_tight": Template("Add chest / bust ease", "Add chest / bust ease and stop gaping at the bust point",
                                    "measurements", ["Chest / bust"]),
        "fit.chest_loose": Template("Reduce chest / bust ease", "Reduce chest / bust ease", "measurements",
                                    ["Chest / bust"]),
        "fit.waist_tight": Template("Add waist ease", "Add waist ease" + ("; consider a partly elasticated back "
                                    "waistband" if lower_body else ""), "measurements", ["Waist"]),
        "fit.waist_loose": Template("Take in the waist", "Reduce the waist and add back-waist shaping to stop gaping",
                                    "measurements", ["Waist"]),
        "fit.hips_tight": Template("Add hip & thigh ease", "Add hip ease" + (" and thigh ease; review the seat depth"
                                   if kind == "trousers" else ""), "measurements",
                                   ["Hip"] + (["Thigh"] if kind == "trousers" else [])),
        "fit.runs_small": Template("Re-grade: the block runs small", "Open the block (circumference at chest/bust, "
                                   "waist and hip) and grade through; flag 'runs small' on the product page until "
                                   "re-graded stock lands", "measurements", ["Chest / bust", "Waist", "Hip"]),
        "fit.runs_large": Template("Re-grade: the block runs large", "Close the block (circumference at chest/bust, "
                                   "waist and hip) and grade through; flag 'runs large' on the product page until "
                                   "re-graded stock lands", "measurements", ["Chest / bust", "Waist", "Hip"]),
        "fit.too_short": Template("Lengthen", f"Lengthen the {L.lower()}", "measurements", [L]),
        "fit.too_long": Template("Shorten", f"Shorten the {L.lower()}; consider a petite length", "measurements", [L]),
        "fit.sleeves_short": Template("Lengthen the sleeve", "Lengthen the sleeve (shoulder point to cuff)",
                                      "measurements", ["Sleeve length"]),
        "fit.sleeves_long": Template("Shorten the sleeve", "Shorten the sleeve; consider a cuff tab for adjustment",
                                     "measurements", ["Sleeve length"]),
        "fit.sleeves_tight": Template("Open the sleeve", "Add bicep and forearm ease; review armhole depth",
                                      "measurements", ["Bicep", "Forearm", "Armhole depth"]),
        "fit.boxy": Template("Add waist shaping", "Introduce waist shaping (darts or side-seam suppression) while "
                             "keeping chest ease", "measurements", ["Waist"]),
        "fabric.pilling": Template("Specify an anti-pill fabric", "Move to a longer-staple, tighter-twist yarn or an "
                                   "anti-pill finish, and add a pilling test to fabric approval", "bom"),
        "fabric.itchy": Template("Soften the hand", "Move to a softer fibre or add a softening finish; bind the neck "
                                 "and cuffs with a soft tape", "bom"),
        "fabric.thin": Template("Heavier shell fabric", "Raise the shell fabric weight, state a minimum weight on the "
                                "BOM and add an opacity check to fabric approval", "bom"),
        "fabric.sheer": Template("Fix opacity", "Use a denser fabric or add a colour-matched modesty lining; add an "
                                 "opacity test to fabric approval", "bom"),
        "fabric.wrinkles": Template("Wrinkle-recovery spec", "Add a wrinkle-recovery requirement to fabric approval, "
                                    "or a fibre blend that recovers better", "testing"),
        "fabric.shrinks": Template("Pre-shrink the fabric", "Pre-shrink / sanforise the shell and add a dimensional-"
                                   "stability test after home washing", "bom"),
        "fabric.stretches_out": Template("Improve recovery", "Specify stretch recovery and stay-tape the neckline, "
                                         "waistband and openings", "bom"),
        "fabric.snags": Template("Snag resistance", "Tighten the construction (shorter floats / denser weave) and add "
                                 "a snag test", "testing"),
        "colour.vs_photo": Template("Colour accuracy: lab dip + photo QC", "Approve colour on a lab dip against the "
                                    "colour standard and re-shoot product photos under controlled light", "colour"),
        "construction.seams": Template("Reinforce seams", "Raise stitch density, bar-tack the stress points and add a "
                                       "seam-slippage test to fabric approval", "construction"),
        "construction.zip": Template("Upgrade the zip", "Upgrade the zip and add a zip garage; topstitch the tape flat",
                                     "bom"),
        "construction.buttons": Template("Secure buttons & closures", "Lock-stitch buttons with backing buttons; stop "
                                         "gaping at the closure", "bom"),
        "construction.lining": Template("Fix the lining", "Re-balance the lining against the shell (length, ease "
                                        "pleat) and use an anti-static lining", "construction"),
        "construction.pockets": Template("Add functional pockets", "Add functional pockets", "bom"),
        "construction.quality": Template("Tighten make QC", "Add inline inspection with thread-trim and seam-strength "
                                         "checks before packing", "construction"),
        "care.dry_clean": Template("Make it machine-washable", "Re-engineer for a gentle machine wash: test shell, "
                                   "fusing and trims for wash durability and update the care label", "testing"),
        "care.durability": Template("Wash-durability specs", "Add colourfastness-to-washing and appearance-after-"
                                    "washing requirements to the test report", "testing"),
        "comfort.uncomfortable": Template("Remove pressure points", "Flat-lock or bind the seams at contact points and "
                                          "soften the waistband and trims", "construction"),
        "warmth.not_warm": Template("Add warmth", "Add insulation in the body and sleeves" if kind in
                                    ("jacket", "coat") else "Move to a warmer yarn or a tighter gauge", "bom"),
        "warmth.too_warm": Template("Improve breathability", "Use a lighter or more open fabric and add ventilation",
                                    "construction"),
        "value.overpriced": Template("Value-engineer the cost", "Look for cost in trims and fabric yield, or keep the "
                                    "price and tell the fabric and make story on the product page", "pricing"),
    }
    return t.get(theme_id)


def _kind_for_class(cls: str | None) -> str:
    if not cls:
        return "top"
    k = garment_kind(cls)
    return "jacket" if k == "coat" else k


def build_changes(themes: list[VoiceTheme], hits: dict[str, list[_Hit]], facts: dict[str, Any], noun: str,
                  default_kind: str | None = None) -> list[RecommendedChange]:
    base = facts["base"]
    class_totals: Counter = facts["class_totals"]
    out: list[RecommendedChange] = []
    for th in themes:
        theme = THEME_BY_ID[th.id]
        if theme.kind == "praise" or th.id == "returns.returned":
            continue
        neg = [h for h in hits.get(th.id, []) if h.polarity == "negative"]
        if theme.kind == "rating":  # unrated records count when the dataset has no ratings at all
            neg += [h for h in hits.get(th.id, []) if h.polarity == "neutral" and facts["avg_rating"] is None]
        n_all = len(neg)
        if n_all < 3 or _share(n_all, base) < 1.5:
            continue
        # Scope: the class that carries most of it, when one clearly does.
        by_cls = Counter(h.record.garment_class for h in neg if h.record.garment_class)
        scope_cls, scoped = None, neg
        if len(class_totals) >= 2 and by_cls:
            cls, n = by_cls.most_common(1)[0]
            if n >= 0.5 * n_all and class_totals[cls] >= 3 and n >= 3:
                scope_cls, scoped = cls, [h for h in neg if h.record.garment_class == cls]
        count = len(scoped)
        scope_base = class_totals[scope_cls] if scope_cls else base
        kind_cls = scope_cls or (by_cls.most_common(1)[0][0] if by_cls else None)
        kind = _kind_for_class(kind_cls) if kind_cls else (default_kind or "top")
        tpl = template(th.id, kind)
        if tpl is None:
            continue
        share = _share(count, scope_base)
        avg = _mean([h.record.rating for h in scoped if h.record.rating is not None])
        baseline = facts["class_avg"].get(scope_cls) if scope_cls else facts["avg_rating"]
        where = f" for {scope_cls}" if scope_cls else ""
        summary = f"{count} of {scope_base} {noun}{where} ({share:g}%) mention {theme.phrase}"
        if avg is not None and baseline is not None:
            summary += f"; they average {avg:.1f}★ vs {baseline:.1f}★"
        quotes = _pick_quotes(scoped, theme.kind, "negative", n=3)
        refs = [q.record_id for q in quotes]
        tech = f"{tpl.action} - {count} of {scope_base} {noun}{where} mention {theme.phrase} [refs: {', '.join(refs)}]"
        drop = max(0.0, (baseline or 0) - (avg or baseline or 0)) if avg is not None and baseline is not None else 0.0
        priority = round(count * (1 + drop) * (1.5 if share >= 10 else 1.0), 2)
        confidence = "high" if count >= 12 and share >= 5 else "medium" if count >= 6 or share >= 3 else "low"
        out.append(RecommendedChange(
            id=f"chg_{th.id.replace('.', '_')}", theme_id=th.id, title=tpl.title, action=tpl.action,
            tech_pack_change=tech, area=tpl.area, points_of_measure=list(tpl.poms),
            confidence=confidence, priority=priority,
            evidence=ChangeEvidence(count=count, base=scope_base, share=share, garment_class=scope_cls,
                                    avg_rating=avg, baseline_rating=baseline, summary=summary,
                                    record_ids=[h.record.id for h in scoped[:50]], quotes=quotes),
        ))
    out = _resolve_conflicts(out, noun)
    out.sort(key=lambda c: (-c.priority, c.id))
    return out[:12]


CONFLICT_PAIRS = (("fit.runs_small", "fit.runs_large"), ("fit.too_short", "fit.too_long"),
                  ("fit.sleeves_short", "fit.sleeves_long"), ("fit.chest_tight", "fit.chest_loose"),
                  ("fit.waist_tight", "fit.waist_loose"), ("fit.shoulders_tight", "fit.shoulders_wide"),
                  ("warmth.not_warm", "warmth.too_warm"))


def _resolve_conflicts(changes: list[RecommendedChange], noun: str) -> list[RecommendedChange]:
    """Opposite findings in the same scope: flag them; for sizing, if both are strong, the real issue is
    inconsistent sizing, so replace the pair with one size-consistency change."""
    by_theme = {c.theme_id: c for c in changes}
    for a_id, b_id in CONFLICT_PAIRS:
        a, b = by_theme.get(a_id), by_theme.get(b_id)
        if not a or not b:
            continue
        same_scope = a.evidence.garment_class == b.evidence.garment_class
        strong, weak = (a, b) if a.evidence.count >= b.evidence.count else (b, a)
        if a_id == "fit.runs_small" and same_scope and weak.evidence.count >= 0.5 * strong.evidence.count:
            ev_a, ev_b = a.evidence, b.evidence
            ids = list(dict.fromkeys(ev_a.record_ids + ev_b.record_ids))
            where = f" for {ev_a.garment_class}" if ev_a.garment_class else ""
            quotes = (ev_a.quotes[:2] + ev_b.quotes[:2])[:4]
            action = ("Audit grading and size labelling: measure production samples per size against the spec at "
                      "chest, waist and hip, and publish a measured size chart on the product page")
            summary = (f"{ev_a.count} of {ev_a.base} {noun}{where} say it runs small and {ev_b.count} say it runs "
                       "large: sizing is inconsistent")
            merged = RecommendedChange(
                id="chg_fit_size_consistency", theme_id="fit.size_consistency", title="Fix size consistency",
                action=action, tech_pack_change=f"{action} - {summary} [refs: {', '.join(q.record_id for q in quotes)}]",
                area="measurements", points_of_measure=["Chest / bust", "Waist", "Hip"],
                confidence="high" if len(ids) >= 12 else "medium", priority=round(a.priority + b.priority, 2),
                evidence=ChangeEvidence(count=len(ids), base=ev_a.base, share=_share(len(ids), ev_a.base),
                                        garment_class=ev_a.garment_class, summary=summary, record_ids=ids[:50],
                                        quotes=quotes))
            changes = [c for c in changes if c.id not in (a.id, b.id)] + [merged]
            continue
        a.conflicts_with.append(b.id)
        b.conflicts_with.append(a.id)
    return changes


def _noun(cols: VoiceColumns, pdf: bool) -> str:
    if pdf:
        return "records"
    names = " ".join(_norm_header(x or "") for x in (cols.text, cols.title))
    if "ticket" in names or "message" in names:
        return "tickets"
    if cols.rating or "review" in names:
        return "reviews"
    if cols.return_reason:
        return "returns"
    return "comments"


def _summary(themes: list[VoiceTheme], changes: list[RecommendedChange], analysed: int, noun: str,
             classes: int) -> str:
    probs = [t for t in themes if t.polarity != "positive" and t.id != "returns.returned"][:3]
    praise = [t for t in themes if t.polarity == "positive"][:2]
    s = f"{analysed:,} {noun} analysed" + (f" across {classes} garment classes" if classes > 1 else "") + "."
    if probs:
        s += " Most-raised issues: " + ", ".join(f"{t.name.lower()} ({t.share:g}%)" for t in probs) + "."
    if praise:
        s += " Customers praise " + " and ".join(f"{THEME_BY_ID[t.id].phrase} ({t.share:g}%)" for t in praise) + "."
    if changes:
        s += f" {len(changes)} tech pack change{'s' if len(changes) != 1 else ''} recommended."
    return s


METHOD = ("Deterministic apparel taxonomy: phrase and proximity rules per theme (fit by point of measure, sizing, "
          "fabric, colour vs photo, construction, care, comfort, warmth, value), with negation (\"not tight at "
          "all\" is not tight), hedging (\"worried it would pill\") and body-description guards; polarity from the "
          "rule, or from the star rating for ambiguous themes. One count per record per theme; every quote is an "
          "exact excerpt of a real record.")


# --------------------------------------------------------------------------- dataset store

_datasets: "OrderedDict[str, Dataset]" = OrderedDict()


@dataclass
class _Applied:
    dataset_id: str
    change: RecommendedChange


_applied_design: dict[str, list[_Applied]] = {}
_applied_trend: dict[str, list[_Applied]] = {}


def reset() -> None:
    _datasets.clear()
    _applied_design.clear()
    _applied_trend.clear()


def build_dataset(records: list[VoiceRecord], cols: VoiceColumns, source: VoiceSource, name: str,
                  warnings: list[str], *, pdf: bool = False) -> Dataset:
    if not records:
        raise VoiceError(422, "no records found")
    themes, hits, facts = analyse(records)
    if facts["base"] == 0:
        raise VoiceError(422, "none of the records has any text to analyse")
    noun = _noun(cols, pdf)
    changes = build_changes(themes, hits, facts, noun)
    classes = facts["class_totals"]
    ins = VoiceInsights(
        id=new_id("voc"), name=name, source=source, noun=noun, record_count=len(records),
        analysed_count=facts["base"], columns=cols, avg_rating=facts["avg_rating"],
        garment_classes=[VoiceClassCount(garment_class=c, count=n, total=facts["base"], share=_share(n, facts["base"]))
                         for c, n in classes.most_common(12)],
        themes=themes, recommended_changes=changes,
        summary=_summary(themes, changes, facts["base"], noun, len(classes)), method=METHOD, warnings=warnings,
    )
    ds = Dataset(insights=ins, records={r.id: r for r in records}, hits=hits)
    _datasets[ins.id] = ds
    while len(_datasets) > MAX_DATASETS:
        _datasets.popitem(last=False)
    return ds


def ingest_upload(data: bytes, filename: str, content_type: str | None = None) -> Dataset:
    if not data:
        raise VoiceError(422, "the file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise VoiceError(413, f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    low = (filename or "").lower()
    ctype = (content_type or "").lower()
    source = VoiceSource(kind="upload", filename=filename, title=f"Your upload: {filename}")
    if low.endswith(".pdf") or ctype == "application/pdf" or data[:5] == b"%PDF-":
        records, cols, warnings = parse_pdf(data)
        return build_dataset(records, cols, source, filename, warnings, pdf=True)
    if low.endswith((".csv", ".tsv", ".txt")) or ctype in ("text/csv", "text/tab-separated-values", "text/plain",
                                                           "application/vnd.ms-excel"):
        records, cols, warnings = parse_csv(data, filename)
        return build_dataset(records, cols, source, filename, warnings)
    raise VoiceError(415, "unsupported file type: upload a CSV/TSV export or a PDF")


def ingest_sample(key: str) -> Dataset:
    if key not in SAMPLES or not (SAMPLES_DIR / f"{key}.csv").exists():
        raise VoiceError(404, f"unknown sample dataset '{key}' (have: {', '.join(SAMPLES)})")
    data = (SAMPLES_DIR / f"{key}.csv").read_bytes()
    records, cols, warnings = parse_csv(data, f"{key}.csv")
    return build_dataset(records, cols, sample_source(key), f"Sample: {SAMPLES[key]['title']}", warnings)


def get_dataset(dataset_id: str) -> Dataset:
    ds = _datasets.get(dataset_id)
    if ds is None:
        raise VoiceError(404, f"voice dataset '{dataset_id}' not found")
    return ds


# --------------------------------------------------------------------------- live phrasing (optional)

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers_ok(text: str, allowed: set[str]) -> bool:
    return all(n.replace(",", "") in allowed for n in _NUM.findall(text))


async def phrase_live(ds: Dataset) -> None:
    """The brain phrases the summary, one rationale per change (numbers only from the facts) and one concrete
    tech-pack instruction per change, drafted from the evidence (labelled with its route). Raises
    brain.BrainUnavailable when no brain is connected / it failed - the deterministic findings stand on their own."""
    from . import brain

    ins = ds.insights
    facts = {
        "noun": ins.noun, "analysedCount": ins.analysed_count, "avgRating": ins.avg_rating,
        "themes": [{"name": t.name, "count": t.count, "share": t.share, "polarity": t.polarity,
                    "quotes": [q.text for q in t.quotes[:2]]} for t in ins.themes[:10]],
        "changes": [{"id": c.id, "title": c.title, "action": c.action, "pointsOfMeasure": c.points_of_measure,
                     "evidence": c.evidence.summary, "quotes": [q.text for q in c.evidence.quotes[:2]]}
                    for c in ins.recommended_changes],
    }
    blob = json.dumps(facts)
    allowed = {n.replace(",", "") for n in _NUM.findall(blob)}
    ids = {c.id for c in ins.recommended_changes}

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
        return [
            {"role": "system", "content": "You are a senior apparel technical designer and merchandiser turning "
                                          "customer feedback into tech-pack changes. Output JSON only."},
            {"role": "user", "content": (
                "Here are deterministic findings from the brand's customer data. (1) Write a 2-sentence summary for "
                "the creative director. (2) For each change id, one short sentence on why it matters commercially "
                "(returns, ratings, sizing confidence) using ONLY numbers that appear in the facts. (3) For each change "
                "id, the concrete instruction a factory would follow (which points of measure / materials / tests, and "
                "by how much), based on the evidence and the quotes; say 'to be confirmed on the fit sample' where the "
                "evidence can't size a change. Never invent customer quotes.\n\n"
                f"Facts:\n{blob}\n\n{context}\n\n"
                f'Schema: {{"summary": str, "rationales": {{"<change id>": str}}, '
                f'"instructions": {{"<change id>": str}}}}{extra}')},
        ]

    def validate(data: Any) -> dict:
        if not isinstance(data, dict) or not isinstance(data.get("summary"), str):
            raise ValueError("expected {summary, rationales, instructions}")
        rats = data.get("rationales") or {}
        instr = data.get("instructions") or {}
        if not isinstance(rats, dict) or not isinstance(instr, dict):
            raise ValueError("rationales / instructions must be objects")
        return {"summary": data["summary"].strip()[:600],
                "rationales": {k: str(v).strip()[:280] for k, v in rats.items() if k in ids and str(v).strip()},
                "instructions": {k: str(v).strip()[:400] for k, v in instr.items() if k in ids and str(v).strip()}}

    thought = await brain.think_json("voice_insights", messages, validate, max_tokens=1400, temperature=0.3,
                                     knowledge_query="fit blocks points of measure fabric standards testing")
    out = thought.value
    if out["summary"] and _numbers_ok(out["summary"], allowed):
        ins.summary = out["summary"]
    for c in ins.recommended_changes:
        r = out["rationales"].get(c.id)
        if r and _numbers_ok(r, allowed):
            c.rationale = r
        ins_text = out["instructions"].get(c.id)
        if ins_text:
            c.instruction, c.instruction_by = ins_text, thought.route
    ins.phrased_by = thought.route
    ins.phrasing_error = None


# --------------------------------------------------------------------------- apply -> tech pack


def _evidence(ds_id: str, change: RecommendedChange, kind: str | None = None) -> CustomerEvidence:
    ds = _datasets.get(ds_id)
    ins = ds.insights if ds else None
    tpl = template(change.theme_id, kind) if kind else None
    action = tpl.action if tpl else change.action
    tech = change.tech_pack_change.replace(change.action, action, 1) if tpl else change.tech_pack_change
    return CustomerEvidence(
        dataset_id=ds_id, dataset_name=ins.name if ins else ds_id,
        source=(ins.source.title or ins.name) if ins else ds_id, change_id=change.id, title=tpl.title if tpl else change.title,
        tech_pack_change=tech, area=tpl.area if tpl else change.area, count=change.evidence.count,
        base=change.evidence.base, share=change.evidence.share, garment_class=change.evidence.garment_class,
        record_ids=list(change.evidence.record_ids), quotes=list(change.evidence.quotes),
        instruction=change.instruction, instruction_by=change.instruction_by,
    )


def apply(dataset_id: str, req: ApplyRequest) -> ApplyResponse:
    ds = get_dataset(dataset_id)
    by_id = {c.id: c for c in ds.insights.recommended_changes}
    unknown = [c for c in req.change_ids if c not in by_id]
    if unknown:
        raise VoiceError(422, f"unknown change id(s): {', '.join(unknown[:5])}")
    for cid in req.change_ids:
        clash = [o for o in by_id[cid].conflicts_with if o in req.change_ids]
        if clash:
            raise VoiceError(422, f"{cid} contradicts {clash[0]} (e.g. 'runs small' vs 'runs large'): apply one")
    if req.design_id:
        design = store.designs.get(req.design_id)
        if design is None:
            raise VoiceError(404, f"design '{req.design_id}' not found")
        target, bucket = ApplyTarget(kind="design", id=design.id), _applied_design
    elif req.trend_id:
        if req.trend_id not in store.trends:
            raise VoiceError(404, f"trend '{req.trend_id}' not found")
        target, bucket = ApplyTarget(kind="trend", id=req.trend_id), _applied_trend
    else:
        raise VoiceError(422, "give a designId or a trendId to apply the changes to")
    # Set semantics per (target, dataset): the request is the full selection from this dataset.
    keep = [a for a in bucket.get(target.id, []) if a.dataset_id != dataset_id]
    chosen = list(dict.fromkeys(req.change_ids))
    bucket[target.id] = keep + [_Applied(dataset_id, by_id[c]) for c in chosen]
    kind = None
    if target.kind == "design":
        kind = _kind_for_class(store.designs[target.id].garment_type)
    elif target.id in store.trends:
        kind = _kind_for_class(store.trends[target.id].garment_type)
    applied = [_evidence(a.dataset_id, a.change, kind) for a in bucket[target.id]]
    return ApplyResponse(dataset_id=dataset_id, target=target, applied=applied)


def _lineage(design: Design) -> list[str]:
    ids, cur, seen = [], design, set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        ids.append(cur.id)
        cur = store.designs.get(cur.parent_design_id) if cur.parent_design_id else None
    return ids


def evidence_for(design: Design) -> list[CustomerEvidence]:
    """Changes applied to this design, its ancestors or its trend (deduplicated, design first)."""
    kind = _kind_for_class(design.garment_type)
    out: list[CustomerEvidence] = []
    seen: set[tuple[str, str]] = set()
    applied = [a for did in _lineage(design) for a in _applied_design.get(did, [])]
    applied += _applied_trend.get(design.trend_id, [])
    for a in applied:
        k = (a.dataset_id, a.change.id)
        if k in seen:
            continue
        seen.add(k)
        out.append(_evidence(a.dataset_id, a.change, kind))
    return out


def _hint(ev: CustomerEvidence) -> str:
    action = ev.instruction or re.split(r' [-\u2014] ', ev.tech_pack_change, maxsplit=1)[0]
    where = f" {ev.garment_class}" if ev.garment_class else ""
    refs = ", ".join(q.record_id for q in ev.quotes[:3])
    return f"{action} (customer evidence: {ev.count} of {ev.base}{where} {_noun_of(ev)}; refs {refs})"


def _noun_of(ev: CustomerEvidence) -> str:
    ds = _datasets.get(ev.dataset_id)
    return ds.insights.noun if ds else "records"


def attach_to_design(design: Design) -> list[CustomerEvidence]:
    """Fold applied customer-voice changes into the design's creative-direction hints (the tech-pack brief), so the
    brain writes them into the measurements / BOM. Idempotent."""
    from .direction import DirectionState

    evidence = evidence_for(design)
    if not evidence:
        return []
    meta = store.design_meta.get(design.id)
    if meta is None:
        meta = DesignMeta(base_seed=design.seed)
        store.design_meta[design.id] = meta
    st = meta.direction if isinstance(meta.direction, DirectionState) else DirectionState()
    for ev in evidence:
        hint = _hint(ev)
        if hint not in st.hints:
            st.hints.append(hint)
        marker = f"voice:{ev.dataset_id}"
        if marker not in st.direction_ids:
            st.direction_ids.append(marker)
    meta.direction = st
    return evidence


def finalize_techpack(tp: TechPack, design: Design) -> TechPack:
    """Attach the customer evidence behind the tech pack (the brain wrote the changes into it)."""
    evidence = evidence_for(design)
    if evidence:
        tp.customer_evidence = evidence
    return tp


def sources_line(evidence: list[CustomerEvidence]) -> str:
    names = list(dict.fromkeys(ev.dataset_name for ev in evidence))
    return ", ".join(names)
