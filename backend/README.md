# Atelier backend

FastAPI service implementing [`../CONTRACT.md`](../CONTRACT.md) for the Atelier Creative Director dashboard.

**There is no mock mode** (CONTRACT.md "v5"). Every model, workflow and store call goes to the real service you
configure. A service that is not configured, or fails, surfaces as an honest error — a `503 {detail, service,
status, hint}` for a request, or a pipeline step in `error` with a setup hint and a retry — never as made-up output.
With no `.env` at all the API starts and every service reports **not connected**.

## Run

```bash
cd backend
uv sync                                   # installs deps into .venv
uv run uvicorn app.main:app --reload --port 8787
```

- API docs: http://localhost:8787/docs
- What is connected: http://localhost:8787/api/health
- Tests: `uv run pytest -q` (all external traffic goes to the in-process test doubles in `tests/fake_upstreams.py`).

The default CORS origins are `http://localhost:3100` (and `:3000`), on both `localhost` and `127.0.0.1`. Set `CORS_ORIGINS` to change them.

## Layout

```
app/
  main.py            app factory, CORS, {detail} error handlers, ServiceError -> 503 with a hint, /static
  config.py          pydantic-settings; a service is "configured" when its env vars are set
  models.py          contract models (snake_case in Python, camelCase on the wire)
  store.py           in-memory store
  pipeline.py        approve -> techpack -> outreach -> quotes & recommendation -> shopify pre-order
                     -> demand validation -> PO; failed steps resume with POST /api/runs/{id}/retry
  routers/           health, trends, designs, direction, runs (+ quote upload, retry, PO send, storefront QR),
                     forecast, guardrails, voice, telemetry, webhooks (Shopify orders/create + inbound quotes)
  services/
    errors.py        ServiceError / NotConfigured + the setup hints
    vision.py        trend analysis on the VLM (OpenAI-compatible); `analyze(images)` or a ServiceError
    diffusion.py     prompt builder + the diffusion server adapter; renders only from the live server
    brain.py         Evolus agent -> AMD vLLM, else direct vLLM; schema-validated JSON, one retry, citations
    llm.py           tech pack + RFQ drafting through the brain
    direction.py     creative direction interpreted by the brain; lineage state (palette, fabrics, hints)
    collection.py    capsule collections planned by the brain
    knowledge.py     grounding passages / citations from the Brand workspace (uploaded brand book, generated
                     supplier catalogue + brand profile) and the Evolus library upload
    workspace.py     v5 the Brand workspace: SQLite store of the brand's own data + readiness gate
    workspace_import.py v5 CSV/XLSX importers (validation, provenance), PDF/DOCX/MD text extraction
    quotes.py        real quote documents: upload / webhook -> extractor chain -> SupplierQuote; the RFQ round
    fx.py            ECB daily euro reference rates (cached a day) for quotes in another currency
    sourcing.py      weighted scoring (workspace weights) over the criteria a quote states + the brain's rationale
    guardrails.py    brand guardrails (set in the Brand workspace): deterministic checks + counter-offer target maths
    decisions.py     human hand-off: decision state machine, counter-offers (brain + Evolus), audit trail
    i18n.py          number formats, language detection, note translation (brain; else "untranslated")
    purchase_orders.py  real POs: persisted per-brand number, sent through the Evolus PO workflow
    sequences.py     persisted per-brand sequences (PO-00001, ST-00001) in ATELIER_DATA_DIR
    evolus.py        Evolus adapter: workflows, agent chat, extractor, library, AI Tools
    openai_compat.py robust JSON parsing, retry, model auto-discovery
    shopify.py       Shopify Admin GraphQL: product create/publish, orders, webhook HMAC
    preorders.py     folds real orders (poll + webhook, de-duplicated) into the demand window
    product_image.py the diffusion PNG for Shopify media
    forecast.py      explained production forecast: Gamma-Poisson on a Bass launch curve + newsvendor
    techpack_pdf.py  factory tech pack PDF (ReportLab)
    voice.py         customer voice: deterministic taxonomy counts + quotes; the brain drafts instructions
    telemetry.py     measured inference calls only
    probe.py         cached health probes (flags the test double)
  data/              mood-board manifest loader; suppliers.py / materials.py read the Brand workspace
  workspace_models.py v5 Brand workspace models (CONTRACT.md "v5")
static/              generated/ (diffusion renders), uploads/ (mood boards), quotes/ (quote documents),
                     moodboards/ (preset boards: real, openly licensed photos + manifest.json + ATTRIBUTION.md)
var/                 the data dir (ATELIER_DATA_DIR; git-ignored): atelier.sqlite3 + files/ (Brand workspace),
                     sequences.json (PO / style numbers)
tests/               pytest suite + fake_upstreams.py, vision_double.py, workspace_fixture.py (TEST DOUBLES / TEST
                     data — never part of the app)
```

