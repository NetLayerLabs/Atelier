"""The approval pipeline: TechPack (the brain) -> supplier outreach (Evolus) -> supplier quotes & recommendation
-> Shopify pre-order (a REAL product: Evolus workflow or the Admin API) -> pre-order demand validation on REAL
Shopify orders -> purchase order (sent through Evolus).

v5: nothing is simulated. When a step's service is not configured or fails, the step ends in an honest error
(`service`, `hint`, `retryable`), the run stops there, and POST /api/runs/{id}/retry resumes from that step.

Runs as an asyncio background task and mutates the stored PipelineRun in place, so
GET /api/runs/{id} shows progress (log lines appear as the work happens) while it runs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from .config import get_settings, host_of
from .data.suppliers import shortlist
from .models import (DemandPoint, Design, PipelineRun, PipelineStep, PreorderDemand, ShopifyProduct, TechPack,
                     TrendAnalysis, now_iso)
from .services import (brain, decisions, direction, evolus, llm, preorders, product_image, purchase_orders, quotes,
                       sequences, shopify, sizes, sourcing, telemetry, voice)
from .services import fx, money, supplier_view
from .services.errors import NotConfigured, ServiceError
from .store import new_id, store

log = logging.getLogger("atelier.pipeline")

STEP_LABELS = {
    "techpack": "Generate Tech Pack",
    "supplier_outreach": "Supplier Outreach",
    "supplier_quotes": "Quotes & Recommendation",
    "shopify_preorder": "Shopify Pre-order",
    "preorder_demand": "Demand Validation",
}
ORDER = list(STEP_LABELS)

_tasks: set[asyncio.Task] = set()


def create_run(design: Design) -> PipelineRun:
    run = PipelineRun(
        id=new_id("run"),
        design_id=design.id,
        steps=[PipelineStep(key=k, label=v) for k, v in STEP_LABELS.items()],  # type: ignore[arg-type]
    )
    store.runs[run.id] = run
    store.run_meta[run.id] = {"seed": design.seed, "suppliers": []}
    return run


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def start_run(run: PipelineRun, design: Design, trend: TrendAnalysis, quantity: int) -> None:
    _meta(run)["quantity"] = quantity
    _spawn(_execute(run, design, trend, quantity))


def retry(run: PipelineRun, *, confirm_resend: bool = False) -> str:
    """Resume a failed run from its first errored step. Returns that step's key. ValueError -> 409.
    QA M3: a step whose Evolus execution started but whose outcome is unknown is only retried (which sends the emails
    again) with `confirm_resend`."""
    if run.status != "failed":
        raise ValueError("only a failed run can be retried")
    step = next((st for st in run.steps if st.status == "error"), None)
    if step is None:
        raise ValueError("no step to retry")
    if step.unknown_execution_id and not confirm_resend:
        raise ValueError(f"the emails may already have been sent (Evolus execution {step.unknown_execution_id}, "
                         f"status unknown) - check Evolus first; to send them again anyway, retry with "
                         f'{{"confirmResend": true}}')
    design = store.designs.get(run.design_id)
    trend = store.trends.get(design.trend_id) if design else None
    if design is None or trend is None:
        raise ValueError("the design or trend of this run is gone")
    start = ORDER.index(step.key)
    for st in run.steps[start:]:
        if st.status == "error":
            st.log.append("↻ Retrying…")
        st.status, st.error, st.service, st.hint, st.retryable = "pending", None, None, None, False
        st.finished_at = None
        if st.unknown_execution_id:
            st.log.append(f"Re-sending confirmed by the creative director (execution {st.unknown_execution_id} "
                          f"status was unknown)")
            st.unknown_execution_id = None
    run.status = "running"
    quantity = int(_meta(run).get("quantity") or (run.tech_pack.production_quantity if run.tech_pack else 1))
    _spawn(_execute(run, design, trend, quantity, start=start))
    return step.key


async def _execute(run: PipelineRun, design: Design, trend: TrendAnalysis, quantity: int, start: int = 0) -> None:
    steps = {s.key: s for s in run.steps}

    def work(key: str):
        st = steps[key]
        if key == "techpack":
            return _step_techpack(run, st, design, trend, quantity)
        if key == "supplier_outreach":
            return _step_outreach(run, st, design, trend, run.tech_pack)
        if key == "supplier_quotes":
            return _step_quotes(run, st, design)
        if key == "shopify_preorder":
            return _step_shopify(run, st, design, trend, run.tech_pack)
        return _step_demand(run, st, design)

    current: PipelineStep | None = None
    try:
        for key in ORDER[start:]:
            current = steps[key]
            await _traced(current, work(key))
        run.status = "completed"
    except ServiceError as e:
        log.warning("pipeline %s stopped at %s: %s", run.id, current.key if current else "?", e.message)
        _fail(run, current, e.message, service=e.service, hint=e.hint)
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline %s failed", run.id)
        _fail(run, current, str(e) or e.__class__.__name__)


def _fail(run: PipelineRun, step: PipelineStep | None, message: str, *, service: str | None = None,
          hint: str | None = None) -> None:
    if step is not None:
        step.status = "error"
        step.error = message
        step.service = service
        step.hint = hint
        step.retryable = True
        step.finished_at = now_iso()
        step.log.append(f"✗ {message}" + (f" - {hint}" if hint else ""))
    run.status = "failed"


async def _traced(step: PipelineStep, coro):
    """v2: attach every inference/Evolus call made while `coro` runs to step.telemetry (live-updating)."""
    step.telemetry = []
    with telemetry.collect(step.telemetry):  # same list object, so polling clients see calls as they land
        return await coro


def _brain_plan() -> str:
    s = get_settings()
    names = {brain.ROUTE_AGENT: f"Evolus agent {s.evolus_agent_model} → {s.evolus_agent_backend}",
             brain.ROUTE_DIRECT: f"direct vLLM @ {host_of(s.amd_vllm_endpoint)}"}
    return ", else ".join(names[r] for r in brain.plan()) or "none connected"


def _model_label(model: str | None, host: str) -> str:
    gpu = telemetry.gpu_label()
    return f"{model or 'the served model'} via vLLM @ {host}" + (f" · {gpu}" if gpu else "")


def _call_stats(step: PipelineStep, purpose: str) -> str | None:
    """'1,666 tok · 412 tok/s · TTFT 180ms · 4.0s' from the last successful call, or None."""
    c = next((c for c in reversed(step.telemetry or []) if c.purpose == purpose and c.ok), None)
    if c is None:
        return None
    parts = []
    if c.completion_tokens:
        parts.append(f"{c.completion_tokens:,} tok")
    if c.tokens_per_sec:
        parts.append(f"{c.tokens_per_sec:,.0f} tok/s")
    if c.ttft_ms is not None:
        parts.append(f"TTFT {c.ttft_ms:,.0f}ms")
    parts.append(f"{c.latency_ms / 1000:.1f}s")
    return " · ".join(parts) + (" (FAKE upstream - not a real model)" if c.fake else "")


async def _say(step: PipelineStep, line: str) -> None:
    """Append a log line. (v5: no artificial pacing - lines appear as the real work happens.)"""
    step.log.append(line)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "atelier-product"


def _begin(step: PipelineStep) -> None:
    step.status = "running"
    step.started_at = now_iso()


def _finish(step: PipelineStep) -> None:
    step.status = "done"
    step.finished_at = now_iso()


# --------------------------------------------------------------------------- step 1


async def _step_techpack(run: PipelineRun, step: PipelineStep, design: Design, trend: TrendAnalysis,
                         quantity: int) -> TechPack:
    _begin(step)
    await _say(step, f"Loaded approved design {design.id} · {design.garment_type}")
    await _say(step, f"Brief: '{trend.trend_name}' · {len(trend.key_fabrics)} fabrics · "
                     f"{len(trend.color_palette)}-colour palette · {quantity} units")
    evidence = voice.attach_to_design(design)  # v3: customer-voice changes join the direction lineage
    if evidence:
        await _say(step, f"Customer evidence: {len(evidence)} change(s) from {voice.sources_line(evidence)} "
                         "added to the brief")
    await _say(step, f"Brain: {_brain_plan()}")
    thought = await llm.live_techpack(trend, design, quantity)  # brain.BrainUnavailable -> step error + retry
    tp = thought.value
    step.route = thought.route
    for err in thought.errors:
        await _say(step, f"⚠ {err} - next in the chain")
    await _say(step, f"{thought.label} returned a TechPack - parsed & schema-validated ✓")
    if tp.citations:
        await _say(step, f"Grounded in {len(tp.citations)} knowledge-library passage(s): "
                         + "; ".join(c.source for c in tp.citations[:3]))
    stats = _call_stats(step, "techpack")
    if stats:
        await _say(step, f"Inference: {stats}")
    if not tp.colorway:  # carry the effective (directed) palette, not the trend's original
        tp.colorway = list(direction.effective_trend(trend, design).color_palette)
    tp = voice.finalize_techpack(tp, design)
    run.tech_pack = tp
    run.original_tech_pack = tp.model_copy(deep=True)
    if not run.style_number:
        run.style_number = sequences.next_code("style")
    unit_cost = sum(b.target_cost_per_unit for b in tp.bill_of_materials)
    await _say(step, f"{tp.garment_name} · style {run.style_number}: {len(tp.bill_of_materials)} BOM lines, "
                     f"{len(tp.measurements)} points of measure")
    await _say(step, f"Target cost {money.fmt(unit_cost, tp.currency)}/unit (the model's costing) · target retail "
                     f"{money.fmt(tp.target_retail_price, tp.currency, 0)} · region: {tp.target_supplier_region}")
    _finish(step)
    return tp


# --------------------------------------------------------------------------- step 2


async def _step_outreach(run: PipelineRun, step: PipelineStep, design: Design, trend: TrendAnalysis,
                         tp: TechPack) -> None:
    s = get_settings()
    _begin(step)
    ref = quotes.rfq_ref(run.id)
    already = run.supplier_emails and all(e.status == "drafted" for e in run.supplier_emails)
    if already:  # a retry after a failed send: keep the drafts, only send again
        await _say(step, f"Re-using the {len(run.supplier_emails or [])} drafted RFQs")
    else:
        suppliers = shortlist(trend.key_fabrics)
        _meta(run)["suppliers"] = suppliers
        await _say(step, f"Matching BOM to the supplier directory: {', '.join(trend.key_fabrics[:3])}")
        await _say(step, "Shortlisted " + ", ".join(f"{x['name']} ({x['region']})" for x in suppliers))
        await _say(step, f"Drafting RFQs · brain: {_brain_plan()}")
        thought = await llm.live_supplier_emails(tp, suppliers, design, trend, rfq_ref=ref)  # raises -> step error
        emails = thought.value
        step.route = thought.route
        for err in thought.errors:
            await _say(step, f"⚠ {err} - next in the chain")
        await _say(step, f"RFQs drafted by {thought.label}")
        stats = _call_stats(step, "rfq_emails")
        if stats:
            await _say(step, f"Inference: {stats}")
        if s.evolus_rfq_ai_tool and s._evolus_base_ok:
            await _say(step, "Polishing RFQ copy with the Evolus 'email' AI Tool…")
            for e in emails:
                try:
                    e.body = await evolus.run_ai_tool("email", e.body, {"mode": "write", "tone": "commercial"},
                                                      purpose="rfq_polish")
                except Exception as ex:  # noqa: BLE001
                    await _say(step, f"⚠ AI Tool skipped for {e.supplier_name}: {str(ex)[:80]} (draft kept as written)")
                    break
        run.supplier_emails = []
        for e in emails:
            run.supplier_emails.append(e)
            await _say(step, f"Drafted RFQ to {e.supplier_name} ({e.region}) → {e.to_email}")

    if not s.evolus_outreach_live:
        raise NotConfigured("evolus_outreach", f"Evolus outreach not connected - the {len(run.supplier_emails or [])} "
                                               "RFQs are drafted but were not sent")
    await _say(step, f"POST Evolus workflow {s.evolus_outreach_workflow_id} (supplier outreach)…")

    async def on_status(status: str, polls: int) -> None:
        await _say(step, f"Evolus execution · {status}")

    try:
        resp = await evolus.execute_workflow(s.evolus_outreach_workflow_id, {
            # Flat parameters (see docs/EVOLUS_SETUP.md); nested values are sent as JSON strings.
            "garment_name": tp.garment_name,
            "production_quantity": tp.production_quantity,
            # The supplier-safe view (no target costs, retail or margin) and a link only a mill can open.
            "tech_pack": supplier_view.techpack(tp),
            "image_url": supplier_view.public_link(design.image_url) or "",
            "rfq_emails": [e.model_dump(by_alias=True) for e in run.supplier_emails or []],
            "rfq_ref": ref,  # v3: replies quote it; the inbound workflow passes it back with the quote
        }, purpose="supplier_outreach", on_status=on_status,
            param_keys=evolus.EMAIL_WORKFLOW_PARAMS)
    except evolus.EvolusStatusUnknown as e:  # QA M3: started - the RFQs may have gone out
        log.warning("supplier_outreach: Evolus execution %s status unknown: %s", e.execution_id, e)
        step.unknown_execution_id = e.execution_id
        raise ServiceError("evolus_outreach", f"RFQ send status unknown - Evolus execution {e.execution_id} was "
                                              f"started but its outcome couldn't be read ({str(e)[:120]})",
                           hint=f"Check execution {e.execution_id} in Evolus before sending again: the suppliers may "
                                f"already have the RFQs. Re-sending needs an explicit confirmation.") from e
    except Exception as e:  # noqa: BLE001
        log.warning("supplier_outreach: Evolus failed (%s: %s)", e.__class__.__name__, e)
        raise ServiceError("evolus_outreach", f"Evolus outreach failed - RFQs not sent: {str(e)[:400]}") from e
    status = evolus.outreach_status(resp)
    for e in run.supplier_emails or []:
        e.status = status  # type: ignore[assignment]
    tail = " - still running in Evolus" if resp.get("timedOut") else ""
    await _say(step, f"Evolus execution {resp.get('executionId') or '(no id returned)'} · "
                     f"{resp.get('status')} · {len(run.supplier_emails or [])} RFQs {status}{tail}")
    _finish(step)


# --------------------------------------------------------------------------- step 4: Shopify pre-order


async def _step_shopify(run: PipelineRun, step: PipelineStep, design: Design, trend: TrendAnalysis,
                        tp: TechPack) -> None:
    """Open the pre-order on a REAL Shopify store.

    Path selection: the Evolus Shopify workflow (an Evolus building block) when it is configured AND returns a
    Shopify product id; otherwise Atelier calls the Shopify Admin API directly. Without Shopify credentials the
    step stops with "Shopify not connected" and a setup hint.
    """
    s = get_settings()
    _begin(step)
    title = f"{tp.garment_name} - Pre-order"
    handle = _slug(tp.garment_name)
    description = tp.description
    await _say(step, f"Preparing listing '{title}' · hero render + copy from tech pack")
    product: ShopifyProduct | None = None
    try:
        lst = await listing_price(tp.target_retail_price, tp.currency or money.brand_currency())
    except shopify.ShopifyError as e:
        raise ServiceError("shopify", f"Couldn't read the store's currency - nothing was listed: {str(e)[:200]}") from e
    if s.shopify_admin_ready or s.evolus_shopify_live:
        await _say(step, _listing_line(lst))

    if s.evolus_shopify_live:
        await _say(step, f"POST Evolus workflow {s.evolus_shopify_workflow_id} (Shopify productCreate)…")

        async def on_status(status: str, polls: int) -> None:
            await _say(step, f"Evolus execution · {status}")

        try:
            resp = await evolus.execute_workflow(s.evolus_shopify_workflow_id, {
                "title": title,
                "description": description,
                "price": lst["price"],
                "currency": lst["currency"] or lst["brand_currency"] or "",
                "image_url": design.image_url,
                "handle": handle,
                "production_quantity": tp.production_quantity,
            }, purpose="shopify_preorder", on_status=on_status)
            parsed = evolus.parse_shopify(resp)
            if shopify.looks_like_product_id(parsed["productId"]):
                product = await _product_from_evolus(run, step, tp, design, title, parsed, lst)
            else:
                await _say(step, "Evolus run finished without a Shopify product id - creating the product "
                                 "directly via the Admin API")
        except Exception as e:  # noqa: BLE001
            log.warning("Evolus Shopify workflow failed (%s: %s); trying the Admin API directly",
                        e.__class__.__name__, e)
            await _say(step, f"⚠ Evolus workflow failed ({str(e)[:90]})")

    if product is None and s.shopify_admin_ready:
        try:
            product = await _product_direct(run, step, tp, design, title, lst)
        except shopify.ShopifyPartialError as e:  # QA M1: the product exists; a retry repairs it (no duplicate)
            raise ServiceError("shopify", f"Shopify product {e.product_id} was created, but setting it up failed: "
                                          f"{str(e)[:160]} - it is not live yet; Retry finishes this same product "
                                          f"(no duplicate)") from e
        except shopify.ShopifyError as e:
            raise ServiceError("shopify", f"Shopify Admin API failed - nothing was listed: {str(e)[:200]}") from e
    if product is None and s.evolus_shopify_live:
        raise ServiceError("shopify", "The Evolus Shopify workflow created no product and there is no Admin API "
                                      "access to create it directly - nothing was listed")
    if product is None:
        raise NotConfigured("shopify", "Shopify not connected - nothing was listed")
    run.shopify_product = product
    price = money.fmt(product.price, product.currency, 0)
    if product.published:  # QA M1: "live" only when it really is published to the Online Store
        await _say(step, f"Pre-order live at {product.url} · {price} - the demand window tracks real orders for "
                         f"this product")
    elif product.published is None:
        await _say(step, f"Listing at {product.url} · {price} (created by Evolus; publication not verified) - the "
                         f"demand window tracks real orders for this product")
    else:
        await _say(step, f"⚠ Product created at {product.url} but NOT published to the Online Store - publish it in "
                         f"Shopify admin ({product.admin_url or 'Products'}) before sharing the QR code; orders are "
                         f"tracked once it sells")
    _finish(step)


async def listing_price(retail: float, brand: str | None) -> dict:
    """The store price for the brand-currency `retail`. The store has its own currency (read from the shop query);
    when it differs from the brand's, the price is converted at the ECB reference rate and both are kept - never a
    brand-currency number silently listed in another currency. Raises ServiceError when a conversion is needed and
    no published rate is available; shopify.ShopifyError when the shop can't be read."""
    out = {"price": round(retail, 2), "currency": None, "price_brand": round(retail, 2), "brand_currency": brand,
           "fx_rate": None, "fx_date": None}
    if not get_settings().shopify_admin_ready:
        return out  # no Admin API: the store currency can't be verified (the step says so)
    store_ccy = str((await shopify.shop_info()).get("currencyCode") or "").upper() or None
    out["currency"] = store_ccy
    if not store_ccy or not brand or store_ccy == brand.upper():
        return out
    got = await fx.rate(brand, store_ccy)
    if got is None:
        raise ServiceError(
            "shopify", f"The store sells in {store_ccy} but the brand prices in {brand}, and no ECB exchange rate "
                       f"could be loaded to convert the {money.fmt(retail, brand)} retail price - nothing was listed",
            hint=f"Retry once the ECB rates load ({fx.last_error() or 'no published rate'}), or set the store "
                 f"currency to {brand} in Shopify admin → Settings → Store details.")
    rate, date = got
    out.update(price=round(retail * rate, 2), fx_rate=rate, fx_date=date or None)
    return out


