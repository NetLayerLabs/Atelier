"""Factory-style tech pack PDF (ReportLab).

Cover (design render, style no., revision) -> BOM & costing -> points of measure & construction
-> colourways, supplier & quantities. Designs are PNG renders from the diffusion server; if the image can't be
loaded, the cover shows the palette with a label saying so.

v5: everything on the page comes from the run - the brain's tech pack (incl. its own construction notes, omitted
when it gave none), the mill's quote ("not stated" where the document is silent), the style number from the brand's
persisted sequence, and a size breakdown only when real sized pre-orders exist (the forecast's size split).
No invented tolerances, season labels, TCX matches or footers.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import httpx
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from ..config import STATIC_DIR
from ..models import Design, PipelineRun, TechPack, TrendAnalysis
from . import money, sourcing
from .direction import effective_trend
from .colors import normalize_hex, rgb
from .sizes import label as size_label, size_range

log = logging.getLogger("atelier.pdf")
_DASH = re.compile(r" [-\u2014] ")  # "change - reason" (older text used an em dash)

PAGE = landscape(A4)
W, H = PAGE
M = 16 * mm

INK = colors.HexColor("#17161A")
MUTED = colors.HexColor("#6B655C")
FAINT = colors.HexColor("#9A9389")
RULE = colors.HexColor("#D9D3C7")
PAPER = colors.HexColor("#FBF9F5")
TINT = colors.HexColor("#F3EEE6")
ACCENT = colors.HexColor("#A88A55")

SERIF, SERIF_I, SANS, SANS_B, MONO = "Times-Roman", "Times-Italic", "Helvetica", "Helvetica-Bold", "Courier"

# --------------------------------------------------------------------------- helpers


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stated(v, fmt="{}") -> str:
    return fmt.format(v) if v not in (None, "") else "not stated"


def size_breakdown(run: PipelineRun, quantity: int) -> tuple[list[tuple[str, int]], str] | None:
    """The forecast's size split applied to `quantity` - only when real sized pre-orders exist. None otherwise."""
    if run.demand is None or not any(e.size for e in run.demand.order_events):
        return None
    try:
        from . import forecast as fc

        fcast = fc.forecast(fc.request_for_run(run))
    except Exception as e:  # noqa: BLE001
        log.warning("tech pack PDF: no size split (%s)", e)
        return None
    shares = {x.size: x.share for x in fcast.sizes}
    if not shares or quantity <= 0:
        return None
    units = fc.largest_remainder(shares, quantity)
    n = fcast.explanation.data.sized_orders
    return ([(k, units.get(k, 0)) for k in shares],
            f"from {n} sized pre-order{'s' if n != 1 else ''} (forecast size split, smoothed toward the base curve)")


def _load_image_bytes(url: str) -> tuple[bytes, str] | None:
    """Return (bytes, kind) where kind is 'svg' or 'raster'."""
    try:
        if url.startswith("data:"):
            header, _, payload = url.partition(",")
            data = base64.b64decode(payload) if ";base64" in header else unquote(payload).encode()
            return data, "svg" if "svg" in header else "raster"
        path = urlparse(url).path
        if path.startswith("/static/"):
            local = (STATIC_DIR / path[len("/static/"):]).resolve()
            if STATIC_DIR.resolve() in local.parents and local.is_file():
                data = local.read_bytes()
                return data, "svg" if local.suffix.lower() == ".svg" else "raster"
        if url.startswith(("http://", "https://")):
            r = httpx.get(url, timeout=5.0, follow_redirects=True)
            r.raise_for_status()
            kind = "svg" if "svg" in r.headers.get("content-type", "") or path.endswith(".svg") else "raster"
            return r.content, kind
    except Exception as e:  # noqa: BLE001
        log.warning("tech pack PDF: could not load design image %s: %s", url[:80], e)
    return None


