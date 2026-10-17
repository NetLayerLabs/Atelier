# Atelier

An AI agent for fashion brands: it reads a trend from a mood board, takes the designer's own sketch (or generates garment concepts), lets a human creative director pick and steer one, then writes the tech pack, drafts supplier RFQs and opens a **real Shopify pre-order**. Production only unlocks once **real pre-orders** clear the threshold.

Built for the AMD Developer Hackathon: ACT III (Evolus Business Agents track and the "Reinvent Commerce" track).

**Live:** https://atelier.netlayerlabs.com. Visitors can try every step up to Approve (read a mood board or a sketch
with Gemma 4, customer voice, creative direction); approving a design emails real suppliers and creates a real
Shopify product, so that and everything after it need the admin token. Pilot brand: **UGO SARTORIA**, Igbo
menswear with Italian tailoring, in EUR; its mood boards are AI-generated inspiration and labelled so.

**As deployed for the hackathon:** one open model, **Gemma 4** (`Gemma-4-31B-IT`, Google), on AMD GPUs through
**AMD Token Factory**. It reads the mood boards and the designer's sketches (vision) and is the model behind the
Evolus agent (registered in the Evolus event workspace as our own model). Evolus building blocks used through the
API: the agent, a knowledge library holding the brand book, a document extractor for supplier quotes, and two email
workflows (RFQs, purchase orders). The UI only names the model and GPU a connected endpoint actually reports in
`/api/health` — it never claims hardware it can't verify.

**Diffusion concepts are optional.** Concept renders need a diffusion server on our own AMD GPU (`deploy/`: vLLM
for Gemma 4 and FLUX.1-schnell on an AMD Instinct MI300X, AMD Developer Cloud). Without one, the "Generate four
concepts" and "Compose a collection" buttons are not offered: the designer uploads their own sketch or photo, Gemma 4
reads it (collar, closure, pockets, details), and that reading goes into the tech pack.

**It runs on a real brand's data.** Nothing brand-specific is built in: the brand profile, brand book, supplier
directory, material price list, guardrails and (optionally) past sales are imported in the **Brand workspace**
(header → *Brand workspace*, or `/workspace`), stored in SQLite under `ATELIER_DATA_DIR` (default `backend/var/`,
git-ignored; a Docker volume in compose) and shown with their provenance ("Imported from suppliers.csv on …"). The
studio can't approve a design until the workspace has a brand profile, at least one supplier whose contacts the brand
confirmed, and reviewed guardrails — approving emails real suppliers (or the per-supplier *RFQ override* inbox the
brand sets for a pilot). What to ask a pilot brand for: [docs/PILOT_DATA.md](docs/PILOT_DATA.md). API:
[CONTRACT.md "v5"](CONTRACT.md).

## Run it

```bash
./dev.sh
```

Opens the dashboard at http://localhost:3100 and the API at http://localhost:8787 (docs at `/docs`).
Requires `uv` and `pnpm`. Ports can be changed with `BACKEND_PORT` / `FRONTEND_PORT`.

**Nothing is mocked.** Every trend read, sketch reading, concept, tech pack, RFQ, quote, order and purchase order
comes from a real service: the AMD-hosted model (and a diffusion server when one is connected), the Evolus agent
and workflows, and a Shopify store. A service
that isn't configured shows **not connected** in the header with the variable to set; the features that need it show
an honest error with a retry, never made-up output. With no `.env` at all the app runs and tells you what to connect.
**Inference** in the header opens per-call stats (model, GPU, tokens/sec, latency) once real calls have happened.

**Demo mode** (Shift+D, **Tour** in the header, or `/?demo=1`) is a guided tour of the real UI against the real
services. Where a beat needs a person — a supplier's quote document, a pre-order — it pauses with a prompt and
continues when the real data arrives. It never sends anything itself: before Approve (which emails the brand's
suppliers) and before a counter-offer it names every address the email goes to and waits for you to press the
button. The stage script, pre-show checklist and the recommended fallback (a
pre-recorded video of a live run) are in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

