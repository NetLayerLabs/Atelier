"""Shopify Admin GraphQL adapter: create the real pre-order product, read real orders, verify webhooks.

Everything Shopify-specific lives here (setup: docs/SHOPIFY_SETUP.md). All calls go through
`services.http.async_client`, so tests route them to the fake in tests/fake_upstreams.py.

    POST {shop}/admin/api/{SHOPIFY_API_VERSION}/graphql.json      X-Shopify-Access-Token: <token>

Token: SHOPIFY_ADMIN_TOKEN if set; otherwise the Dev Dashboard app's client id + secret are exchanged for a
short-lived token with the client-credentials grant (POST {shop}/admin/oauth/access_token), cached and
refreshed before it expires.

Product flow (create_preorder_product):
  1. stagedUploadsCreate  -> upload the design PNG (Shopify can't fetch localhost URLs, and doesn't take SVG)
  2. productCreate        -> title, descriptionHtml, tags, status ACTIVE, media from the staged resourceUrl,
                             productOptions [{name: "Size", values: [{name: "XS"}, …]}] (v4)
  3. productVariantsBulkCreate(strategy: REMOVE_STANDALONE_VARIANT) -> one variant per size, each at the retail
                             price, inventoryPolicy CONTINUE, inventory not tracked (sellable at 0 stock) (v4)
     (no sizes -> productVariantsBulkUpdate on the single default variant, as before)
  4. publications + publishablePublish -> the Online Store channel

v4 size variants, checked against shopify.dev 2026-10 on 2026-10-13: productCreate with productOptions creates only
the first option value's variant ("Only one product variant is created…"); productVariantsBulkCreate creates the
rest, and REMOVE_STANDALONE_VARIANT deletes that standalone variant so every size is created uniformly.
Orders: LineItem.variantTitle / variant { title selectedOptions { name value } } (GraphQL); line_items[].variant_title
and properties (orders/create webhook) -> the per-line size.

Checked against shopify.dev on 2026-10-13 (API 2026-10, latest stable): SVG isn't accepted as product media
(PNG/GIF/JPEG/WEBP/HEIC only), staged image uploads are PUT with parameters as headers, Publication.name is
deprecated in favour of catalog.title, and the orders search syntax has no product filter.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from ..config import get_settings
from .http import async_client

log = logging.getLogger("atelier.shopify")

SETUP_HINT = ("set SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_TOKEN (or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET) "
              "in backend/.env - see docs/SHOPIFY_SETUP.md")


class ShopifyError(RuntimeError):
    pass


class ShopifyNotConnected(ShopifyError):
    pass


class ShopifyPartialError(ShopifyError):
    """The product exists in the store, but a later setup call failed (QA M1). `product_id` is kept on the run so a
    retry repairs that product instead of creating a duplicate."""

    def __init__(self, message: str, product_id: str):
        super().__init__(message)
        self.product_id = product_id


def _transport_error(e: httpx.HTTPError, what: str) -> ShopifyError:
    """QA H4: a network blip / timeout is a ShopifyError like any other (callers retry or report it)."""
    return ShopifyError(f"Shopify {what} unreachable ({e.__class__.__name__}: {str(e)[:120] or 'no detail'})")


# --------------------------------------------------------------------------- auth + transport

_token_cache: dict[str, tuple[str, float]] = {}  # shop base -> (token, expires at monotonic)


def clear_token_cache() -> None:
    _token_cache.clear()


def graphql_url() -> str:
    s = get_settings()
    return f"{s.shopify_base}/admin/api/{s.shopify_api_version}/graphql.json"


def shop_domain() -> str:
    s = get_settings()
    return re.sub(r"^https?://", "", s.shopify_base)


async def access_token(client: httpx.AsyncClient) -> str:
    s = get_settings()
    if s.shopify_admin_token:
        return s.shopify_admin_token
    if not (s.shopify_client_id and s.shopify_client_secret):
        raise ShopifyNotConnected("Shopify not connected - " + SETUP_HINT)
    hit = _token_cache.get(s.shopify_base)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    try:
        r = await client.post(f"{s.shopify_base}/admin/oauth/access_token", data={
            "grant_type": "client_credentials", "client_id": s.shopify_client_id,
            "client_secret": s.shopify_client_secret})
    except httpx.HTTPError as e:
        raise _transport_error(e, "token endpoint") from e
    if r.status_code >= 400:
        raise ShopifyError(_explain(r, "client-credentials token request"))
    body = r.json()
    token = body.get("access_token")
    if not token:
        raise ShopifyError("client-credentials grant returned no access_token")
    ttl = float(body.get("expires_in") or 86399)
    _token_cache[s.shopify_base] = (token, time.monotonic() + max(60.0, ttl - 300.0))
    return token


def _explain(r: httpx.Response, what: str = "Admin API") -> str:
    hint = {
        401: "token rejected (check SHOPIFY_ADMIN_TOKEN / client id + secret, and that the app is installed)",
        402: "the store is frozen / unpaid",
        403: "missing access scope (see docs/SHOPIFY_SETUP.md for the scopes)",
        404: "shop or API version not found (check SHOPIFY_STORE_DOMAIN and SHOPIFY_API_VERSION)",
        423: "the shop is locked",
        429: "rate limited",
    }.get(r.status_code, "")
    body = r.text[:200].replace("\n", " ")
    return f"Shopify {what} HTTP {r.status_code}{' - ' + hint if hint else ''}: {body}"


async def graphql(query: str, variables: Optional[dict[str, Any]] = None, *,
                  client: Optional[httpx.AsyncClient] = None) -> dict[str, Any]:
    """POST one GraphQL operation; returns `data`. Raises ShopifyError on HTTP / GraphQL errors.
    Retries once when throttled (HTTP 429 or a THROTTLED error)."""
    s = get_settings()
    if not s.shopify_admin_ready:
        raise ShopifyNotConnected("Shopify not connected - " + SETUP_HINT)
    if client is None:
        async with async_client(s.shopify_timeout) as c:
            return await graphql(query, variables, client=c)
    for attempt in range(2):
        token = await access_token(client)
        try:
            r = await client.post(graphql_url(), json={"query": query, "variables": variables or {}},
                                  headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json",
                                           "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise _transport_error(e, "Admin API") from e
        if r.status_code == 401 and not s.shopify_admin_token and attempt == 0:
            _token_cache.pop(s.shopify_base, None)  # expired client-credentials token: fetch a new one
            continue
        if r.status_code == 429 and attempt == 0:
            await asyncio.sleep(float(r.headers.get("Retry-After") or 1.0))
            continue
        if r.status_code >= 400:
            raise ShopifyError(_explain(r))
        try:
            body = r.json()
        except ValueError as e:
            raise ShopifyError(f"Shopify Admin API returned non-JSON (HTTP {r.status_code})") from e
        if not isinstance(body, dict):
            raise ShopifyError("Shopify Admin API returned an unexpected body")
        errors = body.get("errors")
        if errors:
            throttled = any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors
                            if isinstance(e, dict))
            if throttled and attempt == 0:
                await asyncio.sleep(1.0)
                continue
            msg = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
            raise ShopifyError(f"Shopify GraphQL error: {msg[:300]}")
        return body.get("data") or {}
    raise ShopifyError("Shopify kept throttling the request")


def _user_errors(payload: dict[str, Any] | None, what: str) -> None:
    errs = (payload or {}).get("userErrors") or []
    if errs:
        msg = "; ".join(f"{'.'.join(map(str, e.get('field') or []))}: {e.get('message')}".lstrip(": ")
                        for e in errs)
        raise ShopifyError(f"{what}: {msg[:300]}")


# --------------------------------------------------------------------------- ids + urls


def numeric_id(gid: str | int | None) -> str:
    """'gid://shopify/Product/123' -> '123'; '123' -> '123'."""
    if gid is None:
        return ""
    m = re.search(r"(\d+)(?:\?.*)?$", str(gid))
    return m.group(1) if m else str(gid)


def product_gid(pid: str | int) -> str:
    s = str(pid)
    return s if s.startswith("gid://") else f"gid://shopify/Product/{numeric_id(s)}"


def looks_like_product_id(v: Any) -> bool:
    return bool(v) and bool(re.fullmatch(r"(gid://shopify/Product/)?\d+", str(v)))


def admin_product_url(pid: str) -> str:
    store = shop_domain().split(".myshopify.com")[0]
    if ".myshopify.com" not in shop_domain():  # local fake / custom origin
        return f"{get_settings().shopify_base}/admin/products/{numeric_id(pid)}"
    return f"https://admin.shopify.com/store/{store}/products/{numeric_id(pid)}"


def storefront_product_url(handle: str) -> str:
    return f"{get_settings().shopify_base}/products/{handle}"


# --------------------------------------------------------------------------- shop / scopes

SHOP_QUERY = """
query AtelierShop {
  shop { name myshopifyDomain currencyCode primaryDomain { url host } }
  currentAppInstallation { accessScopes { handle } }
}"""


async def shop_info(client: Optional[httpx.AsyncClient] = None) -> dict[str, Any]:
    data = await graphql(SHOP_QUERY, client=client)
    shop = data.get("shop") or {}
    scopes = [x.get("handle") for x in ((data.get("currentAppInstallation") or {}).get("accessScopes") or [])]
    return {**shop, "scopes": [x for x in scopes if x]}


# --------------------------------------------------------------------------- product creation

STAGED_UPLOAD = """
mutation AtelierStagedUpload($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}"""

PRODUCT_CREATE = """
mutation AtelierProductCreate($product: ProductCreateInput!, $media: [CreateMediaInput!]) {
  productCreate(product: $product, media: $media) {
    product {
      id handle title status onlineStoreUrl
      options { id name optionValues { id name } }
      variants(first: 1) { nodes { id } }
    }
    userErrors { field message }
  }
}"""

VARIANTS_CREATE = """
mutation AtelierVariantsCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!,
                               $strategy: ProductVariantsBulkCreateStrategy) {
  productVariantsBulkCreate(productId: $productId, variants: $variants, strategy: $strategy) {
    productVariants { id title price inventoryPolicy selectedOptions { name value } }
    userErrors { field message }
  }
}"""

SIZE_OPTION = "Size"

VARIANTS_UPDATE = """
mutation AtelierVariantsUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id price inventoryPolicy }
    userErrors { field message }
  }
}"""

PUBLICATIONS = """
query AtelierPublications {
  publications(first: 25) { nodes { id name catalog { title } } }
}"""

PUBLISH = """
mutation AtelierPublish($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) {
    userErrors { field message }
  }
}"""

PRODUCT_QUERY = """
query AtelierProduct($id: ID!) {
  product(id: $id) {
    id handle title status onlineStoreUrl
    variants(first: 50) { nodes { id title price selectedOptions { name value } } }
  }
}"""

PRODUCT_DELETE = """
mutation AtelierProductDelete($input: ProductDeleteInput!) {
  productDelete(input: $input) { deletedProductId userErrors { field message } }
}"""


@dataclass
class CreatedProduct:
    product_id: str
    handle: str
    url: str
    admin_url: str
    variant_id: Optional[str] = None
    published: bool = False
    image_attached: bool = False
    notes: list[str] = field(default_factory=list)
    variant_ids: dict[str, str] = field(default_factory=dict)  # v4: size -> variant gid (empty: no Size option)

    @property
    def sizes(self) -> list[str]:
        return list(self.variant_ids)


def size_options_input(sizes: list[str]) -> list[dict[str, Any]]:
    """ProductCreateInput.productOptions for a Size option."""
    return [{"name": SIZE_OPTION, "values": [{"name": x} for x in sizes]}]


def size_variants_input(sizes: list[str], price: float) -> list[dict[str, Any]]:
    """productVariantsBulkCreate variants: one per size, priced, sellable at zero stock (pre-order)."""
    return [{"optionValues": [{"optionName": SIZE_OPTION, "name": x}], "price": f"{price:.2f}",
             "inventoryPolicy": "CONTINUE", "inventoryItem": {"tracked": False}} for x in sizes]


def variant_sizes(nodes: Any) -> dict[str, str]:
    """[{id, title, selectedOptions}] -> {size: variant id} for the variants that carry a size."""
    from . import sizes as _sizes

    out: dict[str, str] = {}
    for n in nodes or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        sz = _sizes.from_selected_options(n.get("selectedOptions")) or (
            None if n.get("selectedOptions") else _sizes.from_title(n.get("title")))
        if sz and sz not in out:
            out[sz] = n["id"]
    return out


def preorder_description_html(description: str, *, lead_weeks: Optional[int] = None,
                              materials: Optional[list[str]] = None) -> str:
    parts = [f"<p>{html.escape(description)}</p>"]
    if materials:
        parts.append("<ul>" + "".join(f"<li>{html.escape(m)}</li>" for m in materials[:6]) + "</ul>")
    ship = f" Ships about {lead_weeks + 2} weeks after the pre-order window closes." if lead_weeks else ""
    parts.append("<p><strong>Pre-order.</strong> This piece goes into production only once enough pre-orders "
                 f"are in.{ship} Designed with Atelier.</p>")
    return "".join(parts)


async def stage_image(client: httpx.AsyncClient, png: bytes, filename: str) -> str:
    """Upload PNG bytes via a staged upload; returns the resourceUrl to use as media originalSource."""
    data = await graphql(STAGED_UPLOAD, {"input": [{
        "resource": "IMAGE", "filename": filename, "mimeType": "image/png", "httpMethod": "PUT",
        "fileSize": str(len(png))}]}, client=client)
    payload = data.get("stagedUploadsCreate") or {}
    _user_errors(payload, "stagedUploadsCreate")
    targets = payload.get("stagedTargets") or []
    if not targets:
        raise ShopifyError("stagedUploadsCreate returned no target")
    t = targets[0]
    # Images: PUT the raw bytes, with the returned parameters sent as headers (shopify.dev product-media docs).
    hdrs = {p["name"]: p["value"] for p in t.get("parameters") or []}
    hdrs.setdefault("Content-Type", "image/png")
    try:
        r = await client.put(t["url"], content=png, headers=hdrs)
    except httpx.HTTPError as e:
        raise _transport_error(e, "staged upload") from e
    if r.status_code >= 400:
        raise ShopifyError(f"staged upload HTTP {r.status_code}: {r.text[:160]}")
    return t["resourceUrl"]


async def create_preorder_product(*, title: str, description_html: str, price: float,
                                  image_png: Optional[bytes], image_alt: str,
                                  tags: Optional[list[str]] = None, product_type: str = "",
                                  vendor: str = "Atelier", sizes: Optional[list[str]] = None,
                                  existing_product_id: Optional[str] = None,
                                  on_created: Optional[Callable[[str], None]] = None) -> CreatedProduct:
    """Create the pre-order product. With `sizes`, it gets a Size option and one variant per size (v4).

    QA M1: `on_created(product_id)` is called right after productCreate so the caller can persist the id; a later
    failure raises ShopifyPartialError (the product exists). With `existing_product_id` (a retry) that product is
    repaired - variants created / priced, published - instead of creating a duplicate."""
    s = get_settings()
    sizes = [x for x in dict.fromkeys(str(x).strip() for x in (sizes or [])) if x]
    async with async_client(s.shopify_timeout) as client:
        if existing_product_id:
            existing = (await graphql(PRODUCT_QUERY, {"id": product_gid(existing_product_id)},
                                      client=client)).get("product")
            if existing:
                try:
                    return await _finish_product(client, existing, price=price, sizes=sizes, notes=[
                        f"Re-using product {existing['id']} from the earlier attempt (no duplicate created)"],
                        image_attached=False, repair=True)
                except ShopifyError as e:
                    raise ShopifyPartialError(str(e), existing["id"]) from e
        notes: list[str] = []
        media = None
        if image_png:
            try:
                src = await stage_image(client, image_png, re.sub(r"[^a-z0-9]+", "-", title.lower())[:40] + ".png")
                media = [{"originalSource": src, "mediaContentType": "IMAGE", "alt": image_alt[:500]}]
                notes.append(f"Uploaded the design render ({len(image_png) // 1024} KB PNG) via staged upload")
            except ShopifyError as e:
                notes.append(f"⚠ Image upload failed ({str(e)[:90]}) - creating the product without media")
        product_input: dict[str, Any] = {
            "title": title, "descriptionHtml": description_html, "status": "ACTIVE",
            "tags": tags or ["pre-order", "atelier"], "vendor": vendor,
        }
        if product_type:
            product_input["productType"] = product_type
        if sizes:
            product_input["productOptions"] = size_options_input(sizes)
        data = await graphql(PRODUCT_CREATE, {"product": product_input, "media": media}, client=client)
        payload = data.get("productCreate") or {}
        _user_errors(payload, "productCreate")
        p = payload.get("product") or {}
        pid = p.get("id")
        if not pid:
            raise ShopifyError("productCreate returned no product id")
        if on_created is not None:
            on_created(pid)
        try:
            return await _finish_product(client, p, price=price, sizes=sizes, notes=notes,
                                         image_attached=media is not None, repair=False)
        except ShopifyError as e:
            raise ShopifyPartialError(str(e), pid) from e


async def _finish_product(client: httpx.AsyncClient, p: dict[str, Any], *, price: float, sizes: list[str],
                          notes: list[str], image_attached: bool, repair: bool) -> CreatedProduct:
    """Size variants (or the default variant's price) + publishing, for a new or a re-used product."""
    s = get_settings()
    pid = p["id"]
    nodes = (p.get("variants") or {}).get("nodes") or []
    variant_id = nodes[0].get("id") if nodes else None
    variant_ids: dict[str, str] = variant_sizes(nodes) if repair else {}
    if variant_ids and sizes and set(sizes) <= set(variant_ids):
        variant_id = next(iter(variant_ids.values()))
        notes.append(f"Size variants already in place ({', '.join(variant_ids)})")
        sizes = []
    else:
        variant_ids = {}
    if sizes:
        try:
            data = await graphql(VARIANTS_CREATE, {"productId": pid, "variants": size_variants_input(sizes, price),
                                                   "strategy": "REMOVE_STANDALONE_VARIANT"}, client=client)
            payload = data.get("productVariantsBulkCreate") or {}
            _user_errors(payload, "productVariantsBulkCreate")
            variant_ids = variant_sizes(payload.get("productVariants"))
            if not variant_ids:
                raise ShopifyError("productVariantsBulkCreate returned no sized variants")
            variant_id = next(iter(variant_ids.values()))
        except ShopifyError as e:
            notes.append(f"⚠ Size variants failed ({str(e)[:100]}) - selling one variant; orders will carry "
                         f"no size")
    if not variant_ids:
        if variant_id:
            data = await graphql(VARIANTS_UPDATE, {"productId": pid, "variants": [{
                "id": variant_id, "price": f"{price:.2f}", "inventoryPolicy": "CONTINUE",
                "inventoryItem": {"tracked": False}}]}, client=client)
            _user_errors(data.get("productVariantsBulkUpdate"), "productVariantsBulkUpdate")
        else:
            notes.append("⚠ productCreate returned no default variant - price not set")
    published = False
    if s.shopify_publish:
        try:
            published = await publish_online_store(client, pid)
            if not published:
                notes.append("⚠ No 'Online Store' publication found - product created but not published")
        except ShopifyError as e:
            notes.append(f"⚠ Publishing failed ({str(e)[:100]}) - needs the write_publications scope")
    url = p.get("onlineStoreUrl")
    handle = p.get("handle") or ""
    if published and not url:
        try:
            fresh = (await graphql(PRODUCT_QUERY, {"id": pid}, client=client)).get("product") or {}
            url = fresh.get("onlineStoreUrl")
            handle = fresh.get("handle") or handle
        except ShopifyError:
            pass
    return CreatedProduct(product_id=pid, handle=handle, url=url or storefront_product_url(handle),
                          admin_url=admin_product_url(pid), variant_id=variant_id, published=published,
                          image_attached=image_attached, notes=notes, variant_ids=variant_ids)


def _is_online_store(node: dict[str, Any]) -> bool:
    """The Online Store publication: `name` "Online Store", or a catalog titled "Online Store" / (as Shopify names it
    now) "Channel Catalog 218616332455 for Online Store"."""
    name = str(node.get("name") or "").strip().lower()
    title = str((node.get("catalog") or {}).get("title") or "").strip().lower()
    return name == "online store" or title == "online store" or title.endswith(" for online store")


async def publish_online_store(client: httpx.AsyncClient, pid: str) -> bool:
    pubs = (await graphql(PUBLICATIONS, client=client)).get("publications") or {}
    nodes = pubs.get("nodes") or []
    online = next((n for n in nodes if _is_online_store(n)), None)
    if online is None:
        return False
    data = await graphql(PUBLISH, {"id": pid, "input": [{"publicationId": online["id"]}]}, client=client)
    _user_errors(data.get("publishablePublish"), "publishablePublish")
    return True


async def get_product(pid: str) -> dict[str, Any]:
    data = await graphql(PRODUCT_QUERY, {"id": product_gid(pid)})
    return data.get("product") or {}


async def delete_product(pid: str) -> None:
    data = await graphql(PRODUCT_DELETE, {"input": {"id": product_gid(pid)}})
    _user_errors(data.get("productDelete"), "productDelete")


async def update_price(pid: str, variant_id: str | list[str], price: float) -> None:
    """Set the price on one variant, or on every size variant in one bulk call."""
    ids = [variant_id] if isinstance(variant_id, str) else list(variant_id)
    data = await graphql(VARIANTS_UPDATE, {"productId": product_gid(pid),
                                           "variants": [{"id": v, "price": f"{price:.2f}"} for v in ids if v]})
    _user_errors(data.get("productVariantsBulkUpdate"), "productVariantsBulkUpdate")


# --------------------------------------------------------------------------- orders


@dataclass
class OrderLine:
    product_id: str  # numeric
    quantity: int
    amount: float
    size: Optional[str] = None  # v4: from the variant's Size option / variant title


@dataclass
class Order:
    order_id: str  # gid
    name: str
    created_at: str
    test: bool
    currency: str
    first_name: Optional[str]
    city: Optional[str]
    lines: list[OrderLine]
    cancelled: bool = False

    def for_product(self, pid: str) -> tuple[int, float]:
        n = numeric_id(pid)
        units = sum(x.quantity for x in self.lines if x.product_id == n)
        amount = sum(x.amount for x in self.lines if x.product_id == n)
        return units, round(amount, 2)

    def lines_for(self, pid: str) -> list[OrderLine]:
        n = numeric_id(pid)
        return [x for x in self.lines if x.product_id == n and x.quantity > 0]


ORDERS_QUERY = """
query AtelierOrders($query: String!, $after: String) {
  orders(first: 100, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id name createdAt test cancelledAt
      currencyCode
      customer { firstName }
      shippingAddress { firstName city }
      billingAddress { firstName city }
      lineItems(first: 50) {
        nodes {
          quantity
          product { id }
          variantTitle
          variant { title selectedOptions { name value } }
          discountedTotalSet { shopMoney { amount currencyCode } }
        }
      }
    }
  }
}"""


def _money(v: Any) -> float:
    try:
        return float(((v or {}).get("shopMoney") or {}).get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_word(name: Any) -> Optional[str]:
    """Privacy: only a first name ever leaves this module (never surnames, emails or street addresses)."""
    if not name or not isinstance(name, str):
        return None
    w = name.strip().split()
    return w[0][:24] if w else None


def _city(v: Any) -> Optional[str]:
    return v.strip()[:40] if isinstance(v, str) and v.strip() else None


def line_size_graphql(li: dict[str, Any]) -> Optional[str]:
    """Size of a GraphQL LineItem: the variant's Size option, else a size-looking variant title (the variant
    may have been deleted since; `variantTitle` is the title at order time)."""
    from . import sizes as _sizes

    var = li.get("variant") or {}
    opts = var.get("selectedOptions")
    sz = _sizes.from_selected_options(opts)
    if sz or opts:  # a variant whose options have no Size (e.g. colour only) has no size
        return sz
    return _sizes.from_title(li.get("variantTitle")) or _sizes.from_title(var.get("title"))


def line_size_webhook(li: dict[str, Any]) -> Optional[str]:
    """Size of a REST/webhook line item: a 'Size' property, else a size-looking `variant_title` ('M' / 'M / Blue')."""
    from . import sizes as _sizes

    return _sizes.from_properties(li.get("properties")) or _sizes.from_title(li.get("variant_title"))


def order_from_graphql(n: dict[str, Any]) -> Order:
    ship = n.get("shippingAddress") or {}
    bill = n.get("billingAddress") or {}
    cust = n.get("customer") or {}
    lines = []
    for li in ((n.get("lineItems") or {}).get("nodes") or []):
        prod = li.get("product") or {}
        lines.append(OrderLine(product_id=numeric_id(prod.get("id")), quantity=int(li.get("quantity") or 0),
                               amount=_money(li.get("discountedTotalSet")), size=line_size_graphql(li)))
    return Order(order_id=str(n.get("id")), name=str(n.get("name") or ""), created_at=str(n.get("createdAt") or ""),
                 test=bool(n.get("test")), currency=str(n.get("currencyCode") or "USD"),
                 first_name=_first_word(ship.get("firstName") or bill.get("firstName") or cust.get("firstName")),
                 city=_city(ship.get("city") or bill.get("city")), lines=lines,
                 cancelled=bool(n.get("cancelledAt")))


def order_from_webhook(p: dict[str, Any]) -> Order:
    """orders/create webhook payload (REST shape)."""
    ship = p.get("shipping_address") or {}
    bill = p.get("billing_address") or {}
    cust = p.get("customer") or {}
    lines = []
    for li in p.get("line_items") or []:
        qty = int(li.get("quantity") or 0)
        try:
            gross = float(li.get("price") or 0) * qty
            disc = sum(float(a.get("amount") or 0) for a in li.get("discount_allocations") or [])
        except (TypeError, ValueError):
            gross, disc = 0.0, 0.0
        lines.append(OrderLine(product_id=numeric_id(li.get("product_id")), quantity=qty,
                               amount=round(gross - disc, 2), size=line_size_webhook(li)))
    gid = p.get("admin_graphql_api_id") or f"gid://shopify/Order/{p.get('id')}"
    return Order(order_id=str(gid), name=str(p.get("name") or ""), created_at=str(p.get("created_at") or ""),
                 test=bool(p.get("test")), currency=str(p.get("currency") or p.get("presentment_currency") or "USD"),
                 first_name=_first_word(ship.get("first_name") or bill.get("first_name") or cust.get("first_name")),
                 city=_city(ship.get("city") or bill.get("city")), lines=lines,
                 cancelled=bool(p.get("cancelled_at")))


async def orders_since(since_iso: str, *, max_pages: int = 5) -> list[Order]:
    """Orders created at/after `since_iso` (oldest first). Filtering by product happens client-side:
    the orders search syntax has no product filter."""
    s = get_settings()
    out: list[Order] = []
    after = None
    async with async_client(s.shopify_timeout) as client:
        for _ in range(max_pages):
            data = await graphql(ORDERS_QUERY, {"query": f"created_at:>='{since_iso}'", "after": after},
                                 client=client)
            conn = data.get("orders") or {}
            out.extend(order_from_graphql(n) for n in conn.get("nodes") or [])
            page = conn.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
    return out


# --------------------------------------------------------------------------- webhooks


def verify_webhook(raw_body: bytes, hmac_header: Optional[str], secret: str) -> bool:
    """X-Shopify-Hmac-Sha256 = base64(HMAC-SHA256(secret, raw body)); constant-time compare."""
    if not secret or not hmac_header:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, hmac_header.strip())


def sign_webhook(raw_body: bytes, secret: str) -> str:
    """The header value Shopify would send (used by tests and the fake store)."""
    return base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()
