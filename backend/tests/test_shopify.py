"""v3: real Shopify pre-orders - product creation, order polling, the orders/create webhook, thresholds -> PO.

All Shopify traffic goes in-process to the fake dev store in tests/fake_upstreams.py (same GraphQL operations,
client-credentials grant, staged uploads), via httpx transports. No sockets, no real store.
"""

import asyncio
import json

import pytest
from conftest import go_live, route
from helpers import collecting, upload_quote
from helpers import wait as _wait

from app.services import forecast as fc
from app.services import preorders, probe, product_image, shopify, sizes
from app.store import store
from fake_upstreams import create_shopify_app, tiny_png

SHOP = "atelier-test.myshopify.com"
SECRET = "whsec_test"


@pytest.fixture
def s(s):
    shopify.clear_token_cache()
    yield s
    for meta in store.run_meta.values():  # close any still-open pre-order windows so their tasks finish
        if meta.get("shopify"):
            meta["shopify"]["launchedMono"] -= 10**9
    shopify.clear_token_cache()


@pytest.fixture
def fast_png():
    """(v5: renders are PNG already - nothing to rasterise.)"""


def connect(monkeypatch, st, app=None, **over):
    """Every service on the test doubles, with the Shopify store at SHOP."""
    app = app or create_shopify_app()
    vals = {"shopify_store_domain": SHOP, "shopify_admin_token": "shpat_fake"}
    vals.update(over)
    go_live(monkeypatch, st, **vals)
    route(shopify_app=app, **{SHOP: app})
    return app


def approve(client, qty=300, quotes=1):
    t = client.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))]).json()
    d = client.post("/api/designs/generate", json={"trendId": t["id"], "count": 1}).json()["designs"][0]
    run_id = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": qty}).json()["runId"]
    supply_quotes(client, run_id, quotes)
    return run_id, d


def supply_quotes(client, run_id, n=1):
    """Quotes are real documents: upload n throwaway quote PDFs (through the real extraction path) and close the
    round so the pipeline moves on to Shopify."""
    rnd = wait(client, run_id, lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting"
               or r["status"] != "running")["quoteRound"]
    for name in rnd["awaiting"][:n]:
        upload_quote(client, run_id, name)
    if client.get(f"/api/runs/{run_id}").json()["quoteRound"]["status"] == "awaiting":
        assert client.post(f"/api/runs/{run_id}/quotes/close").status_code == 200


def wait(client, run_id, cond, timeout=15.0):
    return _wait(client, run_id, cond, timeout)


# --------------------------------------------------------------------------- not connected


def test_not_connected_says_so_and_never_fakes(client, s, monkeypatch):
    go_live(monkeypatch, s, shopify_store_domain="", shopify_admin_token="")
    route()
    run_id, _ = approve(client)
    run = wait(client, run_id, lambda r: r["status"] != "running")
    assert run["status"] == "failed"
    steps = {x["key"]: x for x in run["steps"]}
    assert steps["techpack"]["status"] == steps["supplier_quotes"]["status"] == "done"
    sp = steps["shopify_preorder"]
    assert sp["status"] == "error" and sp["error"].startswith("Shopify not connected") and sp["retryable"]
    assert sp["service"] == "shopify" and "docs/SHOPIFY_SETUP.md" in sp["hint"]
    assert steps["preorder_demand"]["status"] == "pending"
    assert "shopifyProduct" not in run and "demand" not in run  # nothing simulated


# --------------------------------------------------------------------------- the real loop (polling)


