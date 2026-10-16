# Shopify setup (real pre-orders)

After approval Atelier opens a **real** pre-order product in a Shopify development store, then counts the **real**
orders placed on it. Crossing the threshold drafts the purchase order and sends it to the mill through Evolus.
Nothing is simulated: without a store the step says **"Shopify not connected"**, with a Retry once you've set it up.
If the window closes below the threshold, no PO is drafted and the pre-orders stay open orders in Shopify — Atelier
does not refund or cancel them (do that in Shopify admin).

Development stores are free, take only test payments, and are always password-protected. That's what you want
for a stage demo: the audience scans a QR code, enters the store password, and checks out with test card `1`.

> **What is verified.** These steps were checked against shopify.dev and help.shopify.com on 2026-10-13 (sources
> are linked at the end). Atelier's adapter has been tested only against a local fake store that follows those docs
> (`backend/tests/fake_upstreams.py`, a test double), because there were no store credentials in that session.
> `scripts/check_shopify.py` is the first thing to run against the real store.

## 1. Create a dev store

1. Sign in at the **Dev Dashboard**, https://dev.shopify.com/dashboard/. A free Shopify Partners / developer
   account works.
2. Open **Stores**, then **Create store**, and choose **Dev**. Pick any plan (the plan only affects which features
   you can test) and a name like `atelier-demo`. Your store domain is then `atelier-demo.myshopify.com`.
   - CLI alternative: `shopify store create dev --name atelier-demo`.
3. Open the store admin once and finish the setup wizard, if it shows one.

## 2. Turn on test payments

In the store admin, open **Settings → Payments**.

- **Recommended: the test payment gateway (the old "Bogus Gateway").** If Shopify Payments or another card
  provider is active, deactivate it first. Then **Add payment method → Test payment gateway** (it may still be
  listed as *(for testing) Bogus Gateway*), and activate it.
  - At checkout, enter card number **`1`** for an approved payment (`2` is declined, `3` is a gateway failure).
    Use any future expiry date and any CVV. The order total has to be over $1.
- Alternative: **Shopify Payments → Manage → Enable test mode** and card `4242 4242 4242 4242`.

Both produce orders with `test: true`. Atelier counts them (`SHOPIFY_COUNT_TEST_ORDERS=true`, the default) and
labels each one *test* on screen.

## 3. Storefront password

Dev stores are always password-protected, and you can't remove the password page. Find or set the password
under **Online Store → Preferences → Store access → Password**. Pick something short the audience can type, such
as `atelier`. Then put it in `SHOPIFY_STOREFRONT_PASSWORD`; the demand screen shows it under the QR code (it is
shown only when that variable is set).

## 4. Create the app and get API access

Since **January 1, 2026** you can no longer create new *legacy custom apps* in the store admin (**Settings → Apps →
Develop apps**). Custom apps are created in the **Dev Dashboard**, and they don't show you a permanent `shpat_…`
token. Instead, the backend exchanges the app's **client id + secret** for a 24-hour token (the client-credentials
grant) and refreshes it by itself.

1. Dev Dashboard → **Apps → Create app → Start from Dev Dashboard**. Name it `Atelier`.
2. Open the app's **Versions** tab and set **Scopes**:

   | Scope | Why |
   |---|---|
   | `write_products` | create the product, upload its image, set price and pre-order inventory policy (includes `read_products`) |
   | `read_orders` | count the real pre-orders (the last 60 days are enough) |
   | `write_publications` | publish to the Online Store sales channel (also accepted as `write_channels`) |
   | `read_publications` | find the Online Store publication id |

   Then click **Release** to release that version.
3. **Protected customer data.** The order feed shows each buyer's **first name and city only**, and those are
   protected fields. For apps that are installed only on development stores, Shopify doesn't need a review, but you
   still have to select the data in the dashboard: request access to protected customer data, and select **Name**
   and **Address**. *Unverified:* exactly where this sits in the Dev Dashboard UI; the docs only describe the
   Partner Dashboard. Without it, orders still count, just without a name or city.
4. On the app's overview, click **Install app**, choose your dev store and confirm. The app and the store must be in
   the **same organization**, otherwise the token request fails with `shop_not_permitted`.