def _listing_line(lst: dict) -> str:
    brand, store_ccy = lst["brand_currency"], lst["currency"]
    retail = money.fmt(lst["price_brand"], brand)
    if store_ccy is None:
        return (f"⚠ Store currency not verified (no Admin API access) - the listing price is the brand retail "
                f"{retail}; check the store sells in {brand or 'the brand currency'}")
    if lst["fx_rate"] is None:
        return f"Store currency {store_ccy} = brand currency · listed at {retail}"
    return (f"Store currency {store_ccy} ≠ brand currency {brand}: retail {retail} listed at "
            f"{money.fmt(lst['price'], store_ccy)} (ECB reference rate{' ' + lst['fx_date'] if lst['fx_date'] else ''}: "
            f"1 {brand} = {lst['fx_rate']:.6g} {store_ccy})")


def _listing_fields(lst: dict) -> dict:
    return {k: lst[k] for k in ("price", "currency", "price_brand", "brand_currency", "fx_rate", "fx_date")}


def _shopify_extras(run: PipelineRun, url: str) -> dict:
    s = get_settings()
    short = s.shopify_short_url.strip() or re.sub(r"^https?://", "", url)
    return {"short_url": short, "qr_url": s.public_url(f"/api/runs/{run.id}/storefront-qr.svg"),
            "storefront_password": s.shopify_storefront_password or None,
            "shop_domain": shopify.shop_domain() if s.shopify_store_domain else None}