def test_real_preorder_polling_stage_threshold_and_po(client, s, monkeypatch, fast_png):
    app = connect(monkeypatch, s, demand_stage_threshold=3, shopify_storefront_password="atelier-live")
    run_id, design = approve(client, qty=300)
    run = wait(client, run_id, collecting)
    assert run["status"] == "running", run

    # --- the product really exists in the store, sellable as a pre-order
    sp = run["shopifyProduct"]
    assert sp["source"] == "shopify" and "simulated" not in sp
    p = app.state.products[sp["productId"]]
    assert p["title"].endswith("Pre-order") and p["status"] == "ACTIVE"
    assert "pre-order" in p["tags"] and "Pre-order." in p["descriptionHtml"]
    assert float(p["price"]) == run["techPack"]["targetRetailPrice"] == sp["price"]
    assert p["inventoryPolicy"] == "CONTINUE" and p["tracked"] is False
    assert p["published"] is True
    assert p["media"][0]["mediaContentType"] == "IMAGE" and "/staged/" in p["media"][0]["originalSource"]
    assert list(app.state.uploads.values())[0][:8] == b"\x89PNG\r\n\x1a\n"  # the diffusion PNG
    assert app.state.calls[:7] == ["AtelierShop", "AtelierStagedUpload", "AtelierProductCreate", "AtelierVariantsCreate",
                                   "AtelierPublications", "AtelierPublish", "AtelierProduct"]
    # v4: a Size option with one variant per size, every one priced and sellable at zero stock
    assert [x["title"] for x in p["variants"]] == ["S", "M", "L"] == sp["sizes"]  # the brand's size range
    assert all(float(x["price"]) == sp["price"] and x["inventoryPolicy"] == "CONTINUE" and x["tracked"] is False
               for x in p["variants"])
    assert sp["variantIds"] == {x["title"]: x["id"] for x in p["variants"]}
    assert any("productVariantsBulkCreate ✓ 3 size variants" in x for x in run["steps"][3]["log"])
    assert sp["url"] == f"https://{SHOP}/products/{p['handle']}" and sp["handle"] == p["handle"]
    assert sp["adminUrl"] == f"https://admin.shopify.com/store/atelier-test/products/{p['id'].rsplit('/', 1)[1]}"
    assert sp["shortUrl"] == f"{SHOP}/products/{p['handle']}" and sp["storefrontPassword"] == "atelier-live"
    qr = client.get(sp["qrUrl"].replace("http://testserver", ""))
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml") and b"<svg" in qr.content
    steps = {x["key"]: x for x in run["steps"]}

    # --- demand: real, stage threshold clearly separate from the production plan
    d = run["demand"]
    prod = max(300, next(q["moq"] for q in run["quotes"]
                         if q["supplierName"] == run["recommendation"]["selectedSupplierName"]))
    assert d["source"] == "shopify" and "simulated" not in d and "visitors" not in d
    assert d["threshold"] == 3 and d["thresholdBasis"] == "stage" and d["stageThreshold"] == 3
    assert d["productionThreshold"] == prod
    assert any("Stage threshold: 3 pre-orders" in line and f"{prod:,} units" in line
               for line in steps["preorder_demand"]["log"])
    assert client.post(f"/api/runs/{run_id}/demand/speed", json={"speed": 12}).status_code in (404, 405)

    # --- orders arrive (another product's order and a cancelled one must not count)
    app.state.place_order(sp["productId"], first_name="Maya Rossi", city="Milan", lines=[("M", 1), ("L", 1)])
    run = wait(client, run_id, lambda r: r["demand"]["units"] >= 2)
    assert run["demand"]["status"] == "collecting" and run["demand"]["orders"] == 1
    app.state.orders.append({**app.state.orders[0], "id": "gid://shopify/Order/1", "cancelledAt": "2026-10-13T00:00:00Z"})
    app.state.orders.append({**app.state.orders[0], "id": "gid://shopify/Order/2", "lineItems": {"nodes": [
        {"quantity": 9, "product": {"id": "gid://shopify/Product/1"},
         "discountedTotalSet": {"shopMoney": {"amount": "1.00", "currencyCode": "USD"}}}]}})
    app.state.place_order(sp["productId"], 1, first_name="Jun", city="Osaka", size="S")
    run = wait(client, run_id, lambda r: r["status"] != "running")

    assert run["status"] == "completed"
    d = run["demand"]
    assert d["status"] == "unlocked" and d["units"] == 3 and d["orders"] == 2 and d["testOrders"] == 2
    assert d["revenue"] == pytest.approx(3 * sp["price"])
    assert [o["firstName"] for o in d["recentOrders"]] == ["Jun", "Maya"]  # newest first, first name only
    assert [o["city"] for o in d["recentOrders"]] == ["Osaka", "Milan"]
    blob = json.dumps(run)
    assert "Rossi" not in blob and "Lovelace" not in blob and "Private Street" not in blob  # privacy
    assert [p["orders"] for p in d["series"]] == [0, 2, 3]
    po = d["purchaseOrder"]
    assert po["quantity"] == prod and po["status"] == "sent"  # the PO is for the production plan
    assert any(line.startswith("Order #") and "Maya" not in line and "test order" in line
               and "2 units (M, L)" in line for line in run["steps"][4]["log"])
    # v4: per-line events with sizes feed the forecast; the multi-size order counts both sizes
    assert [o["lines"] for o in d["recentOrders"]] == [
        [{"size": "S", "quantity": 1, "amount": sp["price"]}],
        [{"size": "M", "quantity": 1, "amount": sp["price"]}, {"size": "L", "quantity": 1, "amount": sp["price"]}]]
    assert [(e["size"], e["quantity"]) for e in d["orderEvents"]] == [("M", 1), ("L", 1), ("S", 1)]
    assert d["orderEvents"][0]["orderId"] == d["orderEvents"][1]["orderId"] != d["orderEvents"][2]["orderId"]
    assert client.get(f"/api/runs/{run_id}/forecast").status_code == 200
    req = fc.request_for_run(store.runs[run_id])  # as_of = end of the window: the sub-second test window
    req.as_of = "2100-01-01T00:00:00Z"            # would otherwise cut orders stamped in the next second
    f = fc.forecast(req)
    by = {x.size: x for x in f.sizes}
    assert (by["M"].orders, by["L"].orders, by["S"].orders) == (1, 1, 1) and "XS" not in by
    assert f.explanation.data.sized_units == 3 and f.explanation.data.sized_orders == 2
    assert any("Stage threshold crossed: 3 pre-ordered units" in line and "incl. 2 test orders" in line
               for line in run["steps"][4]["log"])