5. In the app's **Settings**, copy the **Client ID** and **Client secret**.

You don't need to request the token by hand, but this is what the backend does:

```bash
curl -X POST "https://atelier-demo.myshopify.com/admin/oauth/access_token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$SHOPIFY_CLIENT_ID&client_secret=$SHOPIFY_CLIENT_SECRET"
# -> {"access_token":"…","scope":"write_products,…","expires_in":86399}
```

If you still have a **legacy custom app** from before 2026, you can put its permanent `shpat_…` Admin API token in
`SHOPIFY_ADMIN_TOKEN` instead of the client id and secret.

## 5. backend/.env

```bash
# --- Shopify (real pre-orders) ---
SHOPIFY_STORE_DOMAIN=atelier-demo.myshopify.com
SHOPIFY_CLIENT_ID=<Dev Dashboard app · Settings · Client ID>
SHOPIFY_CLIENT_SECRET=<Dev Dashboard app · Settings · Client secret>
# SHOPIFY_ADMIN_TOKEN=shpat_…            # only for a legacy custom app (instead of the two lines above)
SHOPIFY_API_VERSION=2026-10              # latest stable as of 2026-10-13
SHOPIFY_STOREFRONT_PASSWORD=atelier      # shown on screen under the QR code
DEMAND_STAGE_THRESHOLD=5                 # PO unlocks at 5 real pre-orders on stage (see below)
# SHOPIFY_SHORT_URL=                     # optional: a short link you made to the product page
# SHOPIFY_WEBHOOK_SECRET=                # defaults to SHOPIFY_CLIENT_SECRET (that's what Shopify signs with)
# SHOPIFY_POLL_INTERVAL=4
```

Once the store variables are set, the pre-order is real. The product image is the diffusion model's PNG render.

**The stage threshold.** The production threshold is `max(production quantity, the chosen mill's MOQ)`, for
example 300 units. Nobody can crowd-fund that during a 3-minute demo, so `DEMAND_STAGE_THRESHOLD=5` lets 5 real
pre-orders unlock the PO instead. This is never hidden: the screen reads **"Stage threshold: 5 pre-orders
(production plan: 300 units)"**, the step log says the same, and the PO is still raised for the full production plan.
Set it to `0` to use the real production threshold.

## 6. Verify

```bash
cd backend
uv run python scripts/check_shopify.py            # token, shop, scopes, draft product + size variants create/read/delete, recent orders (with sizes)
uv run python scripts/check_shopify.py --no-write # read-only
```

Each line prints `PASS`, `FAIL` or `SKIP`, and the exit code is 0 only if every check passes. Then start Atelier
(`./dev.sh`). Under **System** in the header, **Shopify dev store** should show the store's name and be green.
Approve a design. The *Shopify Pre-order* step logs `Size option: XS – XL (5 sizes)`, `productCreate ✓`,
`productVariantsBulkCreate ✓ 5 size variants (XS, S, M, L, XL)` and `Published to the Online Store ✓`. The demand panel then shows the QR code, the store password and the orders as they arrive.

## 7. How orders reach Atelier

- **Polling (default, works on localhost).** While the window is open the backend queries the Admin API's
  `orders` every `SHOPIFY_POLL_INTERVAL` seconds (default 4): orders created since launch, matched to the product
  by its line items. The orders search syntax has no product filter.
