"""v3: explained production forecast - known answers, monotonicity, edge cases, API and the run seam."""

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import forecast as fc
from app.services.forecast import (Economics, ForecastRequest, NegBinom, OrderEvent,
                                   critical_ratio, forecast, largest_remainder, launch_share, orders_for_run)

L = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _iso(h: float) -> str:
    return (L + timedelta(hours=h)).isoformat()


def _orders(n: int, span_h: float = 96.0, sizes=("S", "M", "M", "L")) -> list[OrderEvent]:
    return [OrderEvent(timestamp=_iso(span_h * (i + 0.5) / max(n, 1)), quantity=1, size=sizes[i % len(sizes)])
            for i in range(n)]


def _req(orders=(), as_of_h=96.0, **econ) -> ForecastRequest:
    e = dict(unit_cost=60.0, retail_price=240.0, salvage_value=30.0, moq=0)
    e.update(econ)
    return ForecastRequest(orders=list(orders), launch_at=L.isoformat(), as_of=_iso(as_of_h),
                           economics=Economics(**e), planned_quantity=300)


# --------------------------------------------------------------------------- known answers


def test_critical_ratio_known_answer():
    assert critical_ratio(100, 40, 10) == pytest.approx(60 / 90)
    assert critical_ratio(240, 60, 30) == pytest.approx(180 / 210)
    f = forecast(_req(_orders(50)))
    assert f.critical_ratio == pytest.approx(round(180 / 210, 4))
    assert f.underage_cost == 180 and f.overage_cost == 30


def test_negative_binomial_matches_closed_form():
    r, p = 3.0, 0.4
    nb = NegBinom(r, p)
    for k in range(6):
        exact = math.comb(k + 2, k) * p ** 3 * (1 - p) ** k  # integer r: C(k+r-1, k) p^r (1-p)^k
        assert nb.pmf[k] == pytest.approx(exact, rel=1e-9)
    assert nb.mean == pytest.approx(r * (1 - p) / p, rel=1e-6)
    assert sum(nb.pmf) == pytest.approx(1.0)
    # quantile = smallest k with cdf >= prob
    for prob in (0.1, 0.5, 0.9):
        k = nb.quantile(prob)
        assert nb.cdf[k] >= prob - 1e-12 and (k == 0 or nb.cdf[k - 1] < prob)


def test_geometric_special_case_quantile():
    # NB(r=1, p) is geometric: P(X <= k) = 1 - (1-p)^(k+1)  ->  median for p=0.5 is 0, 0.9-quantile is 3
    nb = NegBinom(1.0, 0.5)
    assert nb.quantile(0.5) == 0
    assert nb.quantile(0.9) == 3


def test_newsvendor_quantity_is_the_cr_quantile():
    f = forecast(_req(_orders(80)))
    dem = fc._Demand(f.observed_units, fc.predictive(f.posterior.alpha, f.posterior.beta,
                                                       2.5 - f.explanation.data.window_share_elapsed))
    q = f.unconstrained_quantity
    assert dem.cdf(q) >= f.critical_ratio > dem.cdf(q - 1)
    # and it maximises expected profit over the sampled curve (within one stride)
    best = max(f.profit_curve, key=lambda p: p.expected_profit)
    stride = f.profit_curve[1].quantity - f.profit_curve[0].quantity
    assert abs(best.quantity - q) <= stride


def test_expected_sales_identity():
    dem = fc._Demand(10, NegBinom(4.0, 0.2))
    q = 25
    direct = sum(min(10 + k, q) * x for k, x in enumerate(dem.rest.pmf))
    assert dem.expected_sales(q) == pytest.approx(direct, rel=1e-9)


def test_launch_share_bounds_and_monotone():
    assert launch_share(0, 336, 0.06, 0.25) == 0
    assert launch_share(336, 336, 0.06, 0.25) == pytest.approx(1.0)
    vals = [launch_share(h, 336, 0.06, 0.25) for h in range(0, 337, 12)]
    assert vals == sorted(vals)


def test_size_rounding_sums_to_quantity():
    for total in (0, 1, 7, 299, 300, 1001):
        out = largest_remainder({"XS": 0.08, "S": 0.22, "M": 0.32, "L": 0.24, "XL": 0.14}, total)
        assert sum(out.values()) == total
    assert largest_remainder({"a": 1, "b": 1, "c": 1}, 10) == {"a": 4, "b": 3, "c": 3}
    f = forecast(_req(_orders(60)))
    assert sum(s.units for s in f.sizes) == f.recommended_quantity
    assert sum(s.share for s in f.sizes) == pytest.approx(1.0, abs=1e-3)