def _draw_design(c, url: str, x: float, y: float, w: float, h: float, palette: list[str]) -> bool:
    """Draw the design render fitted into the box; palette block on failure. Returns True if the image drew."""
    loaded = _load_image_bytes(url) if url else None
    if loaded:
        data, kind = loaded
        try:
            if kind == "svg":
                raise ValueError("not a diffusion render (SVG)")
            img = ImageReader(io.BytesIO(data))
            iw, ih = img.getSize()
            s = min(w / iw, h / ih)
            c.drawImage(img, x + (w - iw * s) / 2, y + (h - ih * s) / 2, iw * s, ih * s, mask="auto")
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("tech pack PDF: image conversion failed, using palette block: %s", e)
    # fallback: palette block
    cols = [normalize_hex(p) for p in palette if normalize_hex(p)] or ["#2A2724", "#C9B79C"]
    band = h / len(cols)
    for i, col in enumerate(cols):
        c.setFillColor(colors.HexColor(col))
        c.rect(x, y + h - (i + 1) * band, w, band, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(SANS, 7)
    c.drawString(x + 8, y + 8, "DESIGN RENDER UNAVAILABLE - PALETTE SHOWN")
    return False


# --------------------------------------------------------------------------- document


class _Ctx:
    def __init__(self, run: PipelineRun, tp: TechPack, design: Design, trend: TrendAnalysis | None):
        # The trend as this design sees it: a creative direction (or collection look) may have re-coloured it and
        # swapped its fabrics, and the factory must make what was directed, not the original mood board.
        self.trend = effective_trend(trend, design) if trend else None
        self.run, self.tp, self.design = run, tp, design
        self.now = datetime.now(timezone.utc)
        self.style_no = run.style_number or "not assigned"
        self.rev = run.tech_pack_revision
        self.rev_date = self.now.strftime("%d %b %Y")
        palette = tp.colorway or (self.trend.color_palette if self.trend else [])
        self.palette = [p for p in palette if normalize_hex(p)] or ["#2A2724"]
        self.unit_cost = sourcing.unit_cost(tp)
        self.quote = sourcing.selected_quote(run.quotes, run.recommendation)
        # Every cost and price on the tech pack is in the brand currency (Brand workspace profile).
        self.currency = tp.currency or money.brand_currency()

    def money(self, x: float, dp: int = 2) -> str:
        return money.fmt(x, self.currency, dp)


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "h": ParagraphStyle("h", fontName=SERIF, fontSize=20, leading=24, textColor=INK, spaceAfter=2),
        "kicker": ParagraphStyle("k", fontName=SANS, fontSize=7, leading=9, textColor=ACCENT, spaceAfter=4,
                                 tracking=1.2),
        "body": ParagraphStyle("b", fontName=SANS, fontSize=8.5, leading=12, textColor=INK),
        "muted": ParagraphStyle("m", fontName=SANS, fontSize=7.5, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("c", fontName=SANS, fontSize=8, leading=10.5, textColor=INK),
        "cellm": ParagraphStyle("cm", fontName=SANS, fontSize=7.5, leading=10.5, textColor=MUTED),
        "cellr": ParagraphStyle("cr", fontName=SANS, fontSize=8, leading=10.5, textColor=INK, alignment=TA_RIGHT),
        "th": ParagraphStyle("th", fontName=SANS, fontSize=6.5, leading=8, textColor=MUTED),
        "thr": ParagraphStyle("thr", fontName=SANS, fontSize=6.5, leading=8, textColor=MUTED, alignment=TA_RIGHT),
    }


def _section(title: str, kicker: str, st) -> list:
    return [Paragraph(kicker.upper(), st["kicker"]), Paragraph(_esc(title), st["h"]), Spacer(1, 8)]


def _table(rows: list[list], widths: list[float], *, numeric_cols: tuple[int, ...] = (), total_rows: int = 0,
           zebra: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, 0), SANS, 6.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1 - total_rows), 0.4, RULE),
    ]
    for col in numeric_cols:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    if zebra:
        for r in range(1, len(rows) - total_rows):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), TINT))
    if total_rows:
        style += [("LINEABOVE", (0, -total_rows), (-1, -total_rows), 0.8, INK),
                  ("FONT", (0, -total_rows), (-1, -1), SANS_B, 8)]
    t.setStyle(TableStyle(style))
    return t