def test_window_closes_without_po(client, s, monkeypatch, fast_png):
    connect(monkeypatch, s, shopify_demand_window_hours=0.00002)  # ~70ms
    run_id, _ = approve(client)
    run = wait(client, run_id, lambda r: r["status"] != "running")
    assert run["status"] == "completed" and run["demand"]["status"] == "expired"
    assert "purchaseOrder" not in run["demand"] and run["demand"]["threshold"] >= 300


# --------------------------------------------------------------------------- webhook


def _webhook(client, payload, secret=SECRET, topic="orders/create"):
    raw = json.dumps(payload).encode()
    return client.post("/api/webhooks/shopify/orders-create", content=raw, headers={
        "Content-Type": "application/json", "X-Shopify-Topic": topic, "X-Shopify-Webhook-Id": "w1",
        "X-Shopify-Hmac-Sha256": shopify.sign_webhook(raw, secret)})


def _payload(product_id, order_id=777, qty=1, price="249.00", first="Lea", city="Paris"):
    return {"id": order_id, "admin_graphql_api_id": f"gid://shopify/Order/{order_id}", "name": f"#{order_id}",
            "created_at": "2099-01-01T00:00:00Z", "test": True, "currency": "USD",
            "shipping_address": {"first_name": first, "last_name": "Secret", "city": city, "address1": "x"},
            "line_items": [{"product_id": int(shopify.numeric_id(product_id)), "quantity": qty, "price": price,
                            "variant_title": "M", "discount_allocations": [{"amount": "10.00"}]}]}