async def _product_direct(run: PipelineRun, step: PipelineStep, tp: TechPack, design: Design,
                          title: str, lst: dict) -> ShopifyProduct:
    s = get_settings()
    await _say(step, f"Shopify Admin API {s.shopify_api_version} @ {shopify.shop_domain()} - creating the product "
                     f"directly")
    png, note = await asyncio.to_thread(product_image.design_png, design.image_url)
    await _say(step, f"Design render: {note}" + (f" · {len(png) // 1024} KB" if png else ""))
    q = sourcing.selected_quote(run.quotes, run.recommendation)
    size_list = sizes.size_range(tp)
    await _say(step, f"Size option: {sizes.label(size_list)} - one variant per size, so every order carries a size")
    created = await shopify.create_preorder_product(
        title=title,
        description_html=shopify.preorder_description_html(
            tp.description, lead_weeks=q.lead_time_weeks if q else None,
            materials=[b.material for b in tp.bill_of_materials[:3]]),
        price=lst["price"], image_png=png, image_alt=f"{tp.garment_name} - Atelier design render",
        tags=["pre-order", "atelier"], product_type=design.garment_type.title(), sizes=size_list,
        existing_product_id=_meta(run).get("shopify_product_id"),  # QA M1: a retry repairs, never duplicates
        on_created=lambda pid: _meta(run).__setitem__("shopify_product_id", pid),
    )
    for n in created.notes:
        await _say(step, n)
    await _say(step, f"productCreate ✓ {created.product_id} · handle {created.handle}")
    if created.variant_ids:
        await _say(step, f"productVariantsBulkCreate ✓ {len(created.variant_ids)} size variants "
                         f"({', '.join(created.variant_ids)}) · each {money.fmt(lst['price'], lst['currency'])} · "
                         f"inventory policy CONTINUE, not tracked (sellable as a pre-order at zero stock)")
    else:
        await _say(step, f"Variant priced {money.fmt(lst['price'], lst['currency'])} · inventory policy CONTINUE, "
                         f"not tracked (sellable as a pre-order at zero stock)")
    if created.published:
        await _say(step, "Published to the Online Store sales channel ✓")
    preorders.attach(run, created.product_id)
    return ShopifyProduct(product_id=created.product_id, title=title, handle=created.handle, url=created.url,
                          image_url=design.image_url, source="shopify", **_listing_fields(lst),
                          admin_url=created.admin_url, variant_id=created.variant_id,
                          published=created.published, sizes=created.sizes or None,
                          variant_ids=created.variant_ids or None, **_shopify_extras(run, created.url))