- **Webhook (when hosted).** `POST /api/webhooks/shopify/orders-create` verifies `X-Shopify-Hmac-Sha256` (base64
  HMAC-SHA256 of the raw body, keyed with the app's client secret) and rejects anything else with 401. To
  subscribe, run:

  ```bash
  uv run python scripts/check_shopify.py --register-webhook https://<public-host>/api/webhooks/shopify/orders-create
  ```

  You can also declare the subscription in the app's configuration in the Dev Dashboard.

Both paths de-duplicate by order id, so an order that arrives both ways counts once. Cancelled orders don't count.

**Sizes.** Every line item of the product keeps its size: from the variant's `Size` option
(`lineItems { variantTitle variant { title selectedOptions { name value } } }` when polling), or from
`line_items[].properties` (a `Size` property) / `variant_title` (`"M"`, `"M / Indigo"`) in the webhook. An order for
an M and an L counts both: the demand feed shows `Giulia · Rome · M, L`, and each line becomes its own forecast event,
so the forecast's size split uses the real size mix instead of only the base curve.

## How the product is made

1. `stagedUploadsCreate` (resource `IMAGE`, `PUT`), then the PNG bytes are `PUT` to the returned URL, with the
   returned parameters as headers. Shopify can't fetch `localhost` image URLs, so the backend uploads the bytes.
2. `productCreate(product:, media:)`: the title is `<garment> — Pre-order`, the description comes from the tech
   pack plus a pre-order note, the tags are `pre-order` and `atelier`, the status is `ACTIVE`, the media is the
   staged `resourceUrl`, and `productOptions: [{name: "Size", values: [{name: "XS"}, …]}]` adds the Size option.
   The sizes are the tech pack's `sizeRange`, else a measurement whose name mentions "size" (`"size range": "S – XXL"`,
   `"sizes": "S, M, L"`), else XS, S, M, L, XL. Shopify creates only one variant here (for the first value).
3. `productVariantsBulkCreate(productId:, variants:, strategy: REMOVE_STANDALONE_VARIANT)`: one variant per size,
   `optionValues: [{optionName: "Size", name: "M"}]`, each at the tech pack's retail price, inventory policy
   `CONTINUE`, `inventoryItem: {tracked: false}`. That makes every size sellable at zero stock, which is how the
   pre-order works. `REMOVE_STANDALONE_VARIANT` deletes the variant `productCreate` made, so all sizes are created the
   same way (with `DEFAULT`, that custom standalone variant would be kept and re-creating its size would fail).
   If this call fails, the step logs `⚠ Size variants failed …` and falls back to pricing the single variant with
   `productVariantsBulkUpdate` (orders then carry no size). (Shopify selling plans with deferred payment need the
   extra `write_purchase_options` scope and more setup, so Atelier doesn't use them.)
4. `publications` (matched by `catalog.title == "Online Store"`), then `publishablePublish`.

A later retail-price edit in the tech pack editor also updates the price of every size variant on Shopify (one
`productVariantsBulkUpdate`).

**Evolus path.** If the Evolus Shopify workflow is configured (`EVOLUS_SHOPIFY_WORKFLOW_ID`, see
[EVOLUS_SETUP.md](EVOLUS_SETUP.md)) and its output contains a Shopify product id, Atelier uses that product. It
checks the product through the Admin API and tracks its orders. Otherwise Atelier creates the product directly.
Either way the product is real. Atelier reads the Evolus product's variants: if they have a `Size` option, the sizes are
used as above; if the workflow made a single variant, the step logs `⚠ No size data: it has no Size variants …` —
orders then carry no size and the forecast's size split stays on the base curve. (The workflow inputs are unchanged;
to get sizes, build the Size option inside the workflow.)

## Rehearse the plumbing without a store (test double)

The fake store is a test double: the app reports it in red as "FAKE UPSTREAM — not real". Never present it as the
product.

```bash
cd backend
uv run python tests/fake_upstreams.py --shopify-host 0.0.0.0 \
  --shopify-webhook-url http://127.0.0.1:8787/api/webhooks/shopify/orders-create
# then in backend/.env (or the environment):
SHOPIFY_STORE_DOMAIN=http://<your-LAN-IP>:18903
SHOPIFY_ADMIN_TOKEN=shpat_fake
SHOPIFY_WEBHOOK_SECRET=fake-webhook-secret
DEMAND_STAGE_THRESHOLD=3
```