def test_webhook_hmac_valid_invalid_and_dedupe(client, s, monkeypatch, fast_png):
    app = connect(monkeypatch, s, demand_stage_threshold=3, shopify_webhook_secret=SECRET)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    pid = run["shopifyProduct"]["productId"]
    assert "orders/create webhook" in run["demand"]["tracking"]

    raw = json.dumps(_payload(pid)).encode()
    bad = client.post("/api/webhooks/shopify/orders-create", content=raw,
                      headers={"X-Shopify-Hmac-Sha256": shopify.sign_webhook(raw, "wrong-secret")})
    assert bad.status_code == 401
    assert client.post("/api/webhooks/shopify/orders-create", content=raw).status_code == 401  # unsigned
    tampered = client.post("/api/webhooks/shopify/orders-create", content=raw.replace(b"Lea", b"Eve"),
                           headers={"X-Shopify-Hmac-Sha256": shopify.sign_webhook(raw, SECRET)})
    assert tampered.status_code == 401
    assert client.get(f"/api/runs/{run_id}").json()["demand"]["units"] == 0

    ok = _webhook(client, _payload(pid, qty=2))
    assert ok.status_code == 200 and ok.json()["runs"] == [run_id]
    assert _webhook(client, _payload(pid, qty=2)).json()["runs"] == []  # same order again: counted once
    assert _webhook(client, _payload("gid://shopify/Product/1", order_id=778)).json()["runs"] == []
    assert _webhook(client, _payload(pid), topic="orders/updated").json()["ignored"] == "orders/updated"
    run = client.get(f"/api/runs/{run_id}").json()
    d = run["demand"]
    assert d["units"] == 2 and d["revenue"] == pytest.approx(2 * 249 - 10)
    assert d["recentOrders"][0] == {"orderId": "gid://shopify/Order/777", "name": "#777",
                                    "createdAt": "2099-01-01T00:00:00Z", "units": 2, "amount": 488.0,
                                    "currency": "USD", "firstName": "Lea", "city": "Paris", "test": True,
                                    "via": "webhook", "lines": [{"size": "M", "quantity": 2, "amount": 488.0}]}
    # the poller sees a different order; both sources add up to the stage threshold -> PO
    app.state.place_order(pid, 1, first_name="Ana", city="Porto")
    run = wait(client, run_id, lambda r: r["status"] != "running")
    assert run["demand"]["status"] == "unlocked" and run["demand"]["units"] == 3
    assert run["demand"]["purchaseOrder"]["quantity"] == run["demand"]["productionThreshold"]


def test_webhook_without_secret_is_503(client):
    r = client.post("/api/webhooks/shopify/orders-create", content=b"{}", headers={"X-Shopify-Hmac-Sha256": "x"})
    assert r.status_code == 503


def test_verify_webhook_unit():
    body = b'{"id":1}'
    sig = shopify.sign_webhook(body, "k")
    assert shopify.verify_webhook(body, sig, "k")
    assert not shopify.verify_webhook(body, sig, "other")
    assert not shopify.verify_webhook(body + b" ", sig, "k")
    assert not shopify.verify_webhook(body, None, "k") and not shopify.verify_webhook(body, sig, "")


# --------------------------------------------------------------------------- Evolus path, auth, errors


def test_evolus_product_is_used_and_verified(client, s, monkeypatch, fast_png):
    from app.services import evolus

    app = connect(monkeypatch, s, demand_stage_threshold=1, evolus_shopify_workflow_id="wf_shop")
    created = asyncio.run(shopify.create_preorder_product(title="Made By Evolus", description_html="<p>x</p>",
                                                          price=199.0, image_png=None, image_alt="x"))
    calls = []

    async def fake_exec(workflow_id, inputs, **kw):
        calls.append(workflow_id)
        return {"execution": {"output": json.dumps({"product": {"id": created.product_id}})}}

    monkeypatch.setattr(evolus, "execute_workflow", fake_exec)
    n_products = len(app.state.products)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    sp = run["shopifyProduct"]
    assert "wf_shop" in calls and len(app.state.products) == n_products  # Evolus made it; no duplicate
    assert sp["source"] == "evolus" and sp["productId"] == created.product_id
    assert sp["handle"] == "made-by-evolus" and sp["url"].endswith("/products/made-by-evolus")
    assert any("Verified in the Admin API" in line for line in run["steps"][3]["log"])
    app.state.place_order(created.product_id, 1)
    run = wait(client, run_id, lambda r: r["status"] != "running")
    assert run["demand"]["status"] == "unlocked"


def test_evolus_without_product_falls_through_to_admin_api(client, s, monkeypatch, fast_png):
    from app.services import evolus

    app = connect(monkeypatch, s, demand_stage_threshold=1, evolus_shopify_workflow_id="wf_shop")

    async def fake_exec(workflow_id, inputs, **kw):
        return {"executionId": "exe_1", "status": "Completed", "execution": {"output": "done"}}

    monkeypatch.setattr(evolus, "execute_workflow", fake_exec)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    assert run["shopifyProduct"]["source"] == "shopify"
    assert run["shopifyProduct"]["productId"] in app.state.products
    assert any("without a Shopify product id" in line for line in run["steps"][3]["log"])