async def _product_from_evolus(run: PipelineRun, step: PipelineStep, tp: TechPack, design: Design, title: str,
                               parsed: dict, lst: dict) -> ShopifyProduct:
    s = get_settings()
    pid = shopify.product_gid(parsed["productId"])
    handle = parsed["handle"] or _slug(tp.garment_name)
    url = parsed["url"] or (shopify.storefront_product_url(handle) if s.shopify_store_domain else "")
    variant_id = None
    variant_ids: dict[str, str] = {}
    await _say(step, f"Evolus created Shopify product {pid}")
    if s.shopify_admin_ready:  # confirm it really exists, and read the canonical handle / URL
        try:
            p = await shopify.get_product(pid)
            if not p:
                raise shopify.ShopifyError(f"product {pid} not found in {shopify.shop_domain()}")
            handle = p.get("handle") or handle
            url = p.get("onlineStoreUrl") or shopify.storefront_product_url(handle)
            nodes = (p.get("variants") or {}).get("nodes") or []
            variant_id = (nodes or [{}])[0].get("id")
            variant_ids = shopify.variant_sizes(nodes)
            await _say(step, f"Verified in the Admin API: {handle} · status {p.get('status')}")
        except shopify.ShopifyError as e:
            await _say(step, f"⚠ Could not verify the Evolus product via the Admin API ({str(e)[:90]})")
    if variant_ids:
        await _say(step, f"Size variants on the Evolus product: {', '.join(variant_ids)}")
    else:
        why = ("it has no Size variants" if s.shopify_admin_ready
               else "its variants can't be read without Admin API access")
        await _say(step, f"⚠ No size data: {why} - orders won't carry a size, so the forecast's size split stays "
                         f"on the base size curve")
    preorders.attach(run, pid)
    return ShopifyProduct(product_id=pid, title=title, handle=handle, url=url or f"/products/{handle}",
                          image_url=design.image_url, source="evolus", **_listing_fields(lst),
                          admin_url=shopify.admin_product_url(pid) if s.shopify_store_domain else None,
                          variant_id=variant_id, published=None, sizes=list(variant_ids) or None,
                          variant_ids=variant_ids or None, **_shopify_extras(run, url))


