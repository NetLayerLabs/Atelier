# Evolus setup (v3: the agent's brain and real supplier quotes)

This guide makes Evolus the agent's brain and the way real supplier quotes come in.

> **As deployed for the hackathon (17 Oct 2026).** The agent's model is **Gemma-4-31B-IT on AMD GPUs through AMD
> Token Factory**, registered under "Your models" in the Evolus event workspace (the organisers confirmed this
> counts as our own model on AMD). No self-hosted vLLM is connected, so the brain chain is `evolus-agent → AMD
> Token Factory` only; the route labels below that say `AMD vLLM` describe the self-hosted setup. Building blocks
> live in the workspace: the agent, a knowledge library (brand book, brand profile, supplier catalogue), the
> "Supplier quote" extractor, and the two email workflows built by `scripts/provision_evolus_workflows.py`
> (RFQs + counter-offers; purchase orders). Quotes are uploaded on the Quotes panel; the inbound-email workflow
> and the AI Tool are optional and not set up. Quotes in another currency are converted with the ECB reference
> rates when they load; otherwise the quote stays in its own currency and says so.

**What you set up.** The tech pack, RFQs, creative direction and supplier rationale are all written by an
**Evolus agent whose model is our AMD vLLM endpoint**, grounded in a **knowledge library**. RFQs go out through an
**Evolus workflow**. Mills reply with **PDF quotes**, which an **Evolus document extractor** reads. Each quote
either arrives by email through an inbound workflow that calls our webhook, or is dropped onto the dashboard.

**What the judges see.** The connected AMD model, five building blocks, and every Atelier API call in the workspace
usage statistics.

> **Verification status.**
>
> - **From the public docs** (https://evolus.ai/en/developers): auth, agent chat, extractor `ask-file`, library
>   upload, AI Tools, workflow execute and poll, and the MCP server.
> - **From the Evolus web app's API client, not the public docs:** creation endpoints, citations, email triggers and
>   webhook headers. See [EVOLUS_API_NOTES.md](EVOLUS_API_NOTES.md) for the source of every fact.
> - **Tested against the real event workspace (2026-10-16):** the agent chat, and both email workflows (section 6A),
>   with test emails to the owner's own inbox. The unit tests also run every call against a local test double
>   (`backend/tests/fake_upstreams.py`), which the app reports as "FAKE UPSTREAM — not real".
> - **Configurable.** Paths and headers can be changed through env vars, so fixes on site need no code changes.

## Building blocks this demonstrates

| # | Block | What Atelier does with it | Config |
|---|---|---|---|
| 1 | **Agent chat, bring-your-own model on AMD** | The brain. `POST /v1/chat/completions` with model `<spaceId>:<agentId>` writes the tech pack, RFQs, creative direction and supplier rationale. The agent runs on our vLLM model on AMD. | `EVOLUS_AGENT_MODEL` |
| 2 | **Knowledge library** | The brand book and supplier catalogue, attached to the agent. Outputs cite it. | `EVOLUS_LIBRARY_ID` |
| 3 | **Document extractor** | Reads the mills' PDF quotes into a fixed schema, for both uploads and email. | `EVOLUS_EXTRACTOR_AGENT_ID`, `EVOLUS_EXTRACTOR_ID` |
| 4 | **Workflows** | (A) "Atelier — send RFQ emails" sends the RFQs and counter-offers, and "Atelier — send purchase order" sends the POs, both from the Evolus mailbox (built by `scripts/provision_evolus_workflows.py`). (B) Inbound: a mill emails a quote, the extractor reads it, and a webhook calls Atelier. (C, optional) Shopify pre-order. | `EVOLUS_OUTREACH_WORKFLOW_ID`, `EVOLUS_INBOUND_WORKFLOW_ID`, `EVOLUS_SHOPIFY_WORKFLOW_ID`, `EVOLUS_PO_WORKFLOW_ID` |
| 5 | **AI Tools** (optional) | The `email` tool polishes each RFQ. | `EVOLUS_RFQ_AI_TOOL=true` |
| (6) | **MCP** | The Evolus MCP server in Claude Code builds the workspace (see the end of this guide). The Shopify workflow can use an MCP connector. | — |

**The brain's chain.** Telemetry, the pipeline step tag and the Inference panel all show which path ran:

1. `evolus-agent → AMD vLLM`
2. `direct vLLM` (only if the agent call fails)

There is no template fallback: if neither answers with valid JSON (one retry each), the step stops with an error,
a setup hint and a **Retry** button.

**Supplier quotes are never simulated.** The quotes step waits for real documents and shows "Awaiting replies — 1
of 3 received".

---

## 0. Before you start

- **The AMD vLLM endpoint must be publicly reachable.** Follow [AMD_SETUP.md](AMD_SETUP.md):
  `deploy/serve_llm.sh` binds port 8000 publicly with `--api-key` and tool calling enabled. Evolus runs in the
  cloud, so it can't use your SSH tunnel. Plain `http://` is accepted only with an **IP address**; a domain name
  needs `https://`.
- **The brand's sourcing inbox (pilot).** RFQs go to the real suppliers in the brand's Brand workspace. During a
  pilot the brand can route them to its own sourcing inbox instead: set each supplier's **RFQ email override** (or
  "Apply to all") in Brand workspace → Suppliers. The inbound workflow watches the inbox the replies arrive in:
  1. Turn on 2-step verification.
  2. Create an **app password**.
  3. Make sure IMAP is enabled.

  Nothing is sent before the brand has confirmed the supplier contacts in the workspace.