def test_client_credentials_token_is_fetched_and_cached(s, monkeypatch):
    app = connect(monkeypatch, s, create_shopify_app(token="", client_id="cid", client_secret="csec"),
                  shopify_admin_token="", shopify_client_id="cid", shopify_client_secret="csec")
    info = asyncio.run(shopify.shop_info())
    assert info["myshopifyDomain"] == "fake-shop.myshopify.com" and "read_orders" in info["scopes"]
    asyncio.run(shopify.shop_info())
    assert len(app.state.issued_tokens) == 1  # cached between calls
    monkeypatch.setattr(s, "shopify_client_secret", "wrong")
    shopify.clear_token_cache()
    with pytest.raises(shopify.ShopifyError, match="401"):
        asyncio.run(shopify.shop_info())


def test_errors_are_explained(s, monkeypatch):
    app = connect(monkeypatch, s, shopify_admin_token="nope")
    with pytest.raises(shopify.ShopifyError, match="401.*token rejected"):
        asyncio.run(shopify.shop_info())
    monkeypatch.setattr(s, "shopify_admin_token", "shpat_fake")
    app.state.fail_ops.add("AtelierProductCreate")
    with pytest.raises(shopify.ShopifyError, match="productCreate: input: fake failure"):
        asyncio.run(shopify.create_preorder_product(title="x", description_html="", price=1, image_png=None,
                                                    image_alt=""))
    limited = create_shopify_app(scopes=("write_products", "read_orders"))
    connect(monkeypatch, s, limited)
    created = asyncio.run(shopify.create_preorder_product(title="No Publish Scope", description_html="",
                                                          price=10, image_png=tiny_png(), image_alt=""))
    assert created.published is False and any("write_publications" in n for n in created.notes)
    assert limited.state.products[created.product_id]["price"] == "10.00"


def test_admin_failure_without_simulation_fails_honestly(client, s, monkeypatch, fast_png):
    app = connect(monkeypatch, s)
    app.state.fail_ops.add("AtelierProductCreate")
    run_id, _ = approve(client)
    run = wait(client, run_id, lambda r: r["status"] != "running")
    assert run["status"] == "failed" and "fake failure" in run["steps"][3]["error"]
    assert "shopifyProduct" not in run


def test_price_edit_syncs_to_shopify(client, s, monkeypatch, fast_png):
    app = connect(monkeypatch, s, demand_stage_threshold=50)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    pid = run["shopifyProduct"]["productId"]
    r = client.patch(f"/api/runs/{run_id}/techpack", json={"targetRetailPrice": 321})
    assert r.status_code == 200 and r.json()["shopifyProduct"]["price"] == 321
    wait(client, run_id, lambda r: any("Price updated on Shopify" in x for x in r["steps"][3]["log"]))
    assert app.state.products[pid]["price"] == "321.00"
    assert {x["price"] for x in app.state.products[pid]["variants"]} == {"321.00"}  # v4: every size variant
    store.run_meta[run_id]["shopify"]["launchedMono"] -= 10**9  # end the window so the task finishes
    wait(client, run_id, lambda r: r["status"] != "running")


def test_health_reports_connected_store(client, s, monkeypatch):
    connect(monkeypatch, s)
    services = {x["name"]: x for x in client.get("/api/health").json()["services"]}
    assert services["shopify"]["status"] == "connected" and services["shopify"]["healthy"]
    probe.clear_cache()
    connect(monkeypatch, s, create_shopify_app(scopes=("read_products",)))
    services = {x["name"]: x for x in client.get("/api/health").json()["services"]}
    assert not services["shopify"]["healthy"] and "missing scopes" in services["shopify"]["detail"]


# --------------------------------------------------------------------------- units


def test_render_png_passes_through():
    assert product_image.to_png(tiny_png()) == tiny_png()


def test_order_normalisation_privacy():
    o = shopify.order_from_graphql({
        "id": "gid://shopify/Order/9", "name": "#1009", "createdAt": "2026-10-13T10:00:00Z", "test": True,
        "currencyCode": "EUR", "customer": {"firstName": "Zed"},
        "shippingAddress": {"firstName": "  Mary Ann ", "city": " Ghent ", "lastName": "X"},
        "lineItems": {"nodes": [
            {"quantity": 2, "product": {"id": "gid://shopify/Product/5"},
             "discountedTotalSet": {"shopMoney": {"amount": "100.50"}}},
            {"quantity": 1, "product": None, "discountedTotalSet": None}]}})
    assert (o.first_name, o.city, o.currency) == ("Mary", "Ghent", "EUR")
    assert o.for_product("gid://shopify/Product/5") == (2, 100.5) and o.for_product("6") == (0, 0)
    w = shopify.order_from_webhook({"id": 3, "name": "#3", "line_items": [{"product_id": 5, "quantity": 1,
                                                                          "price": "20.00"}]})
    assert w.order_id == "gid://shopify/Order/3" and w.first_name is None and w.for_product("5") == (1, 20.0)
    assert preorders.RECENT == 12