**Supplier quotes are real documents.** After the RFQs go out to the brand's own suppliers (through the Evolus
outreach workflow), the quotes step waits ("Awaiting replies — 1 of 3 received") until their quotes arrive: dropped
onto the Quotes panel, or by email through an Evolus inbound workflow. The Evolus document extractor reads them; if
it isn't configured, the AMD model or a local parser reads the PDF text, and each quote says which one ran. A field
the document doesn't state is shown as **not stated** — never assumed. Quotes in another currency are converted
with the ECB's daily reference rates; if those can't be loaded, the quote stays in its own currency and says so.

**The agent knows when to hand the case to a person.** The brand's own guardrails (set in the Brand workspace: a
gross-margin floor, a unit-cost cap, maximum lead time and MOQ, required certificates — unset rules aren't checked)
are checked against every quote, deterministically. When the agent's pick breaks one — or a quote doesn't state
what a guardrail needs — the run stops before Shopify and explains, with the numbers. You approve (recorded as an
override), switch supplier, or negotiate: the brain drafts a counter-offer at a computed target price in the
supplier's own language with the English alongside, sent through Evolus. The revised quote is re-checked when it
lands. Everything goes into an audit trail.

**Pre-orders are real.** After approval, Atelier creates the product in a Shopify store and the demand panel shows
a QR code so the audience can pre-order with a test card. It counts those real orders (test orders are labelled as
such). Without a store, the Shopify step says **"Shopify not connected"**. For a demo, the PO can unlock at a small,
clearly labelled stage threshold (`DEMAND_STAGE_THRESHOLD=5`) instead of the full production run.

**The purchase order is real.** When the threshold is crossed, Atelier drafts a PO with the next number of the
brand's persisted sequence (PO-00001, …) and sends it to the selected mill's address through an Evolus workflow
(`EVOLUS_PO_WORKFLOW_ID`, else the outreach workflow). Without Evolus it stays **draft — not sent**, with a send
button.

**"How many should we make?"** Every real order feeds an explained production forecast (Bayesian launch curve +
newsvendor, no language model). Its assumptions are labelled model parameters you can edit — fit them to your own
past launches.

To go live:
- [docs/AMD_SETUP.md](docs/AMD_SETUP.md): AMD Token Factory (the hackathon setup: `AMD_VISION_ENDPOINT` +
  `AMD_TOKEN_FACTORY_KEY`), or your own vLLM for Gemma 4 (text + vision, one server) plus FLUX diffusion on AMD
  Developer Cloud. The scripts are in [deploy/](deploy/).
- [docs/EVOLUS_SETUP.md](docs/EVOLUS_SETUP.md): the Evolus workspace.
  - **The brain** is an Evolus agent running on our AMD-hosted model (Gemma 4, connected as the workspace model), grounded in a knowledge library: the brand book
    the brand uploads in the Brand workspace, plus a supplier catalogue and brand profile generated from it.
  - **Quotes** are read by a document extractor.
  - **Workflows** handle outreach, inbound email and (optionally) the Shopify listing.
  - API reference with sources: [docs/EVOLUS_API_NOTES.md](docs/EVOLUS_API_NOTES.md).
- [docs/SHOPIFY_SETUP.md](docs/SHOPIFY_SETUP.md): free dev store, Dev Dashboard app, test payments, real pre-orders.

Verify with `backend/scripts/check_amd.py`, `check_evolus.py` and `check_shopify.py`. To rehearse the plumbing
without credentials, `backend/tests/fake_upstreams.py` starts **test doubles** of every upstream; they mark their
responses, so the header shows them in red as "FAKE UPSTREAM — not real" and never shows the credits. More details
in [backend/README.md](backend/README.md).