def test_size_split_smooths_toward_data():
    f = forecast(_req(_orders(200, sizes=("M",))))
    m = next(s for s in f.sizes if s.size == "M")
    xs = next(s for s in f.sizes if s.size == "XS")
    # (200 + 20*0.32) / 220
    assert m.share == pytest.approx((200 + 20 * 0.32) / 220, abs=1e-4)
    assert xs.share == pytest.approx(20 * 0.08 / 220, abs=1e-4) and xs.units > 0
    # an unknown size in the data is kept, with no prior mass
    g = forecast(_req([*_orders(10), OrderEvent(timestamp=_iso(5), size="XXL")]))
    assert any(s.size == "XXL" and s.base_share == 0 and s.units >= 0 for s in g.sizes)


# --------------------------------------------------------------------------- behaviour


def test_more_orders_project_higher():
    means = [forecast(_req(_orders(n))).season.mean for n in (0, 20, 60, 120, 240)]
    assert means[1:] == sorted(means[1:])
    q = [forecast(_req(_orders(n))).unconstrained_quantity for n in (20, 60, 120, 240)]
    assert q == sorted(q)


def test_zero_orders_is_prior_and_wide():
    f = forecast(_req([], as_of_h=0))
    assert f.confidence == "prior-only"
    assert "No orders yet" in f.confidence_note
    assert f.observed_units == 0
    assert f.preorders.mean == pytest.approx(250, rel=1e-3)  # prior mean m0
    assert f.season.mean == pytest.approx(250 * 2.5, rel=1e-3)
    assert (f.season.p90 - f.season.p10) / f.season.mean > 1.0  # deliberately wide
    assert f.posterior.data_weight == 0


def test_interval_narrows_with_data():
    few = forecast(_req(_orders(8), as_of_h=24))
    many = forecast(_req(_orders(200), as_of_h=200))
    rel = lambda f: (f.season.p90 - f.season.p10) / f.season.mean  # noqa: E731
    assert rel(many) < rel(few)
    assert few.confidence in ("early", "firming") and many.confidence in ("data-driven", "firming")


def test_moq_binding():
    f = forecast(_req(_orders(10), moq=2000))
    assert f.moq_binding and f.recommended_quantity == 2000
    assert f.unconstrained_quantity < 2000
    assert f.moq_note and "MOQ" in f.moq_note
    g = forecast(_req(_orders(10), moq=1))
    assert not g.moq_binding and g.moq_note is None


def test_higher_salvage_makes_more():
    lo = forecast(_req(_orders(60), salvage_value=0))
    hi = forecast(_req(_orders(60), salvage_value=55))
    assert hi.critical_ratio > lo.critical_ratio
    assert hi.recommended_quantity >= lo.recommended_quantity


def test_unprofitable_price_makes_zero():
    f = forecast(_req(_orders(30), unit_cost=100, retail_price=90, salvage_value=10))
    assert f.unconstrained_quantity == 0
    assert any("does not cover" in n for n in f.explanation.notes)


def test_determinism_and_no_llm():
    a = forecast(_req(_orders(77))).model_dump()
    b = forecast(_req(_orders(77))).model_dump()
    assert a == b
    assert a["llmUsed"] is False and a["method"] == "gamma-poisson-bass-newsvendor"


def test_explanation_is_complete():
    f = forecast(_req(_orders(40)))
    titles = [s.title for s in f.explanation.steps]
    assert any("Critical ratio" in t for t in titles) and any("Size split" in t for t in titles)
    keys = {a.key for a in f.explanation.assumptions}
    assert {"priorMeanPreorders", "seasonMultiplier", "salvageValue", "sizeCurve", "bassP", "bassQ"} <= keys
    d = f.explanation.data
    assert d.order_events == 40 and d.units == 40 and d.sized_units == 40
    assert f.baseline is not None and f.profit_delta_vs_baseline == pytest.approx(
        f.outcome.expected_profit - f.baseline.expected_profit, abs=0.02)


def test_orders_after_as_of_are_ignored():
    f = forecast(_req(_orders(50, span_h=200), as_of_h=100))
    assert f.observed_units == 25


