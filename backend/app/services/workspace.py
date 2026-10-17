"""v5: the Brand workspace - the merchant's own data, persisted in SQLite (stdlib sqlite3).

One workspace per backend (one brand). File: $ATELIER_DATA_DIR/atelier.sqlite3 (default backend/var/), uploaded
files under $ATELIER_DATA_DIR/files/. Every other module reads brand data through this one:

    profile()            brand name, currency, markets, voice, sizes, colours, price architecture, promise, window
    suppliers()          the supplier directory (real contacts; RFQ override per supplier)
    price_list()         material prices (data/materials.py builds BOM alternatives from it)
    guardrails()         the brand's guardrails (services/guardrails.py evaluates them; unset rules are skipped)
    scoring_weights()    supplier scoring weights (Atelier's default weighting until the brand edits it)
    documents()          brand book files (text extracted locally for grounding; uploaded to the Evolus library)
    sales_history()      past sales, for forecast priors (launch_curves() / size_mix())
    status()             readiness: the studio can approve a design only when ready (require_ready()).

Nothing brand-specific has a default here. The tables hold JSON documents (pydantic models, camelCase).
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from ..config import get_settings
from ..models import Guardrails, now_iso
from ..workspace_models import (BrandDocument, BrandProfile, BrandProfileInput, MaterialPrice, PriceList,
                                Provenance, SalesHistorySummary, SalesRecord, ScoringWeights, SectionStatus, SizePoint,
                                Supplier, SupplierCertification, SupplierConfirmation, SupplierInput, Workspace,
                                WorkspaceStatus)

DB_NAME = "atelier.sqlite3"
DEFAULT_WEIGHTS = {"price": 0.45, "moq": 0.30, "lead_time": 0.25}
DEFAULT_WEIGHTS_LABEL = "default weighting"
MAKER_WORDS = ("cmt", "cut-make-trim", "cut make trim", "full package", "full-package", "garment maker",
               "garment manufacturing", "make-up", "makeup")
GUARDRAIL_RULES = {
    "min_margin": "Gross margin floor",
    "max_unit_cost": "Max unit cost",
    "max_lead_time": "Max lead time",
    "max_moq": "Max MOQ",
    "certifications": "Required certifications",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers (id TEXT PRIMARY KEY, position INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS size_points (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, style TEXT NOT NULL, launch_date TEXT NOT NULL,
                                  week INTEGER NOT NULL, units INTEGER NOT NULL, size TEXT);
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, data TEXT NOT NULL, text TEXT NOT NULL DEFAULT '');
"""

_lock = threading.RLock()
_initialised: set[str] = set()


class NotReady(Exception):
    """The workspace lacks the minimum data to run the studio (message lists what is missing)."""


# --------------------------------------------------------------------------- storage


def data_dir() -> Path:
    return get_settings().data_dir


def db_path() -> Path:
    return data_dir() / DB_NAME


def files_dir() -> Path:
    d = data_dir() / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    path = db_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            if str(path) not in _initialised:
                con.executescript(_SCHEMA)
                _initialised.add(str(path))
            yield con
            con.commit()
        finally:
            con.close()


def _get(key: str) -> Any:
    with _db() as con:
        row = con.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def _put(key: str, value: Any, con: Optional[sqlite3.Connection] = None) -> None:
    if con is None:
        with _db() as c:
            _put(key, value, c)
        return
    con.execute("INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at", (key, json.dumps(value), now_iso()))
    _bump(con)


def _delete(key: str) -> None:
    with _db() as con:
        con.execute("DELETE FROM kv WHERE key = ?", (key,))
        _bump(con)


def _bump(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO kv (key, value, updated_at) VALUES ('revision', '1', ?) ON CONFLICT(key) DO UPDATE SET "
                "value = CAST(CAST(value AS INTEGER) + 1 AS TEXT), updated_at = excluded.updated_at", (now_iso(),))