# --------------------------------------------------------------------------- v4: size variants


def _vars(app, op):
    return [v for name, v in app.state.variables if name == op]


def test_size_variant_creation_payloads(s, monkeypatch):
    app = connect(monkeypatch, s)
    created = asyncio.run(shopify.create_preorder_product(
        title="Sized Coat", description_html="<p>x</p>", price=249.5, image_png=None, image_alt="x",
        sizes=["S", "M", "L", "M"]))
    (pc,) = _vars(app, "AtelierProductCreate")
    assert pc["product"]["productOptions"] == [{"name": "Size", "values": [{"name": "S"}, {"name": "M"},
                                                                           {"name": "L"}]}]
    (vc,) = _vars(app, "AtelierVariantsCreate")
    assert vc["productId"] == created.product_id and vc["strategy"] == "REMOVE_STANDALONE_VARIANT"
    assert vc["variants"] == [{"optionValues": [{"optionName": "Size", "name": x}], "price": "249.50",
                               "inventoryPolicy": "CONTINUE", "inventoryItem": {"tracked": False}}
                              for x in ("S", "M", "L")]
    assert "AtelierVariantsUpdate" not in app.state.calls
    p = app.state.products[created.product_id]
    assert [x["title"] for x in p["variants"]] == ["S", "M", "L"] == created.sizes  # standalone "S" replaced
    assert created.variant_ids == {x["title"]: x["id"] for x in p["variants"]}
    assert created.variant_id == p["variants"][0]["id"]
    # the strategy matters: DEFAULT keeps the standalone custom variant "S" -> a duplicate is rejected
    with pytest.raises(shopify.ShopifyError, match="already exists"):
        async def dup():
            again = await shopify.graphql(shopify.PRODUCT_CREATE, {"product": {
                "title": "Dup", "productOptions": shopify.size_options_input(["S", "M"])}})
            pid = again["productCreate"]["product"]["id"]
            data = await shopify.graphql(shopify.VARIANTS_CREATE, {
                "productId": pid, "variants": shopify.size_variants_input(["S", "M"], 1.0), "strategy": "DEFAULT"})
            shopify._user_errors(data["productVariantsBulkCreate"], "productVariantsBulkCreate")
        asyncio.run(dup())
    # read back: the product query exposes each variant's Size
    got = asyncio.run(shopify.get_product(created.product_id))
    assert shopify.variant_sizes(got["variants"]["nodes"]) == created.variant_ids
    # a price edit reaches every size
    asyncio.run(shopify.update_price(created.product_id, list(created.variant_ids.values()), 199))
    assert {x["price"] for x in p["variants"]} == {"199.00"}


def test_size_variants_failure_falls_back_to_one_variant(s, monkeypatch):
    app = connect(monkeypatch, s)
    app.state.fail_ops.add("AtelierVariantsCreate")
    created = asyncio.run(shopify.create_preorder_product(title="Fallback", description_html="", price=50,
                                                          image_png=None, image_alt="", sizes=["S", "M"]))
    assert created.variant_ids == {} and any("Size variants failed" in n for n in created.notes)
    p = app.state.products[created.product_id]
    assert p["price"] == "50.00" and p["inventoryPolicy"] == "CONTINUE"  # the standalone variant is still sellable


def test_no_sizes_keeps_the_single_variant_flow(s, monkeypatch):
    app = connect(monkeypatch, s)
    created = asyncio.run(shopify.create_preorder_product(title="One Size", description_html="", price=12,
                                                          image_png=None, image_alt=""))
    assert "productOptions" not in _vars(app, "AtelierProductCreate")[0]["product"]
    assert "AtelierVariantsCreate" not in app.state.calls and created.sizes == []
    assert app.state.products[created.product_id]["variants"][0]["title"] == "Default Title"


