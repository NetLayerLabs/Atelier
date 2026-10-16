# Pilot data checklist

Atelier runs on the pilot brand's own data. Nothing brand-specific is built in: until the brand provides it, the
corresponding feature is empty (no swaps without a price list, no guardrail without a limit, no RFQ without a
confirmed supplier). This page is what to ask the brand for, in which format, and how it is used and stored.

Everything is imported in **Brand workspace** (header → *Brand workspace*, `/workspace`). Each table import shows a
preview with row-level validation before anything is stored. CSV templates (header row only) are downloadable on
each step and from `GET /api/workspace/templates/{suppliers|prices|sizes|sales}.csv`.

## What to request

### Required before the studio can approve a design

| # | Item | Format | Fields | Notes |
|---|---|---|---|---|
| 1 | **Brand profile** | entered in the form (5 min with the brand) | name, currency (ISO, e.g. EUR), target markets, persona / tone-of-voice notes, default size range, colour standards (name + hex; Pantone/TCX code **only if the brand book gives one**), price architecture (retail multiple of landed cost *or* target gross margin %), delivery promise (weeks from launch), pre-order window (days) | Only name and currency are required. Everything else may stay empty. |
| 2 | **Supplier directory** | CSV or XLSX (template: `suppliers`) | `name`, `city`, `country`, `language` (ISO code), `contact_emails` (`;`-separated), `categories` (`;`; use **CMT** for cut-make-trim / full-package factories), `capabilities`, `certifications`, `certificate_expiry` (`GOTS=2027-06-30; …`), `moq`, `lead_time_weeks`, `payment_terms`, `notes`, `rfq_email_override` | At least one supplier. **These are real contacts** — see *Consent* below. |
| 3 | **Guardrails** | entered in the form | gross-margin floor %, max unit cost (brand currency) or headroom over the tech-pack costing, max lead time (weeks), max MOQ (pieces / colour), required certifications (all / any) | There are no defaults. The brand may leave any rule empty (it is then not checked) but must review the page once. |

### Strongly recommended

| # | Item | Format | Fields | Used for |
|---|---|---|---|---|
| 4 | **Brand book** and related guides (fabric standards, sustainability policy, tone of voice, fit guide) | PDF, DOCX or Markdown, ≤ 25 MB each | — | Grounding with citations for tech packs, RFQs, creative direction and the supplier rationale; uploaded to the Evolus knowledge library when one is connected. Scanned PDFs without a text layer give no passages — ask for the source file or a text PDF. |
| 5 | **Material price list** | CSV or XLSX (template: `prices`) | `material`, `category`, `unit` (m / kg / pc …), `price`, `currency`, `supplier`, `valid_from` (YYYY-MM-DD) | Material swaps in the tech pack editor, costed against the line's current material within the same category, currency and unit. Shown as "price list dated …". |
| 6 | **Size blocks / points of measure** | CSV or XLSX (template: `sizes`) | `block`, `point_of_measure`, `size`, `value`, `unit` (cm / in), `tolerance` | Named in the tech pack brief and the knowledge passages. |
| 7 | **Supplier certificates** | PDF or image per certificate | attach on the supplier's edit form | Stored with the supplier; the expiry date decides whether the certificate counts for a guardrail. |

### Optional

| # | Item | Format | Fields | Used for |
|---|---|---|---|---|
| 8 | **Past sales history** | CSV or XLSX (template: `sales`) — export from Shopify / ERP, one row per style × week since launch × size | `style`, `launch_date`, `week` (1 = launch week), `units`, `size` (optional) | Stored for the production forecast's priors: `workspace.launch_curves()` (launch-curve shape and lifetime totals per style) and `workspace.size_mix()` (size split). The forecast does not use them yet. |
| 9 | **Customer reviews / returns / tickets export** | CSV, TSV or PDF | review text, rating, product, date (no names or emails needed) | Customer-voice analysis (uploaded on the studio's customer-voice panel; not stored in the workspace). |
| 10 | **Shopify access** | a development store (or a staff account with a custom app) | Admin API token or Dev Dashboard client id + secret; webhook secret | Real pre-orders and order counts (docs/SHOPIFY_SETUP.md). |

## Consent and privacy

- **Supplier contacts are real people.** Before the studio can approve a design the brand must tick *"I confirm
  these are the right contacts and that the brand may email them (or the override inbox) with RFQs and
  counter-offers"*. Re-importing the directory, or changing a supplier's name, emails or override, asks for the
  confirmation again. The brand should tell its suppliers that RFQs drafted by an AI agent may arrive under its name.
- **Pilot routing.** For a first pilot, set each supplier's **RFQ email override** (or *Apply to all*) to the brand's
  own sourcing inbox: Atelier then emails only the brand, which forwards what it wants. Recipients always come from
  the directory, never from model output.
- **Third parties.** RFQs and counter-offers are sent through the brand's Evolus workflow; brand-book files and the
  generated supplier catalogue are uploaded to the Evolus knowledge library when one is configured (the catalogue
  contains no contact addresses). Prompts sent to the model contain the brand name, voice notes, profile facts and
  retrieved passages — not supplier email addresses.
- **Customer data.** Ask for review / ticket exports **without** customer names, emails or order numbers. Sales
  history needs units only — no customer data. Shopify orders are read for counts and sizes; Atelier does not store
  customer details.
- **Shopify access.** Use a development store or a custom app with the narrowest scopes in docs/SHOPIFY_SETUP.md;
  the brand can revoke the token at any time.
- Get written agreement (email is enough) from the brand that Atelier may store the files above for the pilot, and
  agree a deletion date.

## How it is stored

- One brand per backend: a SQLite file `atelier.sqlite3` plus the uploaded files (brand book, certificates) in
  `ATELIER_DATA_DIR` (default `backend/var/`, git-ignored; in Docker the `atelier-data` volume at `/data`). Never
  committed to git.
- Every import records its provenance ("Imported from suppliers.csv on 13 Oct 2026 (12 rows)"), shown in the UI.
- **Deleting:** `DELETE /api/workspace?confirm=DELETE` erases the workspace (database rows and uploaded files);
  `docker compose down -v` removes the volume. Copies already uploaded to the Evolus library or sent by email are
  removed there.

## Quick validation checklist (before the first approval)

- [ ] Profile: name + currency; promise and pre-order window if the brand has them.
- [ ] Suppliers: every row valid in the preview; at least one **CMT** maker if makers are separate from mills;
      certificate expiry dates filled in for the certifications the guardrails require.
- [ ] Contacts confirmed; RFQ overrides set if this is a routed pilot.
- [ ] Guardrails reviewed (the page lists the rules left unset).
- [ ] Brand book uploaded and showing passages (not "0 passages").
- [ ] Price list dated within the season; currencies match the brand's.