def revision() -> tuple[str, int]:
    """(db path, write counter): a cache key for anything derived from the workspace (knowledge passages)."""
    with _db() as con:
        row = con.execute("SELECT value FROM kv WHERE key = 'revision'").fetchone()
    return str(db_path()), int(row[0]) if row else 0


def wipe() -> None:
    """Delete everything (DELETE /api/workspace?confirm=DELETE, and tests). Uploaded files are removed too."""
    with _db() as con:
        for t in ("kv", "suppliers", "prices", "size_points", "sales", "documents"):
            con.execute(f"DELETE FROM {t}")  # noqa: S608 - fixed table names
        _bump(con)
    d = data_dir() / "files"
    if d.is_dir():
        for p in d.iterdir():
            if p.is_file():
                p.unlink()


# --------------------------------------------------------------------------- provenance


def provenance(source: str, filename: Optional[str] = None, rows: Optional[int] = None) -> Provenance:
    at = now_iso()
    day = _human_date(at[:10])
    if source == "form":
        label = f"Entered in the workspace on {day}"
    elif source == "upload":
        label = f"Uploaded {filename or 'a file'} on {day}"
    else:
        label = f"Imported from {filename or source.upper()} on {day}" + (f" ({rows} rows)" if rows is not None else "")
    return Provenance(source=source, filename=filename, imported_at=at, rows=rows, label=label)  # type: ignore[arg-type]


def _human_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.day} {d:%b %Y}"


# --------------------------------------------------------------------------- brand profile


def profile() -> Optional[BrandProfile]:
    raw = _get("profile")
    return BrandProfile.model_validate(raw) if raw else None


def save_profile(inp: BrandProfileInput, source: str = "form") -> BrandProfile:
    data = inp.model_dump(by_alias=False)
    data["currency"] = data["currency"].upper()
    data["name"] = data["name"].strip()
    data["target_markets"] = _clean_list(data.get("target_markets"))
    data["default_size_range"] = _clean_list(data.get("default_size_range"))
    p = BrandProfile.model_validate({**data, "provenance": provenance(source), "updated_at": now_iso()})
    _put("profile", p.model_dump(by_alias=True, mode="json"))
    g = guardrails()  # the guardrails are expressed in the brand currency
    if g.currency != p.currency:
        save_guardrails(g.model_copy(update={"currency": p.currency}), by=g.updated_by or "brand profile",
                        review=False)
    return p


def brand_name() -> str:
    p = profile()
    return p.name if p else ""


def persona(role: str) -> str:
    """'You are <brand>'s <role>.' plus the brand's own voice notes - for system prompts. Without a profile the
    prompt names no brand (never a fictional one)."""
    p = profile()
    who = f"You are {p.name}'s {role}." if p else f"You are the brand's {role}."
    voice = (p.voice or "").strip() if p else ""
    return who + (f" House voice (from the brand): {voice[:600]}" if voice else "")


def brand_prompt(role: str) -> str:
    """persona(role) plus the brand facts a tech pack / design brief must respect (only what the brand provided)."""
    p = profile()
    facts: list[str] = []
    if p:
        facts.append(f"currency {p.currency}")
        if p.target_markets:
            facts.append("target markets " + ", ".join(p.target_markets[:8]))
        if p.default_size_range:
            facts.append("size range " + "-".join([p.default_size_range[0], p.default_size_range[-1]])
                         if len(p.default_size_range) > 1 else "size " + p.default_size_range[0])
        if p.colours:
            facts.append("colour standards " + ", ".join(
                f"{c.name} {c.hex}" + (f" ({c.code})" if c.code else "") for c in p.colours[:16]))
        if p.price_architecture:
            pa = p.price_architecture
            facts.append(f"retail = {pa.value:g}x landed cost" if pa.mode == "retail_multiple"
                         else f"target gross margin {pa.value:g}%")
    blocks = sorted({sp.block for sp in size_points()})
    if blocks:
        facts.append("size blocks on file: " + ", ".join(blocks[:10]))
    return persona(role) + (" Brand facts (from the brand's workspace): " + "; ".join(facts) + "." if facts else "")


def delivery_promise_weeks() -> Optional[int]:
    p = profile()
    return p.delivery_promise_weeks if p else None


