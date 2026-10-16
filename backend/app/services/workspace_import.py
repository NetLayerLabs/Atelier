"""v5: importers for the Brand workspace - CSV / XLSX tables and brand-book documents.

Tables: `parse_table(kind, filename, data)` -> ImportPreview with the parsed rows (camelCase, for the preview table)
and row-level issues; `commit(...)` stores the valid rows (refused while any row has an error). Headers are matched
loosely (case, spaces, punctuation and a few aliases), so a brand's own export usually works without renaming.
List cells (emails, categories, capabilities, certifications) are separated by ";" (or "|" / newlines).

Documents: `extract_text(filename, data)` -> plain text from PDF (pypdf), DOCX (stdlib zip/XML), Markdown or text,
used for local grounding passages with citations (services/knowledge.py).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime
from typing import Any, Callable, Optional
from xml.etree import ElementTree

from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from ..workspace_models import (ImportIssue, ImportKind, ImportPreview, MaterialPrice, SalesRecord, SizePoint,
                                SupplierCertification, SupplierInput)
from . import workspace

MAX_ROWS = 20_000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Canonical column -> accepted header spellings (normalised: lowercase, non-alphanumerics -> "_").
COLUMNS: dict[str, dict[str, list[str]]] = {
    "suppliers": {
        "name": ["name", "supplier", "supplier_name", "company", "mill", "factory"],
        "city": ["city", "town"],
        "country": ["country"],
        "language": ["language", "lang", "correspondence_language"],
        "contact_emails": ["contact_emails", "contact_email", "emails", "email", "e_mail", "contact"],
        "categories": ["categories", "category", "product_categories"],
        "capabilities": ["capabilities", "capability", "specialty", "speciality"],
        "certifications": ["certifications", "certification", "certificates", "certs"],
        "certificate_expiry": ["certificate_expiry", "certification_expiry", "cert_expiry", "certificate_expiry_dates"],
        "moq": ["moq", "minimum_order_quantity", "min_order_qty"],
        "lead_time_weeks": ["lead_time_weeks", "lead_time", "typical_lead_time_weeks", "lead_time_wks", "lead_weeks"],
        "payment_terms": ["payment_terms", "terms", "payment"],
        "notes": ["notes", "note", "comments"],
        "rfq_email_override": ["rfq_email_override", "rfq_override", "override_email", "rfq_email"],
    },
    "prices": {
        "material": ["material", "material_name", "item", "description"],
        "category": ["category", "family", "material_category"],
        "unit": ["unit", "uom", "unit_of_measure"],
        "price": ["price", "unit_price", "cost", "price_per_unit"],
        "currency": ["currency", "ccy", "cur"],
        "supplier": ["supplier", "supplier_name", "mill", "vendor"],
        "valid_from": ["valid_from", "valid_from_date", "effective_date", "date", "price_date"],
    },
    "sizes": {
        "block": ["block", "size_block", "fit_block", "garment", "garment_type"],
        "point_of_measure": ["point_of_measure", "pom", "measurement", "measure"],
        "size": ["size"],
        "value": ["value", "measurement_value", "spec"],
        "unit": ["unit", "uom"],
        "tolerance": ["tolerance", "tol", "tolerance_plus_minus"],
    },
    "sales": {
        "style": ["style", "style_name", "style_code", "sku", "product"],
        "launch_date": ["launch_date", "launch", "launched", "launch_week"],
        "week": ["week", "week_since_launch", "weeks_since_launch", "launch_week_number"],
        "units": ["units", "qty", "quantity", "units_sold"],
        "size": ["size", "variant_size"],
    },
}
REQUIRED: dict[str, list[str]] = {
    "suppliers": ["name", "contact_emails"],
    "prices": ["material", "category", "unit", "price", "currency", "valid_from"],
    "sizes": ["block", "point_of_measure", "size", "value", "unit"],
    "sales": ["style", "launch_date", "week", "units"],
}
LANGUAGES = {"english": "en", "italian": "it", "italiano": "it", "portuguese": "pt", "português": "pt",
             "spanish": "es", "español": "es", "french": "fr", "français": "fr", "german": "de", "deutsch": "de",
             "japanese": "ja", "chinese": "zh", "mandarin": "zh", "turkish": "tr", "hindi": "hi", "dutch": "nl"}


def template_csv(kind: ImportKind) -> str:
    """Headers only - no example rows (nothing invented)."""
    buf = io.StringIO()
    csv.writer(buf).writerow(list(COLUMNS[kind]))
    return buf.getvalue()


# --------------------------------------------------------------------------- reading tables


def _norm_header(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")


def read_table(filename: str, data: bytes) -> list[list[Any]]:
    """Rows of cells (header first) from CSV / TSV / XLSX."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        try:
            from openpyxl import load_workbook
        except ImportError as e:  # pragma: no cover
            raise ValueError("XLSX support needs openpyxl") from e
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"could not read the spreadsheet: {e}") from e
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return [r for r in rows if any(c not in (None, "") for c in r)]
    if name.endswith(".xls"):
        raise ValueError("old .xls files aren't supported - save as .xlsx or .csv")
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:  # pragma: no cover - latin-1 always decodes
        raise ValueError("could not decode the file")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if name.endswith(".tsv") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return [r for r in rows if any(str(c).strip() for c in r)]


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _split(v: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;|\n]+", v or "") if x.strip()]


