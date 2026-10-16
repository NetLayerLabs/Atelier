"""Shared test helpers. Quote documents are generated here, in memory, for each test (never stored in the repo)."""

from __future__ import annotations

import io
import time
from typing import Callable, Optional


def wait(client, run_id: str, cond: Callable[[dict], bool] = lambda r: r["status"] != "running",
         timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if cond(run):
            return run
        time.sleep(0.02)
    raise AssertionError(f"condition not reached: {[(s['key'], s['status'], s.get('error')) for s in run['steps']]}")


def awaiting(run: dict) -> bool:
    return (run.get("quoteRound") or {}).get("status") == "awaiting"


def collecting(run: dict) -> bool:
    return (run.get("demand") or {}).get("status") == "collecting" or run["status"] != "running"


def design(client, trend: dict, count: int = 1) -> dict:
    r = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": count})
    assert r.status_code == 200, r.text
    return r.json()["designs"][0]


def approve(client, trend: dict, qty: int = 300) -> str:
    d = design(client, trend)
    r = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": qty})
    assert r.status_code == 200, r.text
    return r.json()["runId"]


def quote_pdf(supplier: str, *, price: Optional[float] = 101.5, currency: Optional[str] = "USD",
              moq: Optional[int] = 250, lead: Optional[str] = "8 weeks", sample: Optional[float] = 200.0,
              terms: Optional[str] = "30% deposit, 70% before shipment", number: str = "Q-1001",
              ref: str = "", note: Optional[str] = "We can hold the shade for your run.") -> bytes:
    """A throwaway quote document with only the fields given (None = not on the document)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    lines = [supplier, f"Quote No. {number}"]
    if ref:
        lines.append(f"Your reference: {ref}")
    if currency:
        lines.append(f"Currency: {currency}")
    if price is not None:
        lines.append(f"Unit price: {currency or 'USD'} {price:.2f}")
    if moq is not None:
        lines.append(f"MOQ: {moq}")
    if lead:
        lines.append(f"Lead time: {lead}")
    if sample is not None:
        lines.append(f"Sample cost: {currency or 'USD'} {sample:.2f}")
    if terms:
        lines.append(f"Payment terms: {terms}")
    if note:
        lines.append(f"Notes: {note}")
    lines.append("Kind regards")
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def upload_quote(client, run_id: str, supplier: str, **kw) -> dict:
    pdf = quote_pdf(supplier, ref=f"ATL-{run_id}", **kw)
    r = client.post(f"/api/runs/{run_id}/quotes", files={"file": (f"{supplier[:8]}.pdf", pdf, "application/pdf")},
                    data={"supplierName": supplier})
    assert r.status_code == 200, r.text
    return r.json()


def answer_all_rfqs(client, run_id: str, **kw) -> dict:
    run = wait(client, run_id, awaiting)
    for e in run["supplierEmails"]:
        run = upload_quote(client, run_id, e["supplierName"], **kw)
    return run