- **A public URL for Atelier's webhook.** Atelier must be reachable from Evolus for the email path. Use a
  quick tunnel, `cloudflared tunnel --url http://localhost:8787`, and note the `https://….trycloudflare.com` URL.
  The upload path works without one.

## 1. Workspace, API key, model

1. Register on lablab.ai and in the AMD AI Developer Program, then open **https://app.evolus.ai/join/AMDACT3**.
   Sign in and create the team workspace. Only workspaces created from this link are event workspaces.
2. Open **API keys** and create an application key with **Full access**. Copy the key and the **Space ID** shown
   on the same page.
3. Optional: under **Profile → API keys**, create a personal key. Library calls may need it.
4. Open **Models** and choose **Add model** (OpenAI-compatible). This is our own vLLM endpoint on AMD Developer
   Cloud serving **Gemma 4** (`deploy/serve_llm.sh`, see [AMD_SETUP.md](AMD_SETUP.md)) — the same server Atelier
   uses directly for text and vision:

   | Field | Value |
   |---|---|
   | Base URL | `http://<droplet-ip>:8000/v1` |
   | Model | exactly what `GET /v1/models` on the droplet reports: `google/gemma-4-26B-A4B-it` |
   | API key | `VLLM_API_KEY` from `deploy/.env` |
   | Name | e.g. `gemma-4-26B-A4B-it` (this becomes `EVOLUS_OWN_MODEL_NAME`) |

   Click **Test connection**. It checks a short answer, a tool call, streaming and reasoning levels. Tool calling
   works because `serve_llm.sh` starts vLLM with `--enable-auto-tool-choice --tool-call-parser gemma4` and the
   Gemma 4 tool chat template; reasoning is split out by `--reasoning-parser gemma4`. If the tool call fails, check
   `docker logs atelier-llm` for those flags (they are picked from the model name; `LLM_TOOL_PARSER` overrides) and
   run `uv run python scripts/check_amd.py`, which does the same tool-call round trip. For a Qwen model instead,
   the scripts switch to `qwen3_coder` / `qwen3` (not a Gemma model: it doesn't count for the Google prize).

## 2. Fast path: provision by API

Put the key, the space id and `EVOLUS_OWN_MODEL_NAME` in `backend/.env` (section 7), then:

```bash
cd backend
uv run python scripts/build_knowledge.py            # supplier catalogue + brand profile PDFs from the workspace
uv run python scripts/provision_evolus.py --dry-run # what it will create
uv run python scripts/provision_evolus.py --all --webhook-url https://<tunnel>/api/webhooks/evolus/quote
```

The script:

1. Creates the library "<brand> knowledge" and uploads, with `language=en`, the brand-book files uploaded in the
   Brand workspace plus the generated supplier catalogue and brand profile PDFs. (Brand-book files uploaded in the
   workspace while `EVOLUS_LIBRARY_ID` is set are also sent to the library straight away.)
2. Creates the agent on `own/<model name>` and attaches the library.
3. Creates an extractor agent and a "Supplier quote" extractor.
4. Creates the outbound webhook with the `X-Atelier-Webhook-Secret` header.

It prints the `.env` lines to add. These creation endpoints come from the web app's client, not the public docs.
**If a step fails, do that step in the UI (sections 3–5)**; the others are still valid. You still build the two
workflows in the UI (section 6).

## 3. Knowledge library (UI path)

1. Open **Libraries** and choose **New library**, named after the brand (e.g. "<brand> knowledge").
2. Upload the brand's brand book (the file from the Brand workspace) and the PDFs `scripts/build_knowledge.py` writes
   to `$ATELIER_DATA_DIR/knowledge/` (supplier catalogue, brand profile). Set the language to **English**; the API
   default is Italian.
3. Wait until the documents show as indexed.
4. Copy the library id from the URL into `EVOLUS_LIBRARY_ID`. From then on, brand-book uploads in the workspace go
   to the library automatically.

Re-run `scripts/build_knowledge.py` and re-upload the catalogue after the supplier directory changes. The generated
catalogue never contains contact addresses.

## 4. The agent (the brain)

1. Open **Agents** and choose **New agent**, named "Atelier Sourcing & Tech Design".
2. Set **Model** to your AMD model from step 1.4 — the Gemma 4 entry (`own/gemma-4-26B-A4B-it` by API). This is
   the requirement the judges check: the agent runs on our own vLLM endpoint on AMD Developer Cloud.
3. Paste in the **Prompt** from `AGENT_PROMPT_TEMPLATE` in `backend/scripts/provision_evolus.py` (with the brand's
   name). In short: follow the
   brand book and catalogue; when asked for JSON, answer with only the JSON and include `"sources"`; never invent
   supplier prices.
4. Under **Libraries / Knowledge**, attach the brand's library.
5. Copy the model string. `GET https://api.evolus.ai/v1/models` (Bearer key) lists `<spaceId>:<agentId>`, and so
   does `scripts/check_evolus.py`. Put it in `EVOLUS_AGENT_MODEL`.

`EVOLUS_AGENT_TRANSPORT=openai` (the default) uses the documented `/v1/chat/completions`. Set it to `rest` to use
`/api/v1/agents/{id}/ask`, which also returns the library's own citations; those show in the UI as "Evolus
library".

## 5. Document extractor: "Supplier quote"

1. Create an agent "Atelier Quote Reader" (extractor) on your AMD model.
2. In it, add a **JSON extractor** named "Supplier quote". Turn **OCR** on, so scanned quotes work.
3. Use this prompt: *Extract the supplier quotation. Copy values as printed on the document; leave a field empty
   when it is not on the document. Never estimate or invent numbers.*
4. Add these fields. The JSON Schema form is `EXTRACTOR_SCHEMA` in `backend/app/services/quotes.py`.

   | Field | Type | Description |
   |---|---|---|
   | `supplier_name` | text | Company name on the letterhead (required) |
   | `supplier_email` | text | Sender / contact email |
   | `quote_number` | text | Quote / quotation / offer number |
   | `quote_date` | text | Date of the quote |
   | `valid_until` | text | Validity / expiry date |
   | `rfq_reference` | text | Buyer's reference, e.g. `ATL-run_ab12cd` |
   | `style_name` | text | Garment / style quoted |
   | `currency` | text | ISO code (USD, EUR, …) |
   | `unit_price` | number | Price per finished piece, full package (required) |
   | `moq` | number | Minimum order quantity per colour (required) |
   | `lead_time` | text | Bulk lead time as printed, "8 weeks" / "42 days" (required) |
   | `sample_cost` | number | Development / sample cost |
   | `payment_terms` | text | As printed |
   | `incoterm` | text | FOB, EXW, CIF, … |
   | `notes` | text | The mill's message, verbatim |

5. **Leave the extractor's own webhook empty.** Atelier calls it synchronously with `?useWebhook=false`.
6. Copy the extractor agent id into `EVOLUS_EXTRACTOR_AGENT_ID` and the extractor id into `EVOLUS_EXTRACTOR_ID`.
   The connection-info panel shows the `ask-file` URL `…/agents/{agentId}/json/{extractorId}/ask-file`.

Atelier maps any key spelling (`unit_price`, `unitPrice`, "Unit price"), converts EUR, GBP, JPY, CNY and INR to USD
at an approximate rate (labelled on the quote), and rejects a document with no unit price (422). If the extractor
is not configured or fails, uploads fall back to the AMD LLM reading the PDF text, then to a local PDF text parser.
The quote card always says which engine ran.

## 6. Workflows

### A. "Atelier — send RFQ emails" and "Atelier — send purchase order" (built, verified live 2026-10-16)

Both workflows exist in the event workspace and are switched **on**. They are built (and rebuilt in place, ids
unchanged) by `backend/scripts/provision_evolus_workflows.py` through the Evolus MCP server:

```bash
cd backend
uv run python scripts/provision_evolus_workflows.py --dry-run     # lists the recipient addresses
uv run python scripts/provision_evolus_workflows.py               # updates the workflows named in backend/.env
uv run python scripts/check_evolus.py --workflows outreach,po --test-to <your own inbox>   # one test email each
```

| Workflow | .env | Used for |
|---|---|---|
| Atelier — send RFQ emails | `EVOLUS_OUTREACH_WORKFLOW_ID` | the RFQs, and the counter-offers (`EVOLUS_NEGOTIATION_WORKFLOW_ID` empty = this one) |
| Atelier — send purchase order | `EVOLUS_PO_WORKFLOW_ID` | purchase orders |

**Parameters.** Atelier sends them flat, and **every value is a string**: nested values are JSON strings, numbers
their text (`"300"`). Evolus rejects a number with HTTP 400 "The execution parameter 'production_quantity' must be a
string" (verified live), so `services/evolus._flatten` stringifies. Keys the workflow does not declare are accepted
and ignored. Declared on both: `rfq_emails` (required), `rfq_ref`, `kind`, `garment_name`, `production_quantity`,
`quote_number`, `currency`; on the RFQ workflow also `tech_pack`, `image_url`, `target_unit_price`; on the PO workflow
also `po_number`, `supplier_name`, `to_email`, `quantity`, `unit_price`, `total`.

| Parameter | Example |
|---|---|
| `rfq_emails` | `[{"supplierName","region","toEmail","subject","body","status","rfqRef","kind","language"}]` as a JSON string: the emails exactly as Atelier drafted them (in the mill's language), one per mill; one email for a counter-offer or a PO |
| `kind` | `rfq` (absent), `counter_offer`, `purchase_order` |
| `rfq_ref` | `ATL-run_ab12cd` |

**Steps** (same graph in both):

1. **Run a script** "Parse the drafted emails": `JSON.parse(params.rfq_emails)` → `[{toEmail, toKey (lower-case),
   subject, bodyHtml, supplierName, rfqRef, kind}]`. The body becomes HTML (escaped, line breaks kept). No address →
   the run fails.
2. **Repeat for each item** over that array (sequential, `continueOnItemError: true`). Body:
   - **Routing** (Switch, guided on `toKey`): one case per recipient address.
   - **Send an email**, one per address, on that case's branch: recipients = the address, subject
     `{{step:<switch>.subject}}`, body `{{step:<switch>.bodyHtml}}`.
   - default branch: **Run a script** "Not a recipient of this workflow" (nothing is sent).
3. **Run a script** "Summarise what was sent" (reads step 1 and the loop).
4. **Automation output**.

**Why one email step per address.** The "Send an email" step sends **from the Evolus mailbox** (Evolus's own
sender, via Microsoft Graph). No mailbox has to be connected. Its recipients field is **literal**, as the step
documentation says: `{{step:…}}`, `{{output}}` and `{{param:to_email}}` were all tried live, and each one fails with
"Call to 'microsoft-graph' failed in SendCoreAsync". Subject and body placeholders do resolve. So the workflow
routes each drafted email by its address. The addresses are the brand's supplier directory, each supplier's RFQ
override address if set, else its contact email (`data/suppliers.inbox_for`), plus any `--recipient`. **Re-run the
provisioning script after adding a supplier or changing an RFQ override.** Otherwise an email to a new address is
not sent, and the run says so.

**Output** (the run's `output`, a JSON string):

```json
{"emailStatus": "sent", "sentCount": 2, "failedCount": 0, "notSentCount": 0, "rfqRef": "ATL-run_ab12cd",
 "kind": "rfq", "emails": [{"toEmail": "…", "supplierName": "…", "subject": "…",
 "result": "handed to the Evolus mailer", "error": null}]}
```

- `emailStatus: "sent"`: every email went to the Evolus mailer. Atelier marks the RFQs, counter-offer or PO `sent`.
- `"partial"`: at least one went out, but another failed or has no email step. Atelier shows `queued`, never
  `sent`.
- None sent: the run **fails** with the reasons, and Atelier shows the error and keeps the drafts.

"Sent" means that the Evolus mailer accepted the email (its step output reads "Email sent to 1 recipient(s): …").
Delivery to the inbox is not reported back.

**Verified live (2026-10-16):**

- `check_evolus.py --workflows outreach,po --test-to <owner inbox>`: both Completed in about 1.8 s with 1 poll.
  Atelier parsed both as `sent`.
- A counter-offer with the exact parameter set of `decisions.send_counter_offer` went through the RFQ workflow as
  `sent`.
- A mixed run, with one known and one unknown address, gave `partial`: the unknown one was not sent and Atelier showed
  `queued`.

### B. "Atelier · Inbound supplier quote" (email → extractor → Atelier)

1. **Trigger: When an email arrives.**
   - Provider IMAP: host `imap.gmail.com`, port 993, SSL on.
   - Username: the inbox replies arrive in (the brand's sourcing inbox). Password: the Gmail **app password**.
   - Folder `INBOX`. Polling every 30–60 s. Mark as read: on.
   - Click **Test email connection**.
2. **Call a data extractor**: "Supplier quote", fed with the **email attachment**. Set the workflow's file mode to
   run once per file.
3. **Call an endpoint (API)**:
   - `POST https://<tunnel>/api/webhooks/evolus/quote`, content type JSON.
   - **Header** `X-Atelier-Webhook-Secret: <EVOLUS_WEBHOOK_SECRET>`. Or define the outbound **Webhook** once
     (Settings → Webhooks, header name and value) and pick it here. The provisioning script creates it.
   - **Body**: the extractor's output, plus the email's sender and subject if the step lets you add fields:

     ```json
     {"from": "{{email.from}}", "subject": "{{email.subject}}", "filename": "{{file.name}}",
      "extraction": {{extractor.output}}}
     ```

     Atelier accepts any JSON shape:
     - The extracted fields can sit under `extraction`, `fields`, `data` or `output`, or at the top level, and may
       be a JSON string.
     - The run is found from the `ATL-run_…` reference anywhere in the payload (subject, `rfq_reference`, body).
       Otherwise it is the newest run still waiting for that mill.
     - The mill is matched by name, or by the `+tag` in the sender address.

Turn the workflow on and put its id in `EVOLUS_INBOUND_WORKFLOW_ID`; only `check_evolus.py` uses that id.

How to test it: reply to an RFQ with a real quote document (a mill's PDF quote) attached. Within a polling interval
the quote appears on the dashboard, marked "email · Evolus document extractor".

**Security.**

- The webhook rejects requests without the secret (401).
- Without `EVOLUS_WEBHOOK_SECRET` configured it is disabled (503).
- A caller that can sign may send `X-Atelier-Signature: sha256=<HMAC-SHA256(secret, raw body)>` instead.
- Evolus webhook steps send a static header, not a signature, so the shared secret is the right fit.

### C. "Atelier · Shopify pre-order" (optional)

Optional: without it Atelier creates the real Shopify product itself through the Admin API
([SHOPIFY_SETUP.md](SHOPIFY_SETUP.md)). With it, the listing is an Evolus building block too.

**Parameters:** `title` (text), `description` (text), `price` (number), `image_url` (text), `handle` (text),
`production_quantity` (number).

**Steps** (suggested):

1. **Agent: "Merchandiser"**, on your AMD model, with a **Shopify MCP connector**. Its job is to create a
   product in a Shopify **development store**: the given title, description and price, the image from
   `image_url`, and the tags `pre-order` and `atelier`. Status should be `active` or `draft`, whichever you
   want to show.
   - Shopify side: follow [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md) (dev store, Dev Dashboard app, token).
   - **Unverified:** whether your workspace lets you attach external MCP servers to an agent. The track lists
     "MCP connectors" as a building block, but the public docs don't explain how to add one. Shopify has **no
     official Admin API MCP server**: Storefront MCP is buyer-facing (catalog and cart) and can't create products,
     and Dev MCP only looks up docs. So use an HTTP step that calls the Admin GraphQL `productCreate`, or a
     community MCP server.
   - If this workflow isn't configured or returns no product id, Atelier creates the product directly through the
     Admin API. Either way the pre-order is real (CONTRACT.md v3).
2. **Final output.** Return the created product, for example:

   ```json
   {"product": {"id": "gid://shopify/Product/1234567890", "handle": "verso-jacket",
                "onlineStoreUrl": "https://your-dev-store.myshopify.com/products/verso-jacket"}}
   ```

   Atelier searches the whole status body, including JSON-encoded strings, for these keys:
   - product id: `productId`, `admin_graphql_api_id`, or `product.id`
   - URL: `onlineStoreUrl` or `url`
   - handle: `handle`

   If it finds no Shopify product id, Atelier creates the product directly through the Admin API instead.

Turn it on and put its id in `EVOLUS_SHOPIFY_WORKFLOW_ID`.

## 7. backend/.env

```bash
# AMD (see AMD_SETUP.md)
AMD_VLLM_ENDPOINT=http://<droplet-ip>:8000/v1
AMD_VLLM_API_KEY=<VLLM_API_KEY>
AMD_VISION_ENDPOINT=http://<droplet-ip>:8000/v1   # same Gemma 4 server: one model for text, vision and Evolus
AMD_GPU_LABEL=AMD Instinct MI300X
ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}

# Evolus: auth
EVOLUS_API_BASE=https://api.evolus.ai
EVOLUS_API_KEY=<application API key>            # X-ApiKey (REST) and Bearer (/v1 chat)
EVOLUS_WORKSPACE_ID=<Space ID>                  # X-Application-Id
EVOLUS_USER_API_KEY=                            # optional personal key, if library calls get 401
EVOLUS_OWN_MODEL_NAME=gemma-4-26B-A4B-it        # name of the AMD model on the Models page (provisioning)

# Evolus: building blocks
EVOLUS_AGENT_MODEL=<spaceId>:<agentId>          # the brain
EVOLUS_AGENT_LABEL=gemma-4-26B-A4B-it on MI300X # shown in logs: "Evolus agent … → AMD vLLM (<label>)"
EVOLUS_LIBRARY_ID=<library id>
EVOLUS_EXTRACTOR_AGENT_ID=<extractor agent id>
EVOLUS_EXTRACTOR_ID=<extractor id>
EVOLUS_OUTREACH_WORKFLOW_ID=<workflow A id>
EVOLUS_NEGOTIATION_WORKFLOW_ID=                 # v4, optional: counter-offers; empty = workflow A
EVOLUS_PO_WORKFLOW_ID=                          # v5, optional: purchase orders; empty = workflow A
EVOLUS_INBOUND_WORKFLOW_ID=<workflow B id>
EVOLUS_SHOPIFY_WORKFLOW_ID=<workflow C id>      # optional
EVOLUS_WEBHOOK_SECRET=<long random string>      # openssl rand -hex 24; same value as the workflow's header
EVOLUS_RFQ_AI_TOOL=false                        # true = also polish RFQs with the "email" AI Tool (credits)

# v5: supplier contacts and RFQ overrides live in the Brand workspace (not in .env)

PUBLIC_BASE_URL=https://<tunnel>                # so quote document links work from anywhere
```

A block is used when its ids are set. What happens without it:

- no agent: the brain is direct vLLM; with neither, brain steps stop with an error and a retry;
- no extractor: quote documents are read by the AMD LLM over the PDF text, else a local parser of the PDF text;
- no outreach workflow: the RFQs are drafted but not sent — the step errors with a retry (same for counter-offers);
- no PO workflow (and no outreach workflow): the PO stays "draft — not sent".

## 8. Verify

```bash
cd backend
uv run python scripts/check_evolus.py --no-execute     # auth, agents, brain, library (no runs, no credits)
uv run python scripts/check_evolus.py --ai-tool --atelier-url https://<tunnel>   # everything
```

Each block prints PASS, FAIL or SKIP:

| Check | What it does |
|---|---|
| `auth` | Authenticates against the REST API |
| `agents` | Confirms `EVOLUS_AGENT_MODEL` is listed |
| `brain` | The agent returns JSON through Atelier's adapter |
| `library` | Both documents are indexed |
| `extractor` | Reads the quote document you pass with `--quote-pdf` (skipped without one) |
| `ai-tool` | Runs the `email` AI Tool |
| `webhook` | 401 without the secret, 404 with it (no run waiting) |
| `outreach` / `shopify` | Run the workflows once with sandbox data |

Then run the app and approve a design:

- The tech pack step is tagged **Evolus agent → AMD vLLM**.
- The tech pack shows the library passages it followed.
- The Inference panel lists each call with its route.
- The quotes step waits for documents. Drop the mills' PDF quotes onto the Quotes panel, or have them emailed.

**Plumbing rehearsal without any keys (test doubles — the app labels them "FAKE UPSTREAM — not real"):**

```bash
uv run python tests/fake_upstreams.py --atelier-url http://localhost:8787 --webhook-secret s3cret
# backend/.env -> AMD_VLLM_ENDPOINT=http://127.0.0.1:18900/v1, AMD_VLLM_API_KEY=fake-vllm-key,
#   EVOLUS_API_BASE=http://127.0.0.1:18902, EVOLUS_API_KEY=test-key, EVOLUS_WORKSPACE_ID=app_test,
#   EVOLUS_AGENT_MODEL=app_test:agent_sourcing, EVOLUS_LIBRARY_ID=lib_1, EVOLUS_EXTRACTOR_AGENT_ID=agent_x,
#   EVOLUS_EXTRACTOR_ID=ext_quote, EVOLUS_OUTREACH_WORKFLOW_ID=wf_out, EVOLUS_WEBHOOK_SECRET=s3cret
curl -F file=@<a quote document>.pdf -F from=x+prato@example.com \
     http://127.0.0.1:18902/fake/inbound-email   # the fake "inbox": extractor -> Atelier webhook
```

## 9. Let Claude Code build on Evolus (MCP)

Evolus runs an MCP server for coding agents at `https://api.evolus.ai/mcp`. It is documented on evolus.ai/developers,
uses streamable HTTP, and offers tools for agents, workflows, extractors, libraries and more. Connect it to Claude
Code:

```bash
claude mcp add --transport http evolus https://api.evolus.ai/mcp \
  --header "X-ApiKey: $EVOLUS_API_KEY" --header "X-Application-Id: $EVOLUS_WORKSPACE_ID"
```

or add the equivalent `.mcp.json`:

```json
{"mcpServers":{"evolus":{"type":"http","url":"https://api.evolus.ai/mcp",
  "headers":{"X-ApiKey":"${EVOLUS_API_KEY}","X-Application-Id":"${EVOLUS_WORKSPACE_ID}"}}}}
```

The key needs MCP access (full access works). The tool list is not public; run `/mcp` in Claude Code to see it.
With it, Claude can create the library, agent, extractor and workflows directly, which is the same job as
`provision_evolus.py`, but including workflows. **Don't commit the key.** Keep `.mcp.json` out of git, or use env
expansion as above.

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| Model **Test connection**: tool call fails | vLLM must run with `--enable-auto-tool-choice --tool-call-parser gemma4` (Gemma 4). `scripts/check_amd.py` reproduces the round trip and says what came back. |
| Agent answers contain `<\|channel>thought` text | A reasoning block leaked into the content (vLLM issue #39043). Keep `--reasoning-parser gemma4`; Atelier's JSON parsing strips these blocks either way. |
| Step tag says **Direct vLLM** | The agent call failed; the step log shows why (⚠ line). Check `EVOLUS_AGENT_MODEL` format `<spaceId>:<agentId>`. |
| Step shows **brain** error + Retry | Neither the agent nor vLLM answered with valid JSON. Check AMD_SETUP first, then press Retry. |
| `401` on chat but REST works | The `/v1` endpoint uses `Authorization: Bearer <key>`; make sure the key is an application key. |
| `401` on library calls | Set `EVOLUS_USER_API_KEY` (personal key). |
| Extractor returns no unit price | Check the field names (section 5) and that OCR is on. The upload falls back to the AMD LLM and says so on the card. |
| Email quote never arrives | Test the workflow's mailbox connection; check the tunnel URL and the secret header. Atelier logs `rejected quote webhook` on a bad secret. |
| Webhook `404` | No run is waiting for quotes (or the reference names an old run). |
| `402` | Out of platform credits. The extractor, OCR, libraries and AI Tools use credits; your own model doesn't. |
| `429` | Over 60 requests/min. The adapter backs off while polling; health probes are cached for 30 s. |
| Quotes step never ends | It waits for every mill. Use **Stop waiting & recommend** in the Quotes panel, or set `ATELIER_QUOTE_WAIT_SECONDS`. |
| `401` "API key rejected" | Wrong `EVOLUS_API_KEY`, or a missing/wrong `EVOLUS_WORKSPACE_ID` (sent as `X-Application-Id`). |
| `409` "switched off" | Turn the workflow on. |
| `400`/`422` on execute | Evolus rejected the parameters. Atelier retries once with `input` only; declare the parameters above to get structured inputs. |
| Run stays `Running` | Atelier stops waiting after `EVOLUS_POLL_TIMEOUT` (60s). The step completes with RFQs `queued`, and the run carries on inside Evolus. |
| `404` on execute/status | Wrong workflow id, or the paths differ. Set `EVOLUS_EXECUTE_PATH` / `EVOLUS_STATUS_PATH`; both are templates with `{workflow_id}` and `{execution_id}`. |
| Probe fails but runs work | The `GET /api/v1/ai-tools` probe path may need different access. Set `EVOLUS_PROBE_PATH` to any cheap authenticated GET. |

An outreach failure stops the step with the error, the setup hint and a Retry (the drafted RFQs are kept and re-sent
on retry). A Shopify workflow failure falls through to Atelier's direct Admin API call. Without a Shopify store the
step says "Shopify not connected" (see [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md)).