def _date(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = _cell(v)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"'{s}' is not a date - use YYYY-MM-DD")


def _number(v: Any, *, integer: bool = False) -> Optional[float]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = re.sub(r"[^\d,.\-]", "", str(v))
        if s.count(",") and s.count("."):  # 1,234.50 or 1.234,50
            s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
        elif s.count(",") == 1 and len(s.split(",")[1]) != 3:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
        try:
            n = float(s)
        except ValueError:
            raise ValueError(f"'{v}' is not a number") from None
    if integer:
        if not float(n).is_integer():
            raise ValueError(f"'{v}' is not a whole number")
        return int(n)
    return n


# --------------------------------------------------------------------------- row parsers (raise ValueError(field, msg))


class RowError(Exception):
    def __init__(self, field: Optional[str], message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _field(name: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ValueError as e:
        raise RowError(name, str(e)) from None


def _pyd(e: ValidationError) -> RowError:
    err = e.errors()[0]
    loc = ".".join(str(x) for x in err.get("loc", []))
    return RowError(loc or None, err.get("msg", "invalid value"))


def _language(v: str) -> str:
    s = v.strip().lower()
    if not s:
        return "en"
    if re.fullmatch(r"[a-z]{2}", s):
        return s
    if s in LANGUAGES:
        return LANGUAGES[s]
    raise ValueError(f"'{v}' - use a two-letter ISO code such as en, it, pt")


def parse_supplier(r: dict[str, Any], warn: list[tuple[str, str]]) -> SupplierInput:
    emails = [e.lower() for e in _split(_cell(r.get("contact_emails")))]
    bad = [e for e in emails if not EMAIL.match(e)]
    if bad:
        raise RowError("contact_emails", f"not an email address: {', '.join(bad)}")
    if not emails:
        raise RowError("contact_emails", "at least one contact email is required")
    override = _cell(r.get("rfq_email_override")).lower()
    if override and not EMAIL.match(override):
        raise RowError("rfq_email_override", f"not an email address: {override}")
    expiry: dict[str, str] = {}
    for part in _split(_cell(r.get("certificate_expiry"))):
        if "=" not in part and ":" not in part:
            raise RowError("certificate_expiry", f"'{part}' - write CERTIFICATE=YYYY-MM-DD")
        k, v = re.split(r"[=:]", part, maxsplit=1)
        expiry[k.strip().lower()] = _field("certificate_expiry", lambda v=v: _date(v.strip()))  # type: ignore[misc]
    certs = []
    for c in _split(_cell(r.get("certifications"))):
        certs.append(SupplierCertification(name=c[:80], expires_on=expiry.pop(c.lower(), None)))
    today = date.today().isoformat()
    for c in certs:
        if c.expires_on and c.expires_on < today:
            warn.append(("certificate_expiry", f"{c.name} expired on {c.expires_on} - it won't count for guardrails"))
    for k in expiry:
        warn.append(("certificate_expiry", f"expiry given for '{k}', which is not in the certifications column"))
    moq = _field("moq", lambda: _number(r.get("moq"), integer=True))
    lead = _field("lead_time_weeks", lambda: _number(r.get("lead_time_weeks"), integer=True))
    lang = _field("language", lambda: _language(_cell(r.get("language"))))
    if not _cell(r.get("city")) and not _cell(r.get("country")):
        warn.append(("country", "no city or country"))
    try:
        return SupplierInput(name=_cell(r.get("name")), city=_cell(r.get("city")), country=_cell(r.get("country")),
                             language=lang, emails=emails, categories=_split(_cell(r.get("categories"))),
                             capabilities=_split(_cell(r.get("capabilities"))), certifications=certs,
                             moq=moq, lead_time_weeks=lead, payment_terms=_cell(r.get("payment_terms")),
                             notes=_cell(r.get("notes")), rfq_email_override=override or None)
    except ValidationError as e:
        raise _pyd(e) from None


def parse_price(r: dict[str, Any], warn: list[tuple[str, str]]) -> MaterialPrice:
    price = _field("price", lambda: _number(r.get("price")))
    if price is None or price <= 0:
        raise RowError("price", "price must be a number above zero")
    cur = _cell(r.get("currency")).upper()
    if not re.fullmatch(r"[A-Z]{3}", cur):
        raise RowError("currency", f"'{cur or '(empty)'}' - use a three-letter ISO code such as EUR, USD")
    valid = _field("valid_from", lambda: _date(r.get("valid_from")))
    if not valid:
        raise RowError("valid_from", "valid-from date is required (YYYY-MM-DD)")
    sup = _cell(r.get("supplier"))
    if sup and not any(s.name.lower() == sup.lower() for s in workspace.suppliers()):
        warn.append(("supplier", f"'{sup}' is not in the supplier directory"))
    for k in ("material", "category", "unit"):
        if not _cell(r.get(k)):
            raise RowError(k, f"{k.replace('_', ' ')} is required")
    return MaterialPrice(material=_cell(r.get("material")), category=_cell(r.get("category")), unit=_cell(r.get("unit")),
                         price=price, currency=cur, supplier=sup, valid_from=valid)


def parse_size(r: dict[str, Any], warn: list[tuple[str, str]]) -> SizePoint:
    value = _field("value", lambda: _number(r.get("value")))
    if value is None:
        raise RowError("value", "measurement value is required")
    tol = _field("tolerance", lambda: _number(r.get("tolerance")))
    for k in ("block", "point_of_measure", "size", "unit"):
        if not _cell(r.get(k)):
            raise RowError(k, f"{k.replace('_', ' ')} is required")
    unit = _cell(r.get("unit")).lower()
    if unit not in ("cm", "mm", "in", "inch", "inches"):
        warn.append(("unit", f"unusual unit '{unit}'"))
    return SizePoint(block=_cell(r.get("block")), point_of_measure=_cell(r.get("point_of_measure")),
                     size=_cell(r.get("size")), value=value, unit=unit, tolerance=tol)


def parse_sale(r: dict[str, Any], warn: list[tuple[str, str]]) -> SalesRecord:
    launch = _field("launch_date", lambda: _date(r.get("launch_date")))
    if not launch:
        raise RowError("launch_date", "launch date is required (YYYY-MM-DD)")
    week = _field("week", lambda: _number(r.get("week"), integer=True))
    if week is None or week < 1:
        raise RowError("week", "week since launch must be 1 or more")
    units = _field("units", lambda: _number(r.get("units"), integer=True))
    if units is None or units < 0:
        raise RowError("units", "units must be 0 or more")
    if not _cell(r.get("style")):
        raise RowError("style", "style is required")
    return SalesRecord(style=_cell(r.get("style")), launch_date=launch, week=int(week), units=int(units),
                       size=_cell(r.get("size")) or None)


PARSERS: dict[str, Callable[[dict[str, Any], list[tuple[str, str]]], Any]] = {
    "suppliers": parse_supplier, "prices": parse_price, "sizes": parse_size, "sales": parse_sale}


# --------------------------------------------------------------------------- preview + commit


def parse_table(kind: ImportKind, filename: str, data: bytes) -> tuple[ImportPreview, list[Any]]:
    """(preview, parsed items of the valid rows)."""
    preview = ImportPreview(kind=kind, filename=filename)
    try:
        table = read_table(filename, data)
    except ValueError as e:
        preview.issues.append(ImportIssue(row=0, message=str(e)))
        return preview, []
    if not table:
        preview.issues.append(ImportIssue(row=0, message="the file is empty"))
        return preview, []
    header = [_norm_header(h) for h in table[0]]
    aliases = {a: canon for canon, names in COLUMNS[kind].items() for a in names}
    colmap: dict[int, str] = {}
    for i, h in enumerate(header):
        canon = aliases.get(h)
        if canon and canon not in colmap.values():
            colmap[i] = canon
        elif h:
            preview.ignored_columns.append(str(table[0][i]))
    preview.columns = list(colmap.values())
    missing = [c for c in REQUIRED[kind] if c not in colmap.values()]
    if missing:
        preview.issues.append(ImportIssue(row=0, message="missing column(s): " + ", ".join(missing)
                                          + f" - download the {kind} template for the expected headers"))
        return preview, []
    body = table[1:]
    if len(body) > MAX_ROWS:
        preview.issues.append(ImportIssue(row=0, message=f"too many rows ({len(body)}; max {MAX_ROWS})"))
        return preview, []
    items: list[Any] = []
    seen: set[str] = set()
    for n, raw in enumerate(body, 1):
        r = {canon: (raw[i] if i < len(raw) else None) for i, canon in colmap.items()}
        warn: list[tuple[str, str]] = []
        try:
            item = PARSERS[kind](r, warn)
        except RowError as e:
            preview.issues.append(ImportIssue(row=n, field=e.field, message=e.message))
            preview.rows.append({"_row": n, "_error": True, **{to_camel(k): _cell(v) for k, v in r.items()}})
            continue
        if kind == "suppliers":
            key = item.name.lower()
            if key in seen:
                preview.issues.append(ImportIssue(row=n, field="name", message=f"duplicate supplier '{item.name}'"))
                preview.rows.append({"_row": n, "_error": True, **{to_camel(k): _cell(v) for k, v in r.items()}})
                continue
            seen.add(key)
        for f, m in warn:
            preview.issues.append(ImportIssue(row=n, field=f, message=m, level="warning"))
        items.append(item)
        preview.rows.append({"_row": n, **_display(kind, item)})
    preview.valid_rows = len(items)
    if not body:
        preview.issues.append(ImportIssue(row=0, message="no data rows under the header"))
    return preview, items


def _display(kind: str, item: Any) -> dict[str, Any]:
    """A parsed row as strings keyed like the template columns (camelCase), for the preview table."""
    if kind == "suppliers":
        return {"name": item.name, "city": item.city, "country": item.country, "language": item.language,
                "contactEmails": "; ".join(item.emails), "categories": "; ".join(item.categories),
                "capabilities": "; ".join(item.capabilities),
                "certifications": "; ".join(c.name + (f" (exp. {c.expires_on})" if c.expires_on else "")
                                            for c in item.certifications),
                "moq": item.moq, "leadTimeWeeks": item.lead_time_weeks, "paymentTerms": item.payment_terms,
                "notes": item.notes, "rfqEmailOverride": item.rfq_email_override or ""}
    return item.model_dump(by_alias=True, mode="json")


def has_errors(preview: ImportPreview) -> bool:
    return any(i.level == "error" for i in preview.issues)


def commit(kind: ImportKind, filename: str, items: list[Any], append: bool) -> Any:
    src = "xlsx" if filename.lower().endswith((".xlsx", ".xlsm")) else "csv"
    prov = workspace.provenance(src, filename, rows=len(items))
    if kind == "suppliers":
        workspace.replace_suppliers(items, prov, append=append)
    elif kind == "prices":
        workspace.replace_prices(items, prov, append=append)
    elif kind == "sizes":
        workspace.replace_size_points(items, prov, append=append)
    elif kind == "sales":
        workspace.replace_sales(items, prov, append=append)
    return prov


# --------------------------------------------------------------------------- documents -> text


DOC_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}


def extract_text(filename: str, data: bytes) -> str:
    """Plain text (Markdown kept as-is) for local grounding. Raises ValueError for unsupported / unreadable files."""
    ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == ".pdf" or data[:5] == b"%PDF-":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(p.extract_text() or "").strip() for p in reader.pages]
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"could not read the PDF: {e}") from e
        # One "## Page n" section per page, so citations can point at a page.
        return "\n\n".join(f"## Page {i}\n\n{t}" for i, t in enumerate(pages, 1) if t)
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError) as e:
            raise ValueError("not a readable .docx file") from e
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        root = ElementTree.fromstring(xml)
        out: list[str] = []
        for p in root.iter(f"{ns}p"):
            style = p.find(f"{ns}pPr/{ns}pStyle")
            text = "".join(t.text or "" for t in p.iter(f"{ns}t")).strip()
            if not text:
                continue
            sv = (style.get(f"{ns}val") or "").lower() if style is not None else ""
            m = re.match(r"heading(\d)", sv)
            if m:
                out.append("#" * min(int(m.group(1)) + 1, 3) + " " + text)
            elif sv == "title":
                out.append("# " + text)
            else:
                out.append(text)
        return "\n\n".join(out)
    if ext in (".md", ".markdown", ".txt"):
        return data.decode("utf-8", errors="replace")
    raise ValueError("upload a PDF, DOCX or Markdown file")