# --------------------------------------------------------------------------- step 3: quotes


def _meta(run: PipelineRun) -> dict:
    return store.run_meta.setdefault(run.id, {"seed": 0, "suppliers": []})


async def _step_quotes(run: PipelineRun, step: PipelineStep, design: Design) -> None:
    _begin(step)
    await _await_real_quotes(run, step)
    if not run.quotes:
        raise RuntimeError("no supplier quotes received")
    await _await_price_confirmation(run, step)  # QA M10
    tp = run.tech_pack
    assert tp is not None
    await _say(step, sourcing.scoring_summary(tp.production_quantity))  # v5: the workspace's weights
    pick = sourcing.best(run.quotes)
    rationale, cites, route, rerr = None, None, None, None
    await _say(step, f"Drafting the comparison rationale · brain: {_brain_plan()}")
    try:
        thought = await sourcing.live_rationale(tp, run.quotes, pick)
        rationale, cites, route = thought.value, thought.citations, thought.route
        step.route = route
        await _say(step, f"{thought.label} drafted the rationale ✓"
                         + (f" · cites {len(cites)} library passage(s)" if cites else ""))
    except ServiceError as e:
        rerr = e.message
        await _say(step, f"⚠ No rationale: {e.message} - the scores stand on their own")
    run.recommendation = sourcing.recommend(run.quotes, tp.production_quantity, rationale=rationale,
                                            rationale_error=rerr, citations=cites, generated_by=route)
    price = f"{pick.unit_price:,.2f}/unit" if pick.unit_price is not None else "price not converted"
    await _say(step, f"Recommend {pick.supplier_name} · {pick.score:.0f}/100 · {price} - "
                     f"override possible until the PO is drafted")
    # v4: brand guardrails. If the pick breaks one, the agent stops here and a person decides (approve with an
    # override, switch mill, or negotiate); nothing reaches Shopify before that.
    await decisions.gate(run, step)
    _finish(step)