# --------------------------------------------------------------------------- the seam


def test_no_orders_says_no_orders_yet_and_labels_assumptions():
    f = forecast(_req())
    assert f.confidence == "prior-only" and f.confidence_note.startswith("No orders yet.")
    assert not hasattr(f, "simulated")
    keys = {a.key for a in f.explanation.assumptions}
    assert {"priorMeanPreorders", "priorCv", "bassP", "bassQ", "seasonMultiplier", "salvageValue", "sizeCurve",
            "levelCvFloor", "unsoldRiskThreshold"} <= keys
    assert any("fit them to the brand's own past launches" in n for n in f.explanation.notes)


def test_orders_for_run_from_real_order_list():
    real = [{"createdAt": _iso(1), "quantity": 2, "variantTitle": "M", "price": "180.00"},
            {"timestamp": _iso(2), "size": "L"},
            {"no": "timestamp"}]
    run = SimpleNamespace(demand=SimpleNamespace(orders=real, series=[], window_hours=336, elapsed_hours=0,
                                                 launched_at=L.isoformat()),
                          steps=[], created_at=L.isoformat(), shopify_product=None, tech_pack=None)
    ev = orders_for_run(run)
    assert [(e.quantity, e.size, e.unit_price) for e in ev] == [(2, "M", 180.0), (1, "L", None)]


# --------------------------------------------------------------------------- API


def test_post_forecast(client):
    body = {
        "orders": [{"timestamp": _iso(h), "quantity": 1, "size": "M", "unitPrice": 240} for h in range(1, 40)],
        "launchAt": L.isoformat(), "asOf": _iso(48), "windowHours": 336,
        "economics": {"unitCost": 60, "retailPrice": 240, "salvageValue": 30, "moq": 150},
        "assumptions": {"seasonMultiplier": 3},
    }
    r = client.post("/api/forecast", json=body)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["recommendedQuantity"] >= 150 and f["llmUsed"] is False
    assert f["inputs"]["assumptions"]["seasonMultiplier"] == 3
    assert sum(s["units"] for s in f["sizes"]) == f["recommendedQuantity"]
    assert f["explanation"]["steps"][0]["formula"]
    # echo round-trips
    again = client.post("/api/forecast", json=f["inputs"]).json()
    assert again["recommendedQuantity"] == f["recommendedQuantity"]


def test_post_forecast_validation(client):
    r = client.post("/api/forecast", json={"launchAt": L.isoformat(), "economics": {"unitCost": 0, "retailPrice": 1}})
    assert r.status_code == 422 and "detail" in r.json()
    r = client.post("/api/forecast", json={"launchAt": "not a date", "economics": {"unitCost": 1, "retailPrice": 2}})
    assert r.status_code == 422


def test_run_forecast(live, fakes, trend, s, monkeypatch):
    from helpers import answer_all_rfqs, approve, collecting, wait

    from app.store import store

    monkeypatch.setattr(s, "demand_stage_threshold", 2)
    run_id = approve(live, trend, qty=300)
    assert live.get("/api/runs/nope/forecast").status_code == 404
    answer_all_rfqs(live, run_id)
    run = wait(live, run_id, collecting)
    f = live.get(f"/api/runs/{run_id}/forecast").json()
    assert f["confidence"] == "prior-only" and "simulated" not in f and f["observedUnits"] == 0
    fakes["shop.fake"].state.place_order(run["shopifyProduct"]["productId"], 1, size="M")
    fakes["shop.fake"].state.place_order(run["shopifyProduct"]["productId"], 1, size="L")
    run = wait(live, run_id)
    req = fc.request_for_run(store.runs[run_id])
    req.as_of = "2100-01-01T00:00:00Z"  # count every order of the sub-second test window
    f = forecast(req)
    assert f.observed_units == run["demand"]["units"] == 2 and f.inputs.planned_quantity == 300
    q = next(x for x in run["quotes"] if x["supplierName"] == run["recommendation"]["selectedSupplierName"])
    assert f.unit_cost == q["unitPrice"] and f.moq == q["moq"] and f.recommended_quantity >= q["moq"]