The fake store serves `/products/<handle>` with a size picker and a **Pre-order** button that places a test order
for that size's variant (and sends the signed webhook, with `variant_title`). `POST /_fake/orders` takes
`{"productId", "size"}` or `{"productId", "lines": [{"size": "M", "quantity": 1}, {"size": "L"}]}` for a multi-size
order. The fake models `productCreate` + `productOptions` (one variant) and `productVariantsBulkCreate` strategies. Scan the QR code with a phone on the same network and you can rehearse the whole loop.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Step says *Shopify not connected* | `SHOPIFY_STORE_DOMAIN` plus a token or client id/secret is missing. Restart the backend after editing `.env`. |
| `401 … token rejected` | Wrong client secret or token, or the app isn't installed on this store. |
| Token request `shop_not_permitted` | The app and the store are in different organizations. |
| `Access denied … Required access: write_publications` | Add the scope, **Release** a new version, and accept the update on the store. The product is still created, just not published. |
| Orders appear without a name or city | Protected customer data (Name, Address) isn't selected for the app. |
| Product shows a placeholder image | The staged upload failed; the step log says why. The product is still created. |
| Checkout says the store isn't accepting payments | Activate the test payment gateway (section 2). |

## MCP (for the Evolus path)

- **Storefront MCP** (`https://{shop}.myshopify.com/api/mcp`) is a buyer-facing endpoint for catalog search,
  cart and policies. Its catalog and cart tools have moved to `/api/ucp/mcp`, and they need an agent profile. It
  **can't create products or read orders**, so it can't open the pre-order.
- **Dev MCP** (`npx -y @shopify/dev-mcp@latest`) runs locally and does docs and schema lookup and GraphQL
  validation for coding agents. It doesn't touch a store.
- We found **no official Shopify Admin API MCP server**, only community servers.
- We found **no public evidence that Evolus has a Shopify connector**.

So the Evolus workflow would need an HTTP step that calls the Admin GraphQL API (the same mutations as above), or a
community MCP server. Atelier doesn't depend on either: it calls Shopify directly whenever the workflow doesn't
return a product.

## Sources (read 2026-10-13)

- API versions (2026-10 is the latest stable): https://shopify.dev/docs/api/usage/versioning
- Dev Dashboard apps and installing: https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard
- Client-credentials tokens: https://shopify.dev/docs/apps/build/dev-dashboard/get-api-access-tokens
- Legacy custom apps (created before 2026-01-01): https://help.shopify.com/en/manual/apps/app-types/custom-apps
- Dev stores: https://shopify.dev/docs/apps/build/dev-dashboard/development-stores
- Password page: https://help.shopify.com/en/manual/online-store/themes/password-page
- Test payments: https://help.shopify.com/en/manual/checkout-settings/test-orders/payments-test-mode
- `productCreate`: https://shopify.dev/docs/api/admin-graphql/latest/mutations/productCreate · `productSet`:
  https://shopify.dev/docs/api/admin-graphql/latest/mutations/productSet
- Size variants (read 2026-10-13, API 2026-10): `productVariantsBulkCreate`
  https://shopify.dev/docs/api/admin-graphql/latest/mutations/productVariantsBulkCreate · strategy enum
  https://shopify.dev/docs/api/admin-graphql/latest/enums/ProductVariantsBulkCreateStrategy · variant input
  https://shopify.dev/docs/api/admin-graphql/latest/input-objects/ProductVariantsBulkInput · `tracked`
  https://shopify.dev/docs/api/admin-graphql/latest/input-objects/InventoryItemInput · `LineItem.variant` /
  `variantTitle` https://shopify.dev/docs/api/admin-graphql/latest/objects/LineItem · webhook `line_items[].variant_title`
  / `properties` https://shopify.dev/docs/api/admin-rest/latest/resources/order
- Product media formats and staged uploads: https://shopify.dev/docs/apps/build/online-store/product-media
- `publishablePublish`: https://shopify.dev/docs/api/admin-graphql/latest/mutations/publishablePublish ·
  `Publication`: https://shopify.dev/docs/api/admin-graphql/latest/objects/Publication
- `orders` query: https://shopify.dev/docs/api/admin-graphql/latest/queries/orders · scopes:
  https://shopify.dev/docs/api/usage/access-scopes
- Protected customer data: https://shopify.dev/docs/apps/launch/protected-customer-data
- Webhook HMAC: https://shopify.dev/docs/apps/build/webhooks/subscribe/https · headers:
  https://shopify.dev/docs/apps/build/webhooks/delivery-structure
- Storefront MCP: https://shopify.dev/docs/apps/build/storefront-mcp/servers/storefront · Dev MCP:
  https://shopify.dev/docs/apps/build/devmcp