async def _await_real_quotes(run: PipelineRun, step: PipelineStep) -> None:
    """Wait for real quote documents: uploads (POST /api/runs/{id}/quotes) or the inbound-email webhook."""
    s = get_settings()
    rnd = run.quote_round if run.quote_round else quotes.open_round(run)
    if rnd.status != "awaiting":  # every mill already replied (e.g. before a retry)
        await _say(step, f"All {rnd.received} quotes in ✓" if rnd.status == "complete" else
                   f"Round closed by the creative director with {rnd.received} of {rnd.expected} quotes")
        return
    inboxes = sorted({e.to_email for e in run.supplier_emails or []})
    channels = ["upload in the Quotes panel"]
    if s.evolus_webhook_secret:
        channels.append("email reply → Evolus inbound workflow → extractor → webhook")
    engine = ("Evolus document extractor" if s.evolus_extractor_live
              else "AMD LLM over the PDF text" if s.llm_live else "local PDF text parser")
    await _say(step, f"Awaiting replies - 0 of {rnd.expected} received · RFQ ref {rnd.rfq_ref}")
    await _say(step, f"Quotes arrive as documents via {' or '.join(channels)}; read by the {engine}")
    if inboxes and all(i.endswith(".test") for i in inboxes):
        await _say(step, "⚠ The RFQs went to undeliverable *.test addresses - no supplier can reply by email; set "
                         "real contacts (or an RFQ override address) in the Brand workspace")
    deadline = (asyncio.get_running_loop().time() + s.atelier_quote_wait_seconds
                if s.atelier_quote_wait_seconds > 0 else None)
    while rnd.status == "awaiting":
        await asyncio.sleep(0.1)  # real time, not scaled: we are waiting on people
        if deadline is not None and asyncio.get_running_loop().time() >= deadline:
            if run.quotes:
                rnd.status = "closed"
                rnd.closed_at = now_iso()
                await _say(step, f"Stopped waiting after {s.atelier_quote_wait_seconds:.0f}s with "
                                 f"{rnd.received} of {rnd.expected} quotes")
            else:
                raise RuntimeError(f"no supplier quotes after {s.atelier_quote_wait_seconds:.0f}s")
    if rnd.status == "closed" and rnd.awaiting:
        await _say(step, f"Round closed by the creative director with {rnd.received} of {rnd.expected} quotes · "
                         f"no reply from {', '.join(rnd.awaiting)}")
    else:
        await _say(step, f"All {rnd.received} quotes in ✓")


def _needs_price_confirmation(run: PipelineRun) -> bool:
    priced = [q for q in run.quotes or [] if q.unit_price is not None]
    return bool(priced) and all("unitPrice" in q.unverified_fields for q in priced)


async def _await_price_confirmation(run: PipelineRun, step: PipelineStep) -> None:
    """QA M10: when every comparable price was not found in its document's text, the agent doesn't pick on its own:
    a person checks a document and confirms its price (POST /api/runs/{id}/quotes/confirm)."""
    if not _needs_price_confirmation(run):
        return
    await _say(step, "✋ No quote's unit price could be found in its document text - open the document, check the "
                     "price and confirm it on the quote card to continue")
    while _needs_price_confirmation(run):
        await asyncio.sleep(0.1)