def preorder_window_days() -> Optional[int]:
    p = profile()
    return p.preorder_window_days if p else None


def size_points() -> list[SizePoint]:
    with _db() as con:
        rows = con.execute("SELECT data FROM size_points ORDER BY id").fetchall()
    return [SizePoint.model_validate(json.loads(r[0])) for r in rows]


def replace_size_points(points: list[SizePoint], prov: Provenance, append: bool = False) -> None:
    with _db() as con:
        if not append:
            con.execute("DELETE FROM size_points")
        con.executemany("INSERT INTO size_points (data) VALUES (?)",
                        [(json.dumps(p.model_dump(by_alias=True, mode="json")),) for p in points])
        _put("provenance:sizes", prov.model_dump(by_alias=True, mode="json"), con)


# --------------------------------------------------------------------------- suppliers


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "supplier"


def _clean_list(items: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for x in items or []:
        t = re.sub(r"\s+", " ", str(x)).strip()
        if t and t.lower() not in (o.lower() for o in out):
            out.append(t)
    return out


def is_maker(categories: list[str], capabilities: list[str] | None = None) -> bool:
    words = " ".join(categories).lower()
    return any(w in words for w in MAKER_WORDS)


def _finish_supplier(s: Supplier) -> Supplier:
    today = date.today().isoformat()
    certs = [c.model_copy(update={"expired": bool(c.expires_on and c.expires_on < today)}) for c in s.certifications]
    return s.model_copy(update={"certifications": certs,
                                "rfq_recipient": (s.rfq_email_override or (s.emails[0] if s.emails else "")).strip(),
                                "maker": is_maker(s.categories, s.capabilities)})


def suppliers() -> list[Supplier]:
    with _db() as con:
        rows = con.execute("SELECT data FROM suppliers ORDER BY position, id").fetchall()
    return [_finish_supplier(Supplier.model_validate(json.loads(r[0]))) for r in rows]


def supplier(supplier_id: str) -> Optional[Supplier]:
    with _db() as con:
        row = con.execute("SELECT data FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    return _finish_supplier(Supplier.model_validate(json.loads(row[0]))) if row else None


def _normalise_supplier(inp: SupplierInput) -> dict:
    d = inp.model_dump(by_alias=False)
    d["name"] = re.sub(r"\s+", " ", d["name"]).strip()
    d["emails"] = _clean_list([e.strip().lower() for e in d["emails"]])
    d["categories"] = _clean_list(d["categories"])
    d["capabilities"] = _clean_list(d["capabilities"])
    d["language"] = (d.get("language") or "en").lower()
    ov = (d.get("rfq_email_override") or "").strip().lower()
    d["rfq_email_override"] = ov or None
    for c in d["certifications"]:
        c.pop("expired", None)
    return d


def _store_supplier(con: sqlite3.Connection, s: Supplier, position: int) -> None:
    data = s.model_dump(by_alias=True, mode="json", exclude={"rfq_recipient", "maker"})
    for c in data.get("certifications", []):
        c.pop("expired", None)
    con.execute("INSERT INTO suppliers (id, position, data) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "data = excluded.data", (s.id, position, json.dumps(data)))


def _unique_id(con: sqlite3.Connection, name: str) -> str:
    base = _slug(name)
    sid, n = base, 2
    while con.execute("SELECT 1 FROM suppliers WHERE id = ?", (sid,)).fetchone():
        sid, n = f"{base}-{n}", n + 1
    return sid


def add_supplier(inp: SupplierInput, prov: Optional[Provenance] = None) -> Supplier:
    with _db() as con:
        sid = _unique_id(con, inp.name)
        pos = (con.execute("SELECT COALESCE(MAX(position), -1) FROM suppliers").fetchone()[0] or 0) + 1
        s = Supplier.model_validate({**_normalise_supplier(inp), "id": sid, "provenance": prov or provenance("form"),
                                     "created_at": now_iso(), "updated_at": now_iso()})
        _store_supplier(con, s, pos)
        _unconfirm(con)
    return _finish_supplier(s)


def update_supplier(supplier_id: str, inp: SupplierInput) -> Supplier:
    with _db() as con:
        row = con.execute("SELECT position, data FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if row is None:
            raise LookupError(f"supplier '{supplier_id}' not found")
        before = Supplier.model_validate(json.loads(row[1]))
        new = _normalise_supplier(inp)
        # Keep uploaded certificate documents when the form re-sends the same certificate without the id.
        docs = {c.name.lower(): c.document_id for c in before.certifications if c.document_id}
        for c in new["certifications"]:
            if not c.get("document_id") and c["name"].lower() in docs:
                c["document_id"] = docs[c["name"].lower()]
        s = Supplier.model_validate({**new, "id": supplier_id, "provenance": before.provenance or provenance("form"),
                                     "created_at": before.created_at, "updated_at": now_iso()})
        _store_supplier(con, s, row[0])
        if (sorted(before.emails) != sorted(s.emails) or before.rfq_email_override != s.rfq_email_override
                or before.name != s.name):
            _unconfirm(con)  # who gets emailed changed: the brand confirms the directory again
    return _finish_supplier(s)


def delete_supplier(supplier_id: str) -> None:
    with _db() as con:
        cur = con.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        if cur.rowcount == 0:
            raise LookupError(f"supplier '{supplier_id}' not found")
        _bump(con)


def replace_suppliers(items: list[SupplierInput], prov: Provenance, append: bool = False) -> list[Supplier]:
    with _db() as con:
        if not append:
            con.execute("DELETE FROM suppliers")
        pos = (con.execute("SELECT COALESCE(MAX(position), -1) FROM suppliers").fetchone()[0] or 0) + 1
        for i, inp in enumerate(items):
            s = Supplier.model_validate({**_normalise_supplier(inp), "id": _unique_id(con, inp.name),
                                         "provenance": prov, "created_at": now_iso(), "updated_at": now_iso()})
            _store_supplier(con, s, pos + i)
        _put("provenance:suppliers", prov.model_dump(by_alias=True, mode="json"), con)
        _unconfirm(con)
    return suppliers()


def set_certificate_document(supplier_id: str, certification: str, document_id: str) -> Supplier:
    s = supplier(supplier_id)
    if s is None:
        raise LookupError(f"supplier '{supplier_id}' not found")
    certs = list(s.certifications)
    hit = next((i for i, c in enumerate(certs) if c.name.lower() == certification.strip().lower()), None)
    if hit is None:
        certs.append(SupplierCertification(name=certification.strip(), document_id=document_id))
    else:
        certs[hit] = certs[hit].model_copy(update={"document_id": document_id})
    inp = SupplierInput.model_validate(s.model_copy(update={"certifications": certs}).model_dump(by_alias=False))
    return update_supplier(supplier_id, inp)


def _unconfirm(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM kv WHERE key = 'suppliers:confirmed'")
    _bump(con)


def confirm_suppliers(actor: str) -> SupplierConfirmation:
    n = len(suppliers())
    if n == 0:
        raise ValueError("add at least one supplier before confirming the directory")
    c = SupplierConfirmation(confirmed_at=now_iso(), confirmed_by=actor, suppliers=n)
    _put("suppliers:confirmed", c.model_dump(by_alias=True, mode="json"))
    return c


def supplier_confirmation() -> SupplierConfirmation:
    raw = _get("suppliers:confirmed")
    return SupplierConfirmation.model_validate(raw) if raw else SupplierConfirmation(suppliers=len(suppliers()))


# --------------------------------------------------------------------------- material price list


def price_list() -> PriceList:
    with _db() as con:
        rows = con.execute("SELECT data FROM prices ORDER BY id").fetchall()
    items = [MaterialPrice.model_validate(json.loads(r[0])) for r in rows]
    raw = _get("provenance:prices")
    return PriceList(items=items, provenance=Provenance.model_validate(raw) if raw else None,
                     dated=max((i.valid_from for i in items), default=None))


def replace_prices(items: list[MaterialPrice], prov: Provenance, append: bool = False) -> PriceList:
    with _db() as con:
        if not append:
            con.execute("DELETE FROM prices")
        con.executemany("INSERT INTO prices (data) VALUES (?)",
                        [(json.dumps(i.model_dump(by_alias=True, mode="json")),) for i in items])
        _put("provenance:prices", prov.model_dump(by_alias=True, mode="json"), con)
    return price_list()


def clear_prices() -> None:
    with _db() as con:
        con.execute("DELETE FROM prices")
        con.execute("DELETE FROM kv WHERE key = 'provenance:prices'")
        _bump(con)


# --------------------------------------------------------------------------- guardrails


def _unset_rules(g: Guardrails) -> list[str]:
    out = []
    if g.min_gross_margin_pct is None:
        out.append("min_margin")
    if g.max_unit_cost is None and g.cost_headroom_pct is None:
        out.append("max_unit_cost")
    if g.max_lead_time_weeks is None:
        out.append("max_lead_time")
    if g.max_moq is None:
        out.append("max_moq")
    if not g.required_certifications:
        out.append("certifications")
    return out


def guardrails() -> Guardrails:
    raw = _get("guardrails")
    p = profile()
    if raw:
        g = Guardrails.model_validate(raw)
    else:
        g = Guardrails(updated_by="not set")
    if p and g.currency != p.currency:
        g = g.model_copy(update={"currency": p.currency})
    return g.model_copy(update={"unset": _unset_rules(g)})


def save_guardrails(g: Guardrails, by: str, review: bool = True) -> Guardrails:
    upd: dict[str, Any] = {"updated_at": now_iso(), "updated_by": by, "unset": []}
    if review:
        upd["reviewed_at"] = now_iso()
    g = g.model_copy(update=upd)
    _put("guardrails", g.model_dump(by_alias=True, mode="json"))
    return guardrails()


def mark_guardrails_reviewed(by: str) -> Guardrails:
    return save_guardrails(guardrails(), by=by)


def clear_guardrails(by: str) -> Guardrails:
    """Every rule back to 'not set' (still counts as reviewed: the brand chose no limits)."""
    p = profile()
    return save_guardrails(Guardrails(currency=p.currency if p else "USD"), by=by)


# --------------------------------------------------------------------------- scoring weights


def scoring_weights() -> ScoringWeights:
    raw = _get("scoring")
    if raw:
        return ScoringWeights.model_validate(raw)
    return ScoringWeights(price=DEFAULT_WEIGHTS["price"], moq=DEFAULT_WEIGHTS["moq"],
                          lead_time=DEFAULT_WEIGHTS["lead_time"], is_default=True, label=DEFAULT_WEIGHTS_LABEL)


def save_scoring_weights(price: float, moq: float, lead_time: float) -> ScoringWeights:
    total = price + moq + lead_time
    if total <= 0:
        raise ValueError("at least one weight must be above zero")
    w = ScoringWeights(price=round(price / total, 4), moq=round(moq / total, 4), lead_time=round(lead_time / total, 4),
                       is_default=False, label="set by the brand", updated_at=now_iso())
    _put("scoring", w.model_dump(by_alias=True, mode="json"))
    return w


def reset_scoring_weights() -> ScoringWeights:
    _delete("scoring")
    return scoring_weights()


# --------------------------------------------------------------------------- documents


def new_document_id() -> str:
    return f"doc_{secrets.token_hex(5)}"


def save_document(doc: BrandDocument, data: bytes, text: str) -> BrandDocument:
    path = files_dir() / f"{doc.id}{Path(doc.filename).suffix.lower()[:8]}"
    path.write_bytes(data)
    with _db() as con:
        con.execute("INSERT INTO documents (id, data, text) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "data = excluded.data, text = excluded.text",
                    (doc.id, json.dumps(doc.model_dump(by_alias=True, mode="json")), text))
        _bump(con)
    return doc


def update_document(doc: BrandDocument) -> None:
    with _db() as con:
        con.execute("UPDATE documents SET data = ? WHERE id = ?",
                    (json.dumps(doc.model_dump(by_alias=True, mode="json")), doc.id))
        _bump(con)


def documents(kind: Optional[str] = None) -> list[BrandDocument]:
    with _db() as con:
        rows = con.execute("SELECT data FROM documents").fetchall()
    docs = [BrandDocument.model_validate(json.loads(r[0])) for r in rows]
    for d in docs:  # the URL follows this server's PUBLIC_BASE_URL (a database copied from a laptop said localhost)
        d.url = get_settings().public_url(f"/api/workspace/documents/{d.id}/file")
    docs.sort(key=lambda d: d.uploaded_at)
    return [d for d in docs if kind is None or d.kind == kind]


def document(doc_id: str) -> Optional[BrandDocument]:
    return next((d for d in documents() if d.id == doc_id), None)


def document_text(doc_id: str) -> str:
    with _db() as con:
        row = con.execute("SELECT text FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row[0] if row else ""


def document_file(doc_id: str) -> Optional[Path]:
    d = document(doc_id)
    if d is None:
        return None
    p = files_dir() / f"{d.id}{Path(d.filename).suffix.lower()[:8]}"
    return p if p.is_file() else None


def delete_document(doc_id: str) -> None:
    p = document_file(doc_id)
    with _db() as con:
        cur = con.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        if cur.rowcount == 0:
            raise LookupError(f"document '{doc_id}' not found")
        _bump(con)
    if p:
        p.unlink(missing_ok=True)


# --------------------------------------------------------------------------- sales history (forecast priors)


def replace_sales(records: list[SalesRecord], prov: Provenance, append: bool = False) -> SalesHistorySummary:
    with _db() as con:
        if not append:
            con.execute("DELETE FROM sales")
        con.executemany("INSERT INTO sales (style, launch_date, week, units, size) VALUES (?, ?, ?, ?, ?)",
                        [(r.style, r.launch_date, r.week, r.units, r.size) for r in records])
        _put("provenance:sales", prov.model_dump(by_alias=True, mode="json"), con)
    return sales_summary()


def clear_sales() -> None:
    with _db() as con:
        con.execute("DELETE FROM sales")
        con.execute("DELETE FROM kv WHERE key = 'provenance:sales'")
        _bump(con)


def sales_history() -> list[SalesRecord]:
    with _db() as con:
        rows = con.execute("SELECT style, launch_date, week, units, size FROM sales ORDER BY style, week, id").fetchall()
    return [SalesRecord(style=r[0], launch_date=r[1], week=r[2], units=r[3], size=r[4]) for r in rows]


def sales_summary() -> SalesHistorySummary:
    with _db() as con:
        n, styles = con.execute("SELECT COUNT(*), COUNT(DISTINCT style) FROM sales").fetchone()
    raw = _get("provenance:sales")
    return SalesHistorySummary(rows=n, styles=styles, provenance=Provenance.model_validate(raw) if raw else None)


def launch_curves(max_weeks: int = 26) -> dict[str, list[int]]:
    """Past sales as launch curves, for fitting forecast priors (services/forecast.py can call this; it does not
    yet). {style: [units in week 1, week 2, …]} - sizes summed, missing weeks 0, at most `max_weeks` weeks.

    Typical use: normalise each curve to its total to get the share of lifetime demand sold by week w (the launch
    curve shape prior), and use the totals' spread across styles as the prior on a new style's total demand."""
    curves: dict[str, list[int]] = {}
    for r in sales_history():
        if r.week > max_weeks:
            continue
        c = curves.setdefault(r.style, [0] * max_weeks)
        c[r.week - 1] += r.units
    for k, c in curves.items():
        last = max((i for i, u in enumerate(c) if u), default=-1)
        curves[k] = c[: last + 1]
    return curves


def size_mix() -> dict[str, float]:
    """Share of units per size across the whole history (rows without a size are ignored); {} when unknown.
    A prior for the forecast's size split."""
    tot: dict[str, int] = {}
    for r in sales_history():
        if r.size:
            tot[r.size] = tot.get(r.size, 0) + r.units
    n = sum(tot.values())
    return {k: round(v / n, 4) for k, v in tot.items()} if n else {}


# --------------------------------------------------------------------------- readiness


def status() -> WorkspaceStatus:
    p = profile()
    sups = suppliers()
    conf = supplier_confirmation()
    g = guardrails()
    pl = price_list()
    books = documents("brand_book")
    sales = sales_summary()
    sizes_prov = _get("provenance:sizes")
    sections: list[SectionStatus] = []
    missing: list[str] = []

    prof_done = bool(p and p.name and p.currency)
    if not prof_done:
        missing.append("a brand profile (name and currency)")
    detail = "not set"
    if p:
        bits = [p.name, p.currency]
        if p.delivery_promise_weeks:
            bits.append(f"{p.delivery_promise_weeks}-week promise")
        if sizes_prov:
            bits.append("size blocks imported")
        detail = " · ".join(bits)
    sections.append(SectionStatus(key="profile", label="Brand profile", required=True, done=prof_done, detail=detail,
                                  provenance=p.provenance if p else None))

    sections.append(SectionStatus(
        key="brand_book", label="Brand book", required=False, done=bool(books),
        detail=f"{len(books)} document{'s' if len(books) != 1 else ''}" if books else "no documents yet",
        provenance=Provenance.model_validate(_doc_prov(books[-1])) if books else None))

    sup_done = bool(sups) and bool(conf.confirmed_at)
    if not sups:
        missing.append("at least one supplier")
    elif not conf.confirmed_at:
        missing.append("confirmation of the supplier contacts (Atelier emails them when you approve a design)")
    raw = _get("provenance:suppliers")
    sections.append(SectionStatus(
        key="suppliers", label="Suppliers", required=True, done=sup_done,
        detail=(f"{len(sups)} supplier{'s' if len(sups) != 1 else ''} · "
                + ("contacts confirmed" if conf.confirmed_at else "contacts not confirmed")) if sups else "none yet",
        provenance=Provenance.model_validate(raw) if raw else (sups[0].provenance if sups else None)))

    sections.append(SectionStatus(
        key="prices", label="Material price list", required=False, done=bool(pl.items),
        detail=f"{len(pl.items)} prices · price list dated {pl.dated}" if pl.items else "no price list",
        provenance=pl.provenance))

    gr_done = bool(g.reviewed_at)
    if not gr_done:
        missing.append("a review of the guardrails")
    set_n = len(GUARDRAIL_RULES) - len(g.unset)
    sections.append(SectionStatus(
        key="guardrails", label="Guardrails", required=True, done=gr_done,
        detail=(f"{set_n} of {len(GUARDRAIL_RULES)} rules set" + (" · reviewed" if gr_done else " · not reviewed")),
        provenance=None))

    sections.append(SectionStatus(
        key="sales", label="Sales history", required=False, done=sales.rows > 0,
        detail=f"{sales.rows} rows · {sales.styles} styles" if sales.rows else "optional · none yet",
        provenance=sales.provenance))
    return WorkspaceStatus(ready=not missing, missing=missing, sections=sections)


def _doc_prov(d: BrandDocument) -> dict:
    return {"source": "upload", "filename": d.filename, "importedAt": d.uploaded_at,
            "label": f"Uploaded {d.filename} on {_human_date(d.uploaded_at[:10])}"}


def require_ready() -> None:
    st = status()
    if not st.ready:
        raise NotReady("The brand workspace isn't set up yet. Add " + "; ".join(st.missing)
                       + " in Brand workspace before approving a design.")


def snapshot() -> Workspace:
    raw = _get("provenance:sizes")
    return Workspace(profile=profile(), size_points=size_points(),
                     size_provenance=Provenance.model_validate(raw) if raw else None, suppliers=suppliers(),
                     supplier_confirmation=supplier_confirmation(), price_list=price_list(), guardrails=guardrails(),
                     scoring=scoring_weights(), documents=documents(), sales=sales_summary(), status=status())


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()