def test_order_line_sizes_graphql():
    def li(**kw):
        return {"quantity": 1, "product": {"id": "gid://shopify/Product/5"},
                "discountedTotalSet": {"shopMoney": {"amount": "10.00"}}, **kw}

    o = shopify.order_from_graphql({"id": "gid://shopify/Order/1", "lineItems": {"nodes": [
        li(variant={"title": "M", "selectedOptions": [{"name": "Size", "value": "M"}]}, variantTitle="M"),
        li(variant={"title": "Indigo / l", "selectedOptions": [{"name": "Color", "value": "Indigo"},
                                                                {"name": "Size", "value": "l"}]}),
        li(variant={"title": "Indigo", "selectedOptions": [{"name": "Color", "value": "Indigo"}]}),
        li(variant=None, variantTitle="XL"),  # variant deleted since: the title at order time still says XL
        li(variant={"title": "Default Title", "selectedOptions": [{"name": "Title", "value": "Default Title"}]}),
        li(variant={"selectedOptions": [{"name": "Taglia", "value": "2XL"}]}),
    ]}})
    assert [x.size for x in o.lines] == ["M", "L", None, "XL", None, "XXL"]
    assert [x.size for x in o.lines_for("5")] == ["M", "L", None, "XL", None, "XXL"]


def test_order_line_sizes_webhook_and_multi_size_order():
    w = shopify.order_from_webhook({"id": 4, "name": "#4", "line_items": [
        {"product_id": 5, "quantity": 2, "price": "100.00", "variant_title": "M"},
        {"product_id": 5, "quantity": 1, "price": "100.00", "variant_title": "L / Indigo",
         "discount_allocations": [{"amount": "5.00"}]},
        {"product_id": 5, "quantity": 1, "price": "100.00", "variant_title": None,
         "properties": [{"name": "Size", "value": "s"}]},
        {"product_id": 6, "quantity": 1, "price": "1.00", "variant_title": "XS"},
        {"product_id": 5, "quantity": 1, "price": "100.00", "variant_title": "Default Title"}]})
    assert [(x.size, x.quantity, x.amount) for x in w.lines_for("5")] == [
        ("M", 2, 200.0), ("L", 1, 95.0), ("S", 1, 100.0), (None, 1, 100.0)]
    assert w.for_product("5") == (5, 495.0)


def test_recompute_emits_one_event_per_sized_line(client, s, monkeypatch, fast_png):
    app = connect(monkeypatch, s, demand_stage_threshold=50, shopify_webhook_secret=SECRET)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    pid = run["shopifyProduct"]["productId"]
    payload = _payload(pid, order_id=901, qty=1, price="100.00", first="Giulia", city="Rome")
    payload["line_items"] = [
        {"product_id": int(shopify.numeric_id(pid)), "quantity": 2, "price": "100.00", "variant_title": "M"},
        {"product_id": int(shopify.numeric_id(pid)), "quantity": 1, "price": "100.00", "variant_title": "L"}]
    assert _webhook(client, payload).json()["runs"] == [run_id]
    app.state.place_order(pid, 1, first_name="Ana", city="Porto", size="S")
    run = wait(client, run_id, lambda r: r["demand"]["units"] >= 4)
    d = run["demand"]
    assert d["orders"] == 2 and d["units"] == 4
    ev = [(e["size"], e["quantity"], e["unitPrice"]) for e in d["orderEvents"]]
    assert sorted(ev) == [("L", 1, 100.0), ("M", 2, 100.0), ("S", 1, run["shopifyProduct"]["price"])]
    giulia = next(o for o in d["recentOrders"] if o["firstName"] == "Giulia")
    assert [(x["size"], x["quantity"]) for x in giulia["lines"]] == [("M", 2), ("L", 1)]
    # the same order again (webhook retry or poll) still counts once
    assert _webhook(client, payload).json()["runs"] == []
    assert client.get(f"/api/runs/{run_id}").json()["demand"]["units"] == 4
    store.run_meta[run_id]["shopify"]["launchedMono"] -= 10**9
    wait(client, run_id, lambda r: r["status"] != "running")
    log = client.get(f"/api/runs/{run_id}").json()["steps"][4]["log"]
    assert any(" · 3 units (2× M, L)" in x for x in log)
    assert not any("Giulia" in x or "Rome" in x for x in log)  # PII stays out of the step log (order feed only)