def requote(run: PipelineRun) -> None:
    """After a tech pack edit: re-score the quotes (MOQ fit depends on the run size) and refresh the recommendation.
    The mills' prices are what their documents say - an edit never re-prices a quote."""
    tp = run.tech_pack
    if not run.quotes or tp is None or run.recommendation is None:
        return
    if run.demand and run.demand.purchase_order:
        return  # the PO is locked
    sourcing.score_quotes(run.quotes, tp.production_quantity)
    run.recommendation = sourcing.recommend(run.quotes, tp.production_quantity, previous=run.recommendation)
    _sync_threshold(run)
    decisions.reevaluate(run, "techpack_changed", "creative director (tech pack edit)")  # v4


def select_supplier(run: PipelineRun, supplier_name: str) -> None:
    """Human override of the agent's pick. Raises ValueError (409) / LookupError (404) for the router.
    v4: during a guardrail hand-off this is the "switch supplier" decision; otherwise it is audited."""
    if not run.quotes or run.recommendation is None:
        raise ValueError("quotes are not in yet")
    if run.demand and run.demand.purchase_order:
        raise ValueError("the purchase order has already been drafted")
    q = next((x for x in run.quotes if x.supplier_name.lower() == supplier_name.strip().lower()), None)
    if q is None:
        raise LookupError(f"no quote from '{supplier_name}'")
    if decisions.is_open(run):
        decisions.switch(run, q.supplier_name)
        _sync_threshold(run)
        return
    run.recommendation.selected_supplier_name = q.supplier_name
    run.recommendation.overridden = q.supplier_name != run.recommendation.supplier_name
    _sync_threshold(run)
    decisions.note_supplier_override(run, q.supplier_name)


# --------------------------------------------------------------------------- step 5: demand -> PO


def _threshold(run: PipelineRun) -> tuple[int, str]:
    """The production threshold: max(productionQuantity, the chosen mill's MOQ)."""
    qty = run.tech_pack.production_quantity if run.tech_pack else 1
    q = sourcing.selected_quote(run.quotes, run.recommendation)
    if q and q.moq and q.moq > qty:  # an MOQ the quote does not state is not assumed
        return q.moq, "moq"
    return qty, "productionQuantity"


def _sync_threshold(run: PipelineRun) -> None:
    d = run.demand
    if d and d.status == "collecting":
        prod, basis = _threshold(run)
        d.production_threshold, d.production_threshold_basis = prod, basis  # type: ignore[assignment]
        if not d.stage_threshold:
            d.threshold, d.threshold_basis = prod, basis  # type: ignore[assignment]


async def _step_demand(run: PipelineRun, step: PipelineStep, design: Design) -> None:
    s = get_settings()
    product = run.shopify_product
    if product is None or preorders.shopify_meta(run) is None:
        _begin(step)
        raise NotConfigured("shopify", "No pre-order product to track - open the Shopify pre-order first")
    if not (s.shopify_admin_ready or s.shopify_webhook_key):
        _begin(step)
        raise NotConfigured("shopify", "The product is live, but Atelier can't see its orders (no Admin API "
                                       "access or webhook secret)")
    await _demand_real(run, step, design)


async def _place_po(run: PipelineRun, step: PipelineStep, quantity: int) -> None:
    """Draft the PO (persisted sequence number) and send it through Evolus when connected."""
    d = run.demand
    assert d is not None
    try:
        po = purchase_orders.create_draft(run, quantity)
    except purchase_orders.POError as e:
        await _say(step, f"✗ No purchase order: {e}")
        return
    d.purchase_order = po
    unit = f"{po.currency} {po.unit_price:,.2f}"
    await _say(step, f"{po.po_number} drafted for {po.supplier_name}: {po.quantity:,} units × {unit} = "
                     f"{po.currency} {po.total:,.2f}"
                     + (f" · {po.lead_time_weeks} wks lead time as quoted" if po.lead_time_weeks else
                        " · lead time not stated on the quote"))
    await purchase_orders.send(run, po, step.log.append)


