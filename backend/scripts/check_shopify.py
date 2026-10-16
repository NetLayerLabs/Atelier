"""One-shot check of the Shopify dev-store setup in backend/.env (or the environment), against the REAL store.

    cd backend && uv run python scripts/check_shopify.py                  # all checks
    uv run python scripts/check_shopify.py --no-write                     # read-only: shop, scopes, orders
    uv run python scripts/check_shopify.py --register-webhook https://<public-host>/api/webhooks/shopify/orders-create

Checks: token (static or client-credentials grant) -> shop query -> access scopes -> create a DRAFT test product
(with the staged-upload image flow and a Size option) -> create its size variants (productVariantsBulkCreate,
REMOVE_STANDALONE_VARIANT), read them back -> delete it -> list recent orders with each line's size.
Exit code 0 only if every check passes.
Uses the app's own adapter (app/services/shopify.py), so a PASS here means the pipeline will work too.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services import shopify, sizes  # noqa: E402
from app.services.http import async_client  # noqa: E402

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = DIM = RESET = ""

REQUIRED = {"write_products": "create the pre-order product", "read_orders": "count real pre-orders"}
RECOMMENDED = {"write_publications": "publish to the Online Store", "read_products": "verify Evolus-made products"}

WEBHOOK_CREATE = """
mutation AtelierWebhookCreate($topic: WebhookSubscriptionTopic!, $sub: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $sub) {
    webhookSubscription { id }
    userErrors { field message }
  }
}"""

CHECK_SIZES = sizes.DEFAULT_SIZES
CHECK_PRICE = 1.0


async def check_variants(pid: str) -> bool:
    """productVariantsBulkCreate with the pipeline's exact payload, then read the variants back."""
    ok = True
    try:
        data = await shopify.graphql(shopify.VARIANTS_CREATE, {
            "productId": pid, "variants": shopify.size_variants_input(CHECK_SIZES, CHECK_PRICE),
            "strategy": "REMOVE_STANDALONE_VARIANT"})
        r = data.get("productVariantsBulkCreate") or {}
        errs = r.get("userErrors") or []
        made = shopify.variant_sizes(r.get("productVariants"))
        ok &= line(not errs and list(made) == CHECK_SIZES, "variants",
                   f"productVariantsBulkCreate · sizes {', '.join(made) or '-'} {errs or ''}")
        nodes = ((await shopify.get_product(pid)).get("variants") or {}).get("nodes") or []
        back = shopify.variant_sizes(nodes)
        priced = all(float(n.get("price") or 0) == CHECK_PRICE for n in nodes)
        ok &= line(list(back) == CHECK_SIZES and len(nodes) == len(CHECK_SIZES) and priced, "read back",
                   f"{len(nodes)} variant(s) · Size {', '.join(back) or '-'} · "
                   f"{'all' if priced else 'NOT all'} at {CHECK_PRICE:.2f} (standalone variant removed)")
        policies = {v.get("inventoryPolicy") for v in r.get("productVariants") or []}
        ok &= line(policies == {"CONTINUE"}, "pre-order", f"inventory policy {', '.join(map(str, policies))} "
                                                        f"(CONTINUE = sellable at zero stock)")
    except Exception as e:  # noqa: BLE001
        ok &= line(False, "variants", str(e))
    return ok


def line(ok: bool | None, name: str, msg: str) -> bool:
    tag = f"{GREEN}PASS" if ok else (f"{DIM}SKIP" if ok is None else f"{RED}FAIL")
    print(f"  {tag}{RESET}  {name:<12} {msg}")
    return ok is not False


