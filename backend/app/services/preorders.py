"""Real pre-order tracking: fold Shopify orders (from the Admin API poller or the orders/create webhook) into
the run's PreorderDemand. Both sources feed `record_order`, which de-duplicates by order id, so an order that
arrives by webhook and is then seen by the poller counts once.

v4: each stored order keeps this product's line items with their sizes (`PreorderOrder.lines`), and `recompute`
emits one DemandOrderEvent per line (size, quantity, unit price, order id), so an order for an M and an L feeds
both sizes into the forecast's size split.

Per-run state lives in store.run_meta[run_id]["shopify"]:
    {"productId": gid, "launchedAt": iso, "launchedMono": float, "orders": {order_id: PreorderOrder}}
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from ..models import DemandOrderEvent, DemandPoint, PipelineRun, PreorderDemand, PreorderLine, PreorderOrder
from ..store import store
from . import shopify

RECENT = 12


def shopify_meta(run: PipelineRun) -> Optional[dict]:
    return (store.run_meta.get(run.id) or {}).get("shopify")


def attach(run: PipelineRun, product_id: str) -> dict:
    meta = store.run_meta.setdefault(run.id, {})
    now = datetime.now(timezone.utc)
    # launchedAt is whole seconds (like Shopify's createdAt); backdate the monotonic clock by the dropped fraction so
    # elapsed hours are measured from that same instant and an order placed just before a poll is never "in the future"
    st = {"productId": product_id, "launchedAt": now.isoformat(timespec="seconds"),
          "launchedMono": time.monotonic() - now.microsecond / 1e6, "orders": {}}
    meta["shopify"] = st
    return st


def runs_for_product(product_id: str) -> list[PipelineRun]:
    n = shopify.numeric_id(product_id)
    out = []
    for run_id, meta in store.run_meta.items():
        st = meta.get("shopify")
        run = store.runs.get(run_id)
        if st and run and shopify.numeric_id(st["productId"]) == n:
            out.append(run)
    return out


def record_order(run: PipelineRun, order: shopify.Order, via: str) -> Optional[PreorderOrder]:
    """Add `order` if it contains this run's product and is new. Returns the stored order or None."""
    st = shopify_meta(run)
    if st is None or order.cancelled:
        return None
    if order.test and not _count_test():
        return None
    if order.order_id in st["orders"]:
        return None
    units, amount = order.for_product(st["productId"])
    if units <= 0:
        return None
    lines = [PreorderLine(size=x.size, quantity=x.quantity, amount=round(x.amount, 2))
             for x in order.lines_for(st["productId"])]
    po = PreorderOrder(order_id=order.order_id, name=order.name, created_at=order.created_at or _now(),
                       units=units, amount=amount, currency=order.currency, first_name=order.first_name,
                       city=order.city, test=order.test, via=via, lines=lines)  # type: ignore[arg-type]
    st["orders"][order.order_id] = po
    if run.demand is not None:
        recompute(run, run.demand)
    return po


def recompute(run: PipelineRun, d: PreorderDemand) -> None:
    """Derive the counters, the newest-first order list and the cumulative series from the stored orders."""
    st = shopify_meta(run)
    if st is None:
        return
    orders = sorted(st["orders"].values(), key=lambda o: o.created_at)
    d.orders = len(orders)
    d.units = sum(o.units for o in orders)
    d.revenue = round(sum(o.amount for o in orders), 2)
    d.test_orders = sum(1 for o in orders if o.test)
    d.test_units = sum(o.units for o in orders if o.test)
    if orders:
        d.currency = orders[-1].currency
    d.recent_orders = list(reversed(orders))[:RECENT]
    d.order_events = [e for o in orders for e in order_events(o)]
    d.launched_at = st["launchedAt"]
    launched = _parse(st["launchedAt"])
    series = [DemandPoint(hour=0, orders=0)]
    total = 0
    for o in orders:
        total += o.units
        at = _parse(o.created_at)
        h = max(0.0, (at - launched).total_seconds() / 3600) if (launched and at) else series[-1].hour
        series.append(DemandPoint(hour=round(max(h, series[-1].hour), 4), orders=total))
    d.series = series


def order_events(o: PreorderOrder) -> list[DemandOrderEvent]:
    """One forecast event per line item (each with its size and unit price); one per order if it has no lines."""
    if not o.lines:
        return [DemandOrderEvent(timestamp=o.created_at, quantity=o.units, order_id=o.order_id,
                                 unit_price=round(o.amount / o.units, 2) if o.units else None)]
    return [DemandOrderEvent(timestamp=o.created_at, quantity=x.quantity, size=x.size, order_id=o.order_id,
                             unit_price=round(x.amount / x.quantity, 2) if x.quantity else None)
            for x in o.lines if x.quantity > 0]


def size_label(o: PreorderOrder) -> str:
    """'M' / '2× M, L' / '' - for the step log and the feed."""
    parts = [f"{x.quantity}× {x.size}" if x.quantity > 1 else x.size for x in o.lines if x.size]
    return ", ".join(parts)


def elapsed_hours(st: dict) -> float:
    return (time.monotonic() - st["launchedMono"]) / 3600


def _count_test() -> bool:
    from ..config import get_settings

    return get_settings().shopify_count_test_orders


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(iso: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None