## Services

Copy `.env.example` to `.env`. Each service is used when its variables are set; otherwise the features that need
it say **not connected** with the variable(s) to set:

| Service | Configured by | Without it |
|---|---|---|
| vision | `AMD_VISION_ENDPOINT` | mood boards can't be analysed (503 + hint) |
| diffusion | `AMD_DIFFUSION_ENDPOINT` | no concepts can be rendered (503 + hint) |
| brain: Evolus agent | `EVOLUS_API_KEY`, `EVOLUS_WORKSPACE_ID`, `EVOLUS_AGENT_MODEL` | the brain uses direct vLLM |
| brain: direct vLLM | `AMD_VLLM_ENDPOINT` | with neither brain path: tech pack / RFQs / direction / collection / counter-offers fail honestly |
| evolus_extractor | `EVOLUS_EXTRACTOR_AGENT_ID`, `EVOLUS_EXTRACTOR_ID` | quote documents are read by the AMD LLM over the PDF text, else a local parser of the PDF text (both read the real document) |
| evolus_outreach | `EVOLUS_OUTREACH_WORKFLOW_ID` (+ key, workspace) | RFQs are drafted but not sent: the step errors with a retry |
| counter-offers | `EVOLUS_NEGOTIATION_WORKFLOW_ID`, else the outreach workflow | the draft is kept, not sent (503 + hint) |
| purchase orders | `EVOLUS_PO_WORKFLOW_ID`, else the outreach workflow | the PO stays "draft — not sent" with a send action |
| evolus_shopify (optional) | `EVOLUS_SHOPIFY_WORKFLOW_ID` | Atelier calls the Shopify Admin API directly |
| shopify | `SHOPIFY_STORE_DOMAIN` + `SHOPIFY_CLIENT_ID`/`SECRET` (or `SHOPIFY_ADMIN_TOKEN`) | "Shopify not connected": nothing is listed, no demand |
| FX | `ATELIER_FX_URL` (default: the ECB daily XML) | a quote in another currency stays in it, marked "not converted" |

Every brain call validates the model's JSON against a schema and retries once; then it is an error. Nothing falls
back to a template.

`GET /api/health` probes every configured service (2.5s timeout, cached 5s; Evolus 30s) and reports
`status: connected | unreachable | not_configured`, a `hint`, the served `model` and the `gpu` label.
`poweredBy` says which credits may be shown (only real, connected services). An endpoint whose responses carry
`X-Atelier-Fake-Upstream` (the test double) is reported `fake: true`, "FAKE UPSTREAM — not real", and never counts.

`GET /api/telemetry` returns measured calls only: latency, TTFT, tokens and tok/s from the server's `usage`,
images/s. It is empty until real calls happen.

**Going live:**
- [`docs/AMD_SETUP.md`](../docs/AMD_SETUP.md): AMD Developer Cloud, vLLM, diffusion, SSH tunnel. Verify with
  `uv run python scripts/check_amd.py`.
- [`docs/EVOLUS_SETUP.md`](../docs/EVOLUS_SETUP.md): workspace, workflows, keys. Verify with
  `uv run python scripts/check_evolus.py` (`--quote-pdf <a real quote>` to test the extractor).
- [`docs/SHOPIFY_SETUP.md`](../docs/SHOPIFY_SETUP.md): dev store and app. Verify with `scripts/check_shopify.py`.

### Rehearsing without credentials (test doubles)

`uv run python tests/fake_upstreams.py` starts local **test doubles** of vLLM, the diffusion server, Evolus and a
Shopify dev store (ports 18900-18903). They answer with canned data and mark every response, so `/api/health`
shows them in red as "FAKE UPSTREAM — not real" and the AMD / Evolus credits are never shown. Use them to rehearse
the plumbing, never as a demo of the product.

### AMD Developer Cloud (vLLM on ROCm)

The full walkthrough is in [`docs/AMD_SETUP.md`](../docs/AMD_SETUP.md). In short, on the MI300X droplet run
`cp deploy/env.example deploy/.env`, set `VLLM_API_KEY` and `HF_TOKEN`, then `./deploy/serve_all.sh`. That starts:
- `google/gemma-4-26B-A4B-it` on :8000 — text **and** vision, one server (gemma4 tool/reasoning parsers)
- FLUX.1-schnell on :8002
- (optional, only with `VLM_MODEL` set) a separate vision server on :8001

On the laptop, run `./deploy/tunnel.sh <ip>`, then put this in `backend/.env`:

```bash
AMD_VLLM_ENDPOINT=http://127.0.0.1:18000/v1
AMD_VLLM_API_KEY=<VLLM_API_KEY>
AMD_VISION_ENDPOINT=http://127.0.0.1:18000/v1   # the same Gemma 4 server
AMD_DIFFUSION_ENDPOINT=http://127.0.0.1:18002/generate
AMD_GPU_LABEL=AMD Instinct MI300X     # what rocm-smi reports; shown in the Inference panel
ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
```