def test_real_shopify_orders_reach_the_forecast():
    """Every recorded Shopify order (not just the 12-item feed) becomes a forecast OrderEvent."""
    from types import SimpleNamespace

    from app.models import DemandOrderEvent, PreorderDemand

    events = [DemandOrderEvent(timestamp=f"2026-10-13T10:{i:02d}:00+00:00", quantity=1 + i % 2, unit_price=385.0)
              for i in range(20)]
    d = PreorderDemand(threshold=5, threshold_basis="stage", source="shopify",
                       order_events=events, launched_at="2026-10-13T09:00:00+00:00")
    run = SimpleNamespace(demand=d, steps=[], created_at="2026-10-13T09:00:00+00:00", shopify_product=None)
    got = fc.orders_for_run(run)
    assert len(got) == 20 and sum(o.quantity for o in got) == sum(e.quantity for e in events)
    launch, _, _ = fc.window_for_run(run)
    assert launch.isoformat().startswith("2026-10-13T09:00")


# --------------------------------------------------------------------------- v4: real sizes


def test_size_split_responds_to_real_sizes():
    """Per-line events from Shopify size variants move the split away from the base curve, toward the data."""
    from app.models import DemandOrderEvent, PreorderDemand, PreorderLine, PreorderOrder
    from app.services import preorders

    # 30 orders: each buys an L, every third also an XL (multi-size order -> two lines, one order id)
    orders = [PreorderOrder(order_id=f"gid://shopify/Order/{i}", name=f"#{i}", created_at=_iso(1 + i), units=0,
                            amount=0.0, lines=[PreorderLine(size="L", quantity=1, amount=240.0)]
                            + ([PreorderLine(size="xl", quantity=1, amount=240.0)] if i % 3 == 0 else []))
              for i in range(30)]
    events: list[DemandOrderEvent] = [e for o in orders for e in preorders.order_events(o)]
    assert len(events) == 40 and all(e.size for e in events)
    d = PreorderDemand(threshold=5, threshold_basis="stage", source="shopify",
                       order_events=events, launched_at=L.isoformat(), elapsed_hours=48)
    run = SimpleNamespace(demand=d, steps=[], created_at=L.isoformat(), shopify_product=None, tech_pack=None)
    ev = orders_for_run(run)
    assert ev[0].order_id == "gid://shopify/Order/0" == ev[1].order_id and ev[0].size == "L" and ev[1].size == "xl"

    base = forecast(_req([OrderEvent(timestamp=e.timestamp, quantity=1) for e in ev], as_of_h=48))
    sized = forecast(_req(ev, as_of_h=48))
    b = {s.size: s for s in base.sizes}
    z = {s.size: s for s in sized.sizes}
    assert set(z) == {"XS", "S", "M", "L", "XL"}  # "xl" counts toward the curve's "XL", not a new size
    assert z["L"].orders == 30 and z["XL"].orders == 10 and z["M"].orders == 0
    assert all(b[k].share == b[k].base_share for k in b)  # no sizes -> the base curve
    assert z["L"].share > b["L"].share and z["XL"].share > b["XL"].share and z["M"].share < b["M"].share
    assert sized.recommended_quantity == base.recommended_quantity  # sizes split the run, they don't resize it
    assert z["L"].units > b["L"].units and z["M"].units < b["M"].units
    assert sum(s.units for s in sized.sizes) == sized.recommended_quantity
    assert sized.explanation.data.sized_units == 40 and sized.explanation.data.sized_orders == 30
    assert base.explanation.data.sized_orders == 0
    assert "from 30 orders" in next(s for s in sized.explanation.steps if s.title == "Size split").substituted


def test_size_curve_follows_the_products_sizes():
    assert fc.size_curve_for(None) == fc.DEFAULT_SIZE_CURVE
    assert fc.size_curve_for(["XS", "S", "M", "L", "XL"]) == pytest.approx(fc.DEFAULT_SIZE_CURVE)
    c = fc.size_curve_for(["S", "M", "L", "XL", "XXL"])
    assert list(c) == ["S", "M", "L", "XL", "XXL"] and sum(c.values()) == pytest.approx(1, abs=1e-3)
    assert c["XXL"] < c["S"] < c["M"]
    tp = SimpleNamespace(size_range=None, measurements={"size range": "S – XXL"}, production_quantity=300,
                         target_retail_price=240.0)
    run = SimpleNamespace(shopify_product=SimpleNamespace(sizes=["S", "M"]), tech_pack=tp)
    assert fc._run_sizes(run) == ["S", "M"]
    run.shopify_product = None
    assert fc._run_sizes(run) == ["S", "M", "L", "XL", "XXL"]