**Mood boards are real photos, read live.** The five preset boards are openly licensed photographs: New York
Fashion Week Fall/Winter 2010 runway shots by Masaki-H (CC BY 2.0, via Wikimedia Commons) and 19th-century
coats and jackets from The Met's Open Access collection (CC0). Picking a board sends its photos to the vision
model on AMD, the same path as an upload. Nothing about a board is pre-written. The analysis says which model and
host produced it. Without a vision endpoint, the trend step says **"Vision model not connected"** instead of
inventing a trend.
- **Image licences.** Every image's author, source page, licence and modifications (downscaled, re-encoded) are
  listed in [backend/static/moodboards/ATTRIBUTION.md](backend/static/moodboards/ATTRIBUTION.md) and
  `manifest.json`, and shown under **Image credits** in the picker. CC BY 2.0 requires that credit to stay with
  the photos if you redistribute them. Garments and logos in the photos belong to their owners.
- To rebuild or change the boards: `backend/scripts/build_moodboards.py` (it checks each licence at the source).

## Run with Docker

```bash
docker compose up --build
```

Same URLs: dashboard at http://localhost:3100, API at http://localhost:8787. With no `.env` it starts and shows
every service as "not connected". If `backend/.env` exists (copy `backend/.env.example`), the backend loads it. Inside the container, an
SSH tunnel on the host is `host.docker.internal`, e.g. `AMD_VLLM_ENDPOINT=http://host.docker.internal:18000/v1`.

To use other host ports: `BACKEND_PORT=8890 FRONTEND_PORT=3190 docker compose up --build`.

**Access.** Both ports are published on `127.0.0.1` only, and without `ATELIER_ADMIN_TOKEN` the API accepts changes
from this machine only (`GET /api/health` says so under `security`). Changes must also come from the dashboard's own
origin (`CORS_ORIGINS`): a cross-site form post is refused. To host Atelier for others, set `ATELIER_ADMIN_TOKEN` in
`backend/.env` (the dashboard then shows a sign-in form; scripts send `Authorization: Bearer <token>`), point
`PUBLIC_BASE_URL` / `CORS_ORIGINS` at the public URLs, and publish on all interfaces with
`BACKEND_BIND=0.0.0.0 FRONTEND_BIND=0.0.0.0`. Behind a reverse proxy or tunnel, always set the token. Supplier
quote documents and brand files are private (served only to signed-in / local clients); webhooks stay open to their
senders and are verified by signature / shared secret. Details: [CONTRACT.md "Access, uploads and quote
integrity"](CONTRACT.md).
Next.js inlines `NEXT_PUBLIC_API_BASE` into the browser bundle at build time, so compose passes it as a build
arg (`http://localhost:$BACKEND_PORT`). The backend URL is fixed per build: change it, then rebuild.

## Submission

- Containerized: `backend/Dockerfile` (FastAPI on Python 3.12, uv-locked deps, non-root, healthcheck) and
  `frontend/Dockerfile` (Next.js standalone build, non-root). `docker-compose.yml` wires them together and
  starts the dashboard once the API is healthy.
- To run it: clone the repo, run `docker compose up --build`, open http://localhost:3100. The header shows which
  services are connected; set up the Brand workspace (`/workspace`) and configure `backend/.env` (AMD endpoints,
  Evolus, Shopify) to run the flow end to end. The image includes the preset mood boards (`backend/static/moodboards`);
  the brand's data and PO / style numbers persist on the `atelier-data` volume.
- No keys are committed. Configuration lives in git-ignored `.env` files; only the `*.example` templates are in the repo.

## Layout

- [backend/](backend/) — FastAPI orchestrator: vision, LLM, diffusion, Evolus and Shopify adapters (real services only)
- [frontend/](frontend/) — Next.js Creative Director Dashboard
- [CONTRACT.md](CONTRACT.md) — the API contract between them
- [PROJECT_SPEC.md](PROJECT_SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md) — original plan

## Tests

```bash
(cd backend && uv run pytest -q)
(cd frontend && pnpm lint && pnpm build)
```