Uploaded images are sent to the VLM as base64 `data:` URLs (OpenAI `image_url` parts, images before the text, as
Gemma 4 recommends), so the GPU box never has to reach your laptop. `imageUrls` are passed through as-is. At most
`ATELIER_VISION_MAX_IMAGES` (4, = the server's `--limit-mm-per-prompt`) go into the prompt, on the retry too; the
analysis reports `analyzedBy.imagesAnalyzed` / `imagesSubmitted` and the UI says when only the first 4 were read.
Model replies are parsed by `openai_compat.extract_json`, which strips leaked reasoning (`<|channel>thought…`,
`<think>…`) and stray control tags before the JSON.

### Diffusion

`app/services/diffusion.py::_call_diffusion_endpoint` is the only function that knows the wire format:

```
POST {AMD_DIFFUSION_ENDPOINT}  {"prompt","negative_prompt","seed","width","height"}  ->  {"images": ["<base64 png>"]}
```

PNGs are saved to `static/generated/` and returned as absolute URLs built from `PUBLIC_BASE_URL`.

### Evolus

The adapter follows the public docs at https://evolus.ai/developers: `X-ApiKey` + `X-Application-Id`, `POST
/api/v1/workflows/{id}/execute` (multipart `input` + flat `parameters`, 202 + `executionId`), then polling
`GET …/executions/{executionId}` until `Completed` or `Failed`. Paths are env-configurable.

- Outreach parameters: `garment_name`, `production_quantity`, `tech_pack`, `image_url`, `rfq_emails`, `rfq_ref`.
- Counter-offer: the same flat shape, one email, plus `kind=counter_offer`, `quote_number`, `target_unit_price`,
  `currency`.
- Purchase order: the same flat shape (one email, so the outreach workflow can send it) plus `kind=purchase_order`,
  `po_number`, `supplier_name`, `to_email`, `quantity`, `unit_price`, `currency`, `total`, `rfq_ref`,
  `quote_number`. The PO is `sent` when the run's output says so, `queued` when the run completed without saying.
- Shopify parameters: `title`, `description`, `price`, `image_url`, `handle`, `production_quantity`.

Recipients always come from the supplier directory (`data/suppliers.inbox_for`), never from model output.

RFQs go to the brand's own suppliers from the Brand workspace: each supplier's RFQ override address if the brand
set one (e.g. its own sourcing inbox during a pilot), else its first contact email. Recipients never come from model
output, and nothing is sent before the brand confirmed the directory.

### Quotes

Quotes only come from real documents: upload (`POST /api/runs/{id}/quotes`) or an inbound email through the Evolus
workflow -> extractor -> `POST /api/webhooks/evolus/quote`. A field the document does not state stays empty and is
shown as "not stated"; scoring and guardrails never assume it (an unstated lead time or MOQ fails its guardrail and
a person decides). Other currencies are converted with the ECB reference rate of the day (`fxRate`, `fxDate`); if
the rates can't be loaded the quote stays in its own currency, unconverted, and says so.

### Guardrails and hand-off

`services/guardrails.py` checks every quote (no model): gross margin floor, unit-cost cap (absolute, or the tech
pack costing × (1 + headroom) if the brand set a headroom), lead time, MOQ, certifications (from the supplier
directory; expired certificates don't count). v5: the brand sets them in the Brand workspace (`PUT /api/guardrails`,
persisted); there are no defaults, and a rule left empty is not checked (`Guardrails.unset` lists them). If the pick
breaks one, `services/decisions.py` opens a decision and the pipeline waits until a person approves (an override, in
the audit log), switches supplier, or negotiates. The counter-offer target is deterministic; the brain writes the
wording in the supplier's language with an English version, and a draft that drops the number is rejected (an
error, not a template). Sending needs Evolus.

### Purchase orders

When real pre-orders reach the threshold, `services/purchase_orders.py` drafts a PO for the selected supplier: the
next number of the brand's persisted sequence (`sequences.json` in `ATELIER_DATA_DIR`, next to the workspace), the
quoted unit price in the quoted currency, the lead time only if the quote stated one, and the supplier's directory
address. It is sent through the Evolus PO workflow and the result recorded. Without Evolus it stays "draft — not
sent" (`POST /api/runs/{id}/purchase-order/send` sends it later).

### Demand

With a Shopify store connected the demand step counts **real orders** (Admin API poll + `orders/create` webhook).
`DEMAND_STAGE_THRESHOLD` sets a labelled stage threshold for a live demo (the production plan stays visible).
Test (Bogus Gateway) orders are counted and always labelled. When the window closes below the threshold no PO is
drafted; the pre-orders stay open orders in Shopify — Atelier does not refund or cancel them.