def _cover(c, doc) -> None:
    ctx: _Ctx = doc._atelier
    tp, run = ctx.tp, ctx.run
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    # left: design render on a tinted panel
    img_w = W * 0.42
    c.setFillColor(TINT)
    c.rect(0, 0, img_w, H, stroke=0, fill=1)
    _draw_design(c, ctx.design.image_url, M, M, img_w - 2 * M, H - 2 * M, ctx.palette)

    x = img_w + 14 * mm
    right = W - M
    # wordmark + doc type
    c.setFillColor(INK)
    c.setFont(SERIF, 13)
    c.drawString(x, H - M - 6, "A T E L I E R")
    c.setFont(SANS, 7)
    c.setFillColor(MUTED)
    c.drawRightString(right, H - M - 4, f"TECH PACK  ·  REV {ctx.rev:02d}  ·  {ctx.rev_date.upper()}")
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.line(x, H - M - 14, right, H - M - 14)

    # title block
    y = H - M - 70
    c.setFillColor(ACCENT)
    c.setFont(SANS, 7.5)
    c.drawString(x, y + 26, f"STYLE {ctx.style_no}")
    c.setFillColor(INK)
    size = 40 if len(tp.garment_name) <= 20 else 30
    c.setFont(SERIF, size)
    c.drawString(x, y - 14, tp.garment_name)
    if ctx.trend:
        c.setFont(SERIF_I, 14)
        c.setFillColor(MUTED)
        c.drawString(x, y - 36, f"from the “{ctx.trend.trend_name}” story")

    # description
    desc = Paragraph(_esc(tp.description), ParagraphStyle("d", fontName=SANS, fontSize=8.5, leading=12.5,
                                                          textColor=INK))
    dw, dh = desc.wrap(right - x, 120)
    desc.drawOn(c, x, y - 52 - dh)

    # design brief: what the factory needs to know at a glance
    brief: list[tuple[str, str]] = []
    if ctx.trend:
        brief.append(("Silhouette", " · ".join(ctx.trend.core_silhouettes[:3])))
        brief.append(("Key fabrics", " · ".join(ctx.trend.key_fabrics[:3])))
    if ctx.design.vibe:
        brief.append(("Creative direction", f"“{ctx.design.vibe}”"))
    brief.append(("Sourcing region", tp.target_supplier_region))
    by = y - 52 - dh - 26
    lab = ParagraphStyle("bl", fontName=SANS, fontSize=6.2, leading=8, textColor=MUTED)
    val = ParagraphStyle("bv", fontName=SERIF, fontSize=11, leading=13.5, textColor=INK)
    for k, v in brief:
        if by < M + 186:
            break
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(x, by + 10, right, by + 10)
        lp = Paragraph(k.upper(), lab)
        lp.wrap(90, 20)
        lp.drawOn(c, x, by - 4)
        vp = Paragraph(_esc(v), val)
        _, vh = vp.wrap(right - x - 100, 60)
        vp.drawOn(c, x + 100, by + 4 - vh)
        by -= max(vh, 12) + 14

    # key facts grid
    margin = (tp.target_retail_price - ctx.unit_cost) / tp.target_retail_price if tp.target_retail_price else 0
    facts = [
        ("Garment", ctx.design.garment_type.title()),
        ("Size range", size_label(size_range(tp))),
        ("Production qty", f"{tp.production_quantity:,} units"),
        ("Target cost (BOM)", ctx.money(ctx.unit_cost)),
        ("Target retail", ctx.money(tp.target_retail_price, 0)),
        ("Target margin", f"{margin:.0%}"),
        ("Supplier", ctx.quote.supplier_name if ctx.quote else "awaiting quotes"),
        ("Lead time", _stated(ctx.quote.lead_time_weeks, "{} weeks") if ctx.quote else "-"),
        ("Brain", tp.generated_by or "-"),
    ]
    gy = M + 126
    cols = 3
    cw = (right - x) / cols
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    for i, (k, v) in enumerate(facts):
        cx_, row = x + (i % cols) * cw, i // cols
        cy = gy - row * 34
        c.line(cx_, cy + 24, cx_ + cw - 8, cy + 24)
        c.setFont(SANS, 6.2)
        c.setFillColor(MUTED)
        c.drawString(cx_, cy + 14, k.upper())
        # shrink long values to the cell, then truncate as a last resort
        size, avail = 12.0, cw - 10
        while size > 8.5 and stringWidth(v, SERIF, size) > avail:
            size -= 0.5
        val = v
        while stringWidth(val, SERIF, size) > avail and len(val) > 4:
            val = val[:-2].rstrip() + "…"
        c.setFont(SERIF, size)
        c.setFillColor(INK)
        c.drawString(cx_, cy, val)

    # palette chips
    chip_y = M + 8
    c.setFont(SANS, 6.2)
    c.setFillColor(MUTED)
    c.drawString(x, chip_y + 30, "COLOURWAY")
    for i, col in enumerate(ctx.palette[:6]):
        cx_ = x + i * 62
        c.setFillColor(colors.HexColor(normalize_hex(col)))
        c.setStrokeColor(RULE)
        c.rect(cx_, chip_y + 8, 18, 16, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont(MONO, 6.5)
        c.drawString(cx_ + 22, chip_y + 18, normalize_hex(col) or col)
        c.setFont(SANS, 6)
        c.setFillColor(MUTED)
        r_, g_, b_ = rgb(col)
        c.drawString(cx_ + 22, chip_y + 10, f"RGB {r_} {g_} {b_}")
    c.setFont(SANS, 6)
    c.setFillColor(FAINT)
    c.drawRightString(right, M - 8, f"{run.id} · generated by the Atelier agent · confidential")
    c.restoreState()


def _body_page(c, doc) -> None:
    ctx: _Ctx = doc._atelier
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont(SERIF, 10)
    c.drawString(M, H - M + 2, "A T E L I E R")
    c.setFont(SANS, 7)
    c.setFillColor(MUTED)
    c.drawString(M + 80, H - M + 3, f"{ctx.tp.garment_name.upper()}  ·  STYLE {ctx.style_no}")
    c.drawRightString(W - M, H - M + 3, f"REV {ctx.rev:02d}  ·  {ctx.rev_date.upper()}")
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.line(M, H - M - 4, W - M, H - M - 4)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.4)
    c.line(M, M - 2, W - M, M - 2)
    c.setFont(SANS, 6.5)
    c.setFillColor(FAINT)
    c.drawString(M, M - 12, f"Tech pack written by {ctx.tp.generated_by or 'the brain'} · supplier terms from "
                            f"the mill's own quote document · run {ctx.run.id}")
    c.drawRightString(W - M, M - 12, f"PAGE {doc.page}")
    c.restoreState()