async def main(a: argparse.Namespace) -> int:
    s = get_settings()
    print(f"Shopify check · {s.shopify_base or '(no SHOPIFY_STORE_DOMAIN)'} · API {s.shopify_api_version}")
    if not s.shopify_admin_ready:
        line(False, "config", "Shopify not connected - " + shopify.SETUP_HINT)
        return 1
    ok = True
    auth = "SHOPIFY_ADMIN_TOKEN" if s.shopify_admin_token else "client-credentials grant (SHOPIFY_CLIENT_ID/SECRET)"
    try:
        async with async_client(s.shopify_timeout) as c:
            tok = await shopify.access_token(c)
        ok &= line(True, "token", f"{auth} · {tok[:6]}…")
    except Exception as e:  # noqa: BLE001
        line(False, "token", f"{auth}: {e}")
        return 1

    try:
        info = await shopify.shop_info()
        ok &= line(True, "shop", f"{info.get('name')} · {info.get('myshopifyDomain')} · {info.get('currencyCode')}")
    except Exception as e:  # noqa: BLE001
        line(False, "shop", str(e))
        return 1

    scopes = set(info.get("scopes") or [])
    for sc, why in REQUIRED.items():
        ok &= line(sc in scopes, "scope", f"{sc:<20} ({why})")
    for sc, why in RECOMMENDED.items():
        alt = "write_channels" if sc == "write_publications" else None
        has = sc in scopes or (alt in scopes if alt else False) or (sc == "read_products" and "write_products" in scopes)
        line(True if has else None, "scope", f"{sc:<20} ({why}){'' if has else ' - recommended, missing'}")

    if a.no_write:
        line(None, "product", "skipped (--no-write)")
    else:
        try:
            import struct
            import zlib

            def tiny_png(rgb: tuple[int, int, int]) -> bytes:  # a 1x1 image for the throwaway draft product
                def chunk(t: bytes, d: bytes) -> bytes:
                    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
                return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                        + chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb))) + chunk(b"IEND", b""))

            async with async_client(s.shopify_timeout) as c:
                src = await shopify.stage_image(c, tiny_png((201, 183, 156)), "atelier-check.png")
                line(True, "upload", "staged image upload accepted")
                data = await shopify.graphql(shopify.PRODUCT_CREATE, {"product": {
                    "title": "Atelier check - delete me", "status": "DRAFT", "tags": ["atelier-check"],
                    "descriptionHtml": "<p>Created by scripts/check_shopify.py</p>",
                    "productOptions": shopify.size_options_input(CHECK_SIZES)},
                    "media": [{"originalSource": src, "mediaContentType": "IMAGE", "alt": "check"}]}, client=c)
            p = (data.get("productCreate") or {})
            errs = p.get("userErrors") or []
            pid = (p.get("product") or {}).get("id")
            ok &= line(bool(pid) and not errs, "product", f"draft created {pid} {errs or ''}")
            if pid:
                try:
                    ok &= await check_variants(pid)
                finally:
                    await shopify.delete_product(pid)
                    ok &= line(True, "delete", f"{pid} deleted")
        except Exception as e:  # noqa: BLE001
            ok &= line(False, "product", str(e))

    try:
        since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        orders = await shopify.orders_since(since, max_pages=1)
        ok &= line(True, "orders", f"{len(orders)} order(s) in the last {a.days} days")
        for o in orders[-5:]:
            units = sum(x.quantity for x in o.lines)
            who = ", ".join(x for x in (o.first_name, o.city) if x) or "(no name/city - protected data not granted?)"
            sz = ", ".join(f"{x.quantity}× {x.size or 'no size'}" for x in o.lines)
            print(f"  {DIM}      {o.name} · {o.created_at} · {units} unit(s) [{sz}] · {who}"
                  f"{' · test' if o.test else ''}{RESET}")
    except Exception as e:  # noqa: BLE001
        ok &= line(False, "orders", str(e))

    if a.register_webhook:
        try:
            data = await shopify.graphql(WEBHOOK_CREATE, {"topic": "ORDERS_CREATE", "sub": {
                "uri": a.register_webhook, "format": "JSON"}})
            r = data.get("webhookSubscriptionCreate") or {}
            errs = r.get("userErrors") or []
            ok &= line(not errs, "webhook", f"orders/create -> {a.register_webhook} {errs or ''}")
        except Exception as e:  # noqa: BLE001
            ok &= line(False, "webhook", str(e))
    secret = "set" if s.shopify_webhook_key else "not set (polling only - fine on localhost)"
    line(None if not s.shopify_webhook_key else True, "hmac", f"webhook secret {secret}")
    if s.demand_stage_threshold:
        line(True, "stage", f"DEMAND_STAGE_THRESHOLD={s.demand_stage_threshold} (shown on screen as the stage threshold)")
    print(f"\n{'All checks passed.' if ok else 'Some checks FAILED.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-write", action="store_true", help="don't create/delete the draft test product")
    ap.add_argument("--days", type=int, default=7, help="list orders from the last N days (default 7)")
    ap.add_argument("--register-webhook", metavar="URL", help="subscribe orders/create to this public URL")
    sys.exit(asyncio.run(main(ap.parse_args())))