async def _demand_real(run: PipelineRun, step: PipelineStep, design: Design) -> None:
    """Track REAL Shopify orders for the product: poll the Admin API (works from localhost) and accept the
    orders/create webhook (POST /api/webhooks/shopify/orders-create) when hosted. Both de-duplicate."""
    s = get_settings()
    _begin(step)
    product = run.shopify_product
    assert product is not None
    st = preorders.shopify_meta(run)
    assert st is not None
    prod, basis = _threshold(run)
    stage = s.demand_stage_threshold if s.demand_stage_threshold > 0 else None
    window = max(0.0001, float(s.shopify_demand_window_hours))
    tracking = []
    if s.shopify_admin_ready:
        tracking.append(f"Admin API poll every {s.shopify_poll_interval:g}s")
    if s.shopify_webhook_key:
        tracking.append("orders/create webhook")
    d = PreorderDemand(
        source="shopify",
        threshold=stage or prod, threshold_basis="stage" if stage else basis,  # type: ignore[arg-type]
        production_threshold=prod, production_threshold_basis=basis,  # type: ignore[arg-type]
        stage_threshold=stage, window_hours=int(round(window)), hours_left=window,
        series=[DemandPoint(hour=0, orders=0)], tracking=" + ".join(tracking),
        **({"currency": product.currency} if product.currency else {}),  # the store currency orders are paid in
    )
    preorders.recompute(run, d)  # orders that arrived by webhook before this step started
    run.demand = d
    basis_txt = "production run" if basis == "productionQuantity" else "supplier MOQ"
    await _say(step, f"Pre-order window open on {product.shop_domain or 'Shopify'} · tracking real orders for "
                     f"{product.product_id}")
    await _say(step, f"Production plan: {prod:,} units ({basis_txt})")
    if stage:
        await _say(step, f"Stage threshold: {stage:,} pre-orders unlock the PO for the demo "
                         f"(DEMAND_STAGE_THRESHOLD) - production plan stays {prod:,} units")
    await _say(step, f"Tracking via {d.tracking or 'nothing'} · scan the QR code to pre-order"
                     + (" (dev store: test payment gateway, card number 1)" if s.shopify_count_test_orders else ""))

    announced: set[str] = set()
    errors_in_row = 0
    while True:
        if s.shopify_admin_ready:
            try:
                for o in await shopify.orders_since(_minus_minutes(st["launchedAt"], 2)):
                    preorders.record_order(run, o, "poll")
                d.last_checked_at = now_iso()
                d.tracking_error = None
                errors_in_row = 0
            except (shopify.ShopifyError, httpx.HTTPError) as e:  # QA H4: a network blip never ends the run
                errors_in_row += 1
                d.tracking_error = str(e)[:200] or e.__class__.__name__
                if errors_in_row in (1, 5, 20) or errors_in_row % 100 == 0:
                    step.log.append(f"⚠ Order poll failed ({(str(e) or e.__class__.__name__)[:100]}) - retrying"
                                    f" with backoff")
        preorders.recompute(run, d)
        for o in reversed(d.recent_orders):
            if o.order_id not in announced:
                announced.add(o.order_id)
                sz = preorders.size_label(o)  # PII: no first name / city in step logs (they stay in the order feed)
                step.log.append(f"Order {o.name} · {o.units} unit{'s' if o.units != 1 else ''}"
                                f"{' (' + sz + ')' if sz else ''} · "
                                f"{o.amount:,.2f} {o.currency}{' · test order' if o.test else ''}"
                                f"{' · via webhook' if o.via == 'webhook' else ''}")
        hours = preorders.elapsed_hours(st)
        d.elapsed_hours = round(hours, 6)  # sub-second precision: the forecast counts orders up to launch + elapsed
        d.hours_left = round(max(0.0, window - hours), 4)
        if d.units >= d.threshold or hours >= window:
            break
        backoff = min(2 ** min(errors_in_row, 4), max(1.0, 60.0 / max(s.shopify_poll_interval, 0.01)))
        await asyncio.sleep(max(0.01, s.shopify_poll_interval) * (backoff if errors_in_row else 1))

    if d.units >= d.threshold:
        d.status = "unlocked"
        d.unlocked_at_hour = round(d.elapsed_hours, 4)
        what = "stage threshold" if stage else "threshold"
        tests = f", incl. {d.test_orders} test order{'s' if d.test_orders != 1 else ''}" if d.test_orders else ""
        await _say(step, f"{what.capitalize()} crossed: {d.units:,} pre-ordered units "
                         f"({d.orders:,} orders{tests} · {d.revenue:,.2f} {d.currency}) - production unlocked ✓")
        await _place_po(run, step, prod)
    else:
        d.status = "expired"
        await _say(step, f"Window closed at {d.units:,}/{d.threshold:,} - threshold missed, no PO drafted. The "
                         f"pre-orders stay as open orders in Shopify: Atelier does not refund or cancel them - do "
                         f"that in Shopify admin if the style won't be produced")
    _finish(step)


def sync_shopify_price(run: PipelineRun) -> None:
    """After a retail-price edit, update the real product's variant price too (background, best effort)."""
    p = run.shopify_product
    if p is None or run.tech_pack is None:
        return
    retail = run.tech_pack.target_retail_price
    p.price_brand = retail
    if p.fx_rate is None:  # same currency (or not verified): the listing price is the brand retail
        p.price = retail
    if not p.variant_id or not get_settings().shopify_admin_ready:
        return
    step = next((x for x in run.steps if x.key == "shopify_preorder"), None)

    async def go() -> None:
        try:
            lst = await listing_price(retail, p.brand_currency or run.tech_pack.currency or money.brand_currency())
            await shopify.update_price(p.product_id, list((p.variant_ids or {}).values()) or p.variant_id or "",
                                       lst["price"])
            for k, v in _listing_fields(lst).items():
                setattr(p, k, v)
            if step:
                step.log.append(f"Price updated on Shopify: {money.fmt(lst['price'], lst['currency'])}"
                                + (f" ({money.fmt(retail, lst['brand_currency'])} brand retail)"
                                   if lst["fx_rate"] is not None else ""))
        except Exception as e:  # noqa: BLE001
            log.warning("Shopify price sync failed: %s", e)
            if step:
                step.log.append(f"⚠ Shopify price update failed ({str(e)[:90]})")

    task = asyncio.create_task(go())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _minus_minutes(iso: str, minutes: int) -> str:
    from datetime import timedelta

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return (dt - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