def build_techpack_pdf(run: PipelineRun, tp: TechPack, design: Design, trend: TrendAnalysis | None) -> bytes:
    buf = io.BytesIO()
    ctx = _Ctx(run, tp, design, trend)
    st = _styles()
    doc = BaseDocTemplate(buf, pagesize=PAGE, leftMargin=M, rightMargin=M, topMargin=M + 10, bottomMargin=M + 4,
                          title=f"{tp.garment_name} - Tech Pack {ctx.style_no}", author="Atelier",
                          subject=f"Tech pack rev {ctx.rev:02d}", creator="Atelier agent (ReportLab)")
    doc._atelier = ctx  # type: ignore[attr-defined]
    frame = Frame(M, M + 4, W - 2 * M, H - 2 * M - 14, id="body", leftPadding=0, rightPadding=0, topPadding=0,
                  bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(0, 0, W, H, id="cv")], onPage=_cover),
        PageTemplate(id="body", frames=[frame], onPage=_body_page),
    ])
    story: list = [Spacer(1, 1), NextPageTemplate("body"), PageBreak()]
    full = W - 2 * M

    # ---- BOM & costing
    story += _section("Bill of materials & costing", "01 - Materials", st)
    qty = tp.production_quantity
    rows: list[list] = [[Paragraph("#", st["th"]), Paragraph("MATERIAL / PLACEMENT", st["th"]),
                         Paragraph("CONSUMPTION", st["th"]), Paragraph("COST / GARMENT", st["thr"]),
                         Paragraph(f"EXTENDED × {qty:,}", st["thr"]), Paragraph("% OF COST", st["thr"])]]
    for i, b in enumerate(tp.bill_of_materials, 1):
        share = b.target_cost_per_unit / ctx.unit_cost if ctx.unit_cost else 0
        rows.append([Paragraph(f"{i:02d}", st["cellm"]), Paragraph(_esc(b.material), st["cell"]),
                     Paragraph(_esc(b.quantity), st["cellm"]), Paragraph(ctx.money(b.target_cost_per_unit), st["cellr"]),
                     Paragraph(ctx.money(b.target_cost_per_unit * qty, 0), st["cellr"]),
                     Paragraph(f"{share:.0%}", st["cellr"])])
    rows.append(["", "Total per garment", "", ctx.money(ctx.unit_cost), ctx.money(ctx.unit_cost * qty, 0), "100%"])
    story.append(_table(rows, [0.04 * full, 0.5 * full, 0.13 * full, 0.11 * full, 0.13 * full, 0.09 * full],
                        numeric_cols=(3, 4, 5), total_rows=1))
    story.append(Spacer(1, 14))

    retail = tp.target_retail_price
    margin = (retail - ctx.unit_cost) / retail if retail else 0
    break_even = math.ceil(ctx.unit_cost * qty / retail) if retail else 0
    cost_rows = [[f"COSTING SUMMARY ({ctx.currency})" if ctx.currency else "COSTING SUMMARY", ""],
                 ["Target cost (BOM, model costing)", ctx.money(ctx.unit_cost)],
                 ["Target retail (pre-order)", ctx.money(retail)],
                 ["Gross margin", f"{margin:.1%}  ({ctx.money(retail - ctx.unit_cost)} / unit)"],
                 ["Total production cost", ctx.money(ctx.unit_cost * qty, 0)],
                 ["Break-even (units sold)", f"{break_even:,} of {qty:,}"]]
    if ctx.quote and ctx.quote.unit_price is not None:
        q_margin = (retail - ctx.quote.unit_price) / retail if retail else 0
        cost_rows.append(["Quoted unit price (selected supplier)", f"{ctx.money(ctx.quote.unit_price)}  ·  margin {q_margin:.1%}"])
    ct = Table(cost_rows, colWidths=[0.22 * full, 0.26 * full])
    ct.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), SANS, 6.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("FONT", (0, 1), (0, -1), SANS, 8), ("TEXTCOLOR", (0, 1), (0, -1), MUTED),
        ("FONT", (1, 1), (1, -1), SANS_B, 8.5), ("TEXTCOLOR", (1, 1), (1, -1), INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    ct.hAlign = "LEFT"
    story.append(KeepTogether(ct))

    # ---- POM & construction
    story += [PageBreak()] + _section("Points of measure & construction", "02 - Fit", st)
    pom_rows: list[list] = [[Paragraph(h, st["th"]) for h in ("CODE", "POINT OF MEASURE", "SAMPLE")]]
    for i, (k, v) in enumerate(tp.measurements.items(), 1):
        pom_rows.append([Paragraph(f"POM-{i:02d}", st["cellm"]), Paragraph(_esc(k.capitalize()), st["cell"]),
                         Paragraph(_esc(v), st["cell"])])
    pom = _table(pom_rows, [0.07 * full, 0.27 * full, 0.22 * full])
    notes: list = []
    if tp.construction_notes:  # the brain's own construction notes; the section is omitted when it gave none
        notes += [Paragraph("CONSTRUCTION NOTES", st["th"]), Spacer(1, 6)]
        for n in tp.construction_notes:
            notes.append(Paragraph(f"<font color='#A88A55'>-</font>&nbsp; {_esc(n)}", st["body"]))
            notes.append(Spacer(1, 5))
    if design.vibe:
        notes += [Spacer(1, 4), Paragraph("CREATIVE DIRECTION", st["th"]), Spacer(1, 4),
                  Paragraph(f"<i>“{_esc(design.vibe)}”</i>", st["body"])]
    if tp.customer_evidence:  # v3: customer-voice changes, with their counts and a cited quote
        notes += [Spacer(1, 8), Paragraph("CUSTOMER EVIDENCE", st["th"]), Spacer(1, 4)]
        for ev in tp.customer_evidence[:8]:
            where = f" · {_esc(ev.garment_class)}" if ev.garment_class else ""
            notes.append(Paragraph(f"<font color='#A88A55'>-</font>&nbsp; <b>{_esc(ev.title)}</b>: "
                                   f"{_esc(ev.instruction or _DASH.split(ev.tech_pack_change, maxsplit=1)[0])}", st["body"]))
            q = ev.quotes[0] if ev.quotes else None
            notes.append(Paragraph(f"{ev.count} of {ev.base}{where} ({ev.share:g}%) · {_esc(ev.source)}"
                                   + (f" · “{_esc(q.text[:160])}{'…' if len(q.text) > 160 else ''}” "
                                      f"[{_esc(q.record_id)}]" if q else ""), st["muted"]))
            notes.append(Spacer(1, 4))
    layout = Table([[pom, notes or [Spacer(1, 1)]]], colWidths=[0.58 * full, 0.42 * full])
    layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (0, 0), 18), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    story.append(layout)

    # ---- colourways, supplier & quantities
    story += [PageBreak()] + _section("Colourways, supplier & quantities", "03 - Sourcing", st)
    cw_rows: list[list] = [[Paragraph(h, st["th"]) for h in ("", "#", "HEX", "RGB")]]
    for i, col in enumerate(ctx.palette[:6]):
        hx = normalize_hex(col)
        r_, g_, b_ = rgb(hx)
        cw_rows.append(["", Paragraph(f"{i + 1:02d}", st["cellm"]),
                        Paragraph(f"<font face='Courier'>{hx}</font>", st["cell"]),
                        Paragraph(f"{r_} / {g_} / {b_}", st["cellm"])])
    cwt = _table(cw_rows, [0.05 * full, 0.06 * full, 0.12 * full, 0.16 * full], zebra=False)
    for i, col in enumerate(ctx.palette[:6], 1):
        cwt.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), colors.HexColor(normalize_hex(col))),
                                 ("BOX", (0, i), (0, i), 0.4, RULE)]))

    sup_rows: list[list] = [["SUPPLIER & ORDER", ""]]
    q = ctx.quote
    if q:
        quoted = (money.fmt(q.unit_price_quoted, q.currency) if q.unit_price_quoted is not None and q.currency
                  else ctx.money(q.unit_price) if q.unit_price is not None else "not stated")
        if (q.currency and ctx.currency and q.currency.upper() != ctx.currency.upper()
                and q.unit_price is not None and q.unit_price_quoted is not None):
            quoted += f" ≈ {ctx.money(q.unit_price)}"
        sup_rows += [["Supplier", q.supplier_name], ["Region", q.region or "not stated"],
                     ["Quoted unit price", quoted + (f" (quote {q.quote_number})" if q.quote_number else "")],
                     ["MOQ", _stated(f"{q.moq:,}" if q.moq else None, "{} units")],
                     ["Lead time", _stated(q.lead_time_weeks, "{} weeks")],
                     ["Sample cost", _stated(f"{q.sample_cost_quoted:,.0f}" if q.sample_cost_quoted is not None
                                             else None, f"{q.currency or ''} {{}}")],
                     ["Payment terms", _stated(q.payment_terms)]]
        if run.recommendation and run.recommendation.overridden:
            sup_rows.append(["Selection", f"Creative director override (agent recommended "
                                          f"{run.recommendation.supplier_name})"])
        elif run.recommendation:
            sup_rows.append(["Selection", f"Agent recommendation · score {q.score:.0f}/100"])
    else:
        sup_rows += [["Target region", tp.target_supplier_region], ["Status", "Awaiting quotes"]]
    po = run.demand.purchase_order if run.demand else None
    order_qty = po.quantity if po else max(qty, (q.moq or 0) if q else 0)
    sup_rows.append(["Order quantity", f"{order_qty:,} units"])
    if po:
        state = {"sent": f"sent {(po.sent_at or '')[:10]}", "queued": f"queued in Evolus {(po.sent_at or '')[:10]}",
                 "failed": "send failed - not sent", "sending": "sending"}.get(po.status, "draft - not sent")
        sup_rows += [["Purchase order", f"{po.po_number} · {state}"],
                     ["PO value", money.fmt(po.total, po.currency)
                      + (f" ≈ {money.fmt(po.total_brand, po.brand_currency)}"
                         if po.total_brand is not None and po.brand_currency
                         and po.brand_currency.upper() != po.currency.upper() else "")]]
    elif run.demand:
        sup_rows.append(["Purchase order", f"Pending pre-order threshold ({run.demand.units:,} / "
                                           f"{run.demand.threshold:,} units)"])
    sup_par = [[Paragraph(a, st["cellm"] if i else st["th"]), Paragraph(_esc(b), st["cell"])]
               for i, (a, b) in enumerate(sup_rows)]
    sut = Table(sup_par, colWidths=[0.13 * full, 0.27 * full])
    sut.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    split = size_breakdown(run, order_qty)
    right_col: list = [sut]
    if split:
        sizes, basis = split
        sz_rows = [["SIZE"] + [s for s, _ in sizes] + ["TOTAL"],
                   ["Units"] + [f"{n:,}" for _, n in sizes] + [f"{order_qty:,}"]]
        szt = Table(sz_rows, colWidths=[0.06 * full] + [0.05 * full] * len(sizes) + [0.07 * full])
        szt.setStyle(_SIZE_STYLE)
        right_col += [Spacer(1, 16), Paragraph("SIZE BREAKDOWN", st["th"]), Spacer(1, 4), szt, Spacer(1, 4),
                      Paragraph(_esc(basis), st["muted"])]
    left_col = [Paragraph("COLOURWAYS", st["th"]), Spacer(1, 4), cwt]
    layout2 = Table([[left_col, right_col]], colWidths=[0.56 * full, 0.44 * full])
    layout2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (0, 0), 18), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    story.append(layout2)
    story.append(CondPageBreak(30))
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        f"Revision {ctx.rev:02d} · {ctx.rev_date} · {'edited by the creative director' if ctx.rev else 'agent draft'}"
        f" · region: {_esc(tp.target_supplier_region)}", st["muted"]))

    doc.build(story)
    return buf.getvalue()


_SIZE_STYLE = TableStyle([
    ("FONT", (0, 0), (-1, 0), SANS, 6.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
    ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("FONT", (0, 1), (-1, -1), SANS, 8),
    ("TEXTCOLOR", (0, 1), (0, -1), MUTED), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE), ("FONT", (-1, 1), (-1, -1), SANS_B, 8),
    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
])


def _num(v: str) -> float:
    digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in v).split()
    try:
        return float(digits[0]) if digits else 0.0
    except ValueError:
        return 0.0