def test_evolus_product_without_sizes_says_so(client, s, monkeypatch, fast_png):
    from app.services import evolus

    connect(monkeypatch, s, demand_stage_threshold=1, evolus_shopify_workflow_id="wf_shop")
    created = asyncio.run(shopify.create_preorder_product(title="Evolus One Variant", description_html="",
                                                          price=99.0, image_png=None, image_alt="x"))

    async def fake_exec(workflow_id, inputs, **kw):
        return {"execution": {"output": json.dumps({"product": {"id": created.product_id}})}}

    monkeypatch.setattr(evolus, "execute_workflow", fake_exec)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    assert "sizes" not in run["shopifyProduct"]
    assert any("No size data: it has no Size variants" in x for x in run["steps"][3]["log"])
    store.run_meta[run_id]["shopify"]["launchedMono"] -= 10**9
    wait(client, run_id, lambda r: r["status"] != "running")


def test_evolus_product_with_sizes_is_read(client, s, monkeypatch, fast_png):
    from app.services import evolus

    connect(monkeypatch, s, demand_stage_threshold=1, evolus_shopify_workflow_id="wf_shop")
    created = asyncio.run(shopify.create_preorder_product(title="Evolus Sized", description_html="",
                                                          price=99.0, image_png=None, image_alt="x",
                                                          sizes=["S", "M"]))

    async def fake_exec(workflow_id, inputs, **kw):
        return {"execution": {"output": json.dumps({"product": {"id": created.product_id}})}}

    monkeypatch.setattr(evolus, "execute_workflow", fake_exec)
    run_id, _ = approve(client)
    run = wait(client, run_id, collecting)
    assert run["shopifyProduct"]["sizes"] == ["S", "M"]
    assert any("Size variants on the Evolus product: S, M" in x for x in run["steps"][3]["log"])
    store.run_meta[run_id]["shopify"]["launchedMono"] -= 10**9
    wait(client, run_id, lambda r: r["status"] != "running")


def test_size_range_from_the_tech_pack():
    from types import SimpleNamespace as NS

    # no size in the tech pack: the brand's own range (the TEST brand sells S, M, L), else the default
    assert sizes.size_range(None) == ["S", "M", "L"]
    assert sizes.size_range(NS(size_range=None, measurements={"chest": "46in"})) == ["S", "M", "L"]
    real = sizes._brand_sizes
    sizes._brand_sizes = lambda: []
    try:
        assert sizes.size_range(None) == ["XS", "S", "M", "L", "XL"]
    finally:
        sizes._brand_sizes = real
    assert sizes.size_range(NS(size_range=["s", "m", "2XL"], measurements={})) == ["S", "M", "XXL"]
    assert sizes.size_range(NS(size_range=None, measurements={"Size range": "S – XXL (5 sizes)"})) == [
        "S", "M", "L", "XL", "XXL"]
    assert sizes.size_range(NS(size_range=None, measurements={"sizes": "S, M, L"})) == ["S", "M", "L"]
    assert sizes.size_range(NS(size_range=None, measurements={"size range (EU)": "36-44"})) == [
        "36", "38", "40", "42", "44"]
    assert sizes.size_range(NS(size_range=None, measurements={"sample size": "M"})) == ["S", "M", "L"]
    assert sizes.label(["XS", "S", "M", "L", "XL"]) == "XS – XL (5 sizes)"
    assert sizes.from_title("Default Title") is None and sizes.from_title("Indigo") is None
    assert sizes.from_title("Indigo / M") == "M" and sizes.canonical("one size") == "One Size"


def test_check_shopify_script_verifies_variants(s, monkeypatch, capsys):
    import argparse

    from scripts import check_shopify

    app = connect(monkeypatch, s)
    pid = asyncio.run(shopify.create_preorder_product(title="Has Orders", description_html="", price=10,
                                                      image_png=None, image_alt="", sizes=["S", "M"])).product_id
    app.state.place_order(pid, first_name="Giulia", city="Rome", lines=[("M", 2), ("S", 1)])
    rc = asyncio.run(check_shopify.main(argparse.Namespace(no_write=False, days=7, register_webhook=None)))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "productVariantsBulkCreate · sizes XS, S, M, L, XL" in out and "5 variant(s) · Size XS, S, M, L, XL" in out
    assert "[2× M, 1× S]" in out and "All checks passed." in out
    assert {p["title"] for p in app.state.products.values()} == {"Has Orders"}  # the check product was deleted
