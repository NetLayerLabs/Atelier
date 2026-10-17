# Atelier

**Make only what's already sold.** Atelier is an AI agent for independent fashion brands. Gemma 4 on AMD reads the
trend from a mood board and the designer's own sketch, and a human creative director makes every taste call. Then the
agents do the paperwork: a costed tech pack; RFQs to the brand's mills, each in the mill's language; supplier quotes
read into data and checked against the brand's own rules, with the agent stopping for a person when a quote breaks
one; a real Shopify pre-order; and the purchase order, sent to the mill only once real pre-orders clear the threshold.

Built for the AMD Developer Hackathon: ACT III. Main track **Reinvent Commerce**, partner track **Evolus: Business
Agents on AMD**, and also eligible for the **Vibe Generation** prize.

**Live:** https://atelier.netlayerlabs.com. Without signing in, anyone can read a mood board, upload a sketch and have
it read, direct it in plain words, and run customer voice on three public review samples. Approving a design starts
the run that emails the brand's suppliers and opens a Shopify pre-order, so approving and every step after it need
the admin token (as does applying customer-voice changes to a design). The steps after Approve are shown in
[the 17 October run](#what-works-end-to-end-today).

**In short**

- **The problem, and why now.** The fashion industry produced an estimated 2.5–5 billion items of excess stock in
  2023 ([McKinsey & BoF](https://www.mckinsey.com/~/media/mckinsey/industries/retail/our%20insights/state%20of%20fashion/2025/the-state-of-fashion-2025-v2.pdf)),
  and since 19 July 2026 large companies in the EU may no longer destroy unsold apparel, clothing accessories or
  footwear ([Regulation (EU) 2024/1781](https://eur-lex.europa.eu/eli/reg/2024/1781/oj/eng)). Micro and small
  companies, Atelier's first users among them, are exempt, so the ban is a tailwind and a sign of where EU rules are
  heading, not their legal duty.
- **The thesis.** Make only what's already sold: an approved design goes on sale as a pre-order before anything is
  made, and the purchase order goes to the mill only once real orders cover the production run.
- **What works.** The whole loop, on live services. On 17 October 2026 one run went from a mood board to purchase
  order PO-00001 on AMD Token Factory (Gemma 4), Evolus and Shopify; approval to both RFQs sent took 1 min 54 s. No
  real drop has happened yet: the suppliers were demo entries routed to our own inbox, the quotes were documents we
  wrote, and the only order was a 5-unit test-payment order we placed (a Shopify development store accepts only test
  payments). A demo setting, `DEMAND_STAGE_THRESHOLD=5`, let that order unlock the 60-unit purchase order; without
  it, the purchase order waits until pre-orders cover the whole run. The run shows the mechanism, not a funded
  production run.
- **The business model (planned).** A subscription per brand, plus a fee per drop or per purchase order. Not yet
  tested with a paying brand.

**Pilot brand: UGO SARTORIA**: Igbo menswear with Italian tailoring, priced in EUR with a 6-week delivery promise.
It has not run a real drop yet, and its two suppliers are demo entries routed to our own inbox. Its profile, brand
book, two suppliers and guardrails are in the Brand workspace; its mood boards and brand-book images are AI-generated
inspiration, labelled as such. No material price list or sales history is loaded yet, so tech-pack costs are the
model's estimates.

## Contents

1. [The problem](#the-problem)
2. [The thesis: make only what's already sold](#the-thesis-make-only-whats-already-sold)
3. [What works end to end today](#what-works-end-to-end-today)
4. [Business model](#business-model)
5. [How it works](#how-it-works)
6. [Latest development (16–17 Oct 2026)](#latest-development-1617-oct-2026)
7. For developers: [Run it](#run-it) · [Run with Docker](#run-with-docker) · [Submission](#submission) ·
   [Layout](#layout) · [Tests](#tests)

## The problem

Fashion commits to production months before it knows what will sell, and the surplus has to go somewhere.

| | What the source says | Source |
|---|---|---|
| **Surplus** | An estimated 2.5–5 billion items of excess stock were produced by the fashion industry in 2023, worth USD 70–140 billion in sales. | McKinsey & Company and BoF, *The State of Fashion 2025*, November 2024, pp. 15 and 114 ([PDF](https://www.mckinsey.com/~/media/mckinsey/industries/retail/our%20insights/state%20of%20fashion/2025/the-state-of-fashion-2025-v2.pdf)) |
| **Destruction** | An estimated 4–9% of all textile products put on the market in Europe are destroyed before use: 264,000 to 594,000 tonnes in 2020. That destruction causes up to 5.6 million tonnes of CO2-equivalent emissions, slightly less than Sweden's net emissions in 2021. | European Environment Agency, briefing no. 01/2024, 4 March 2024 ([EEA](https://www.eea.europa.eu/en/analysis/publications/the-destruction-of-returned-and-unsold-textiles-in-europes-circular-economy)) |
| **Slow development** | In a 2018 survey of 54 apparel executives, design and development alone took 11 weeks on average at vertically integrated companies and 24 weeks at hybrid players (those selling both wholesale and direct to consumers). Concept to market took 28 and 44 weeks respectively. | McKinsey & Company, *Measuring the fashion world*, October 2018 ([McKinsey](https://www.mckinsey.com/industries/retail/our-insights/measuring-the-fashion-world)), as reported by [Retail Dive](https://www.retaildive.com/news/Apparel-lead-times-McKinsey-vertical-integration/540838/) on 29 October 2018 |

How to read them: the McKinsey surplus figure is a range estimate for one year, 2023, not a count, and "items" can
include footwear and accessories. The EEA says the overall size of destruction "remains uncertain" and "is likely to
be an underestimation"; its 5.6 million tonnes is an upper bound that counts fibre-production emissions only. The 2018
durations are survey averages, not a current benchmark.

### Why now: the EU ban on destroying unsold apparel and footwear

Since **19 July 2026**, large companies in the EU may no longer destroy unsold apparel, clothing accessories or
footwear ([Regulation (EU) 2024/1781](https://eur-lex.europa.eu/eli/reg/2024/1781/oj/eng), the Ecodesign for
Sustainable Products Regulation, Article 25 and Annex VII). The ban extends to medium-sized companies from 19 July
2030; micro and small companies are exempt.

- **What it covers.** "Unsold" includes surplus stock, excess inventory, deadstock and products returned by
  consumers under their right of withdrawal (or during a longer withdrawal period the trader offers). "Destruction"
  means intentionally damaging a product or discarding it as waste, unless it is handed over solely to be prepared
  for reuse.
- **Narrow exceptions**, for example dangerous, damaged or defective goods, IP infringement, or goods that were
  offered for donation and not taken, are set out in
  [Delegated Regulation (EU) 2026/296](http://data.europa.eu/eli/reg_del/2026/296/oj).
- **Disclosure.** Companies that discard unsold consumer products must publish each year the number and weight
  discarded by product type, the reasons, and how much went to reuse, recycling, other recovery or disposal (Article 24
  of the same Regulation). A standard disclosure format applies from 2 March 2027
  ([Implementing Regulation (EU) 2026/2](http://data.europa.eu/eli/reg_impl/2026/2/oj)). Medium-sized companies are
  covered from 19 July 2030; micro and small companies are exempt.

**Why it pushes brands toward selling first (our reading).** When surplus may not be destroyed, every unit made and
not sold has to be stored, sold off, donated or prepared for reuse, unless an exception applies, and large companies
have to report what they discard. The cheapest surplus unit is the one that was never made.

**Who it binds.** Atelier's first users, small direct-to-consumer brands, are exempt. We present the ban as a
tailwind and a sign of where EU rules are heading (binding on large companies now and on medium-sized ones from 2030),
not as a legal duty for small brands.

## The thesis: make only what's already sold

Fashion brands usually design, sample, order a full production run and then hope it sells. Atelier flips the last two
steps: an approved design goes on sale as a pre-order before anything is made, and the purchase order goes to the mill
only once real orders cover the production run. "Make only what's already sold" is a rule in the code, not only a line
on the landing page.

1. **An approved design is sold as a pre-order before anything is made.** After approval the agents write the tech
   pack and collect supplier quotes. Once a quote passes the brand's guardrails (or a person approves an exception),
   the product goes live on the brand's Shopify store as a pre-order, with size variants and a pre-order window (set
   by `SHOPIFY_DEMAND_WINDOW_HOURS`, 14 days by default; the brand profile's own window, 21 days for the pilot, is not
   applied to it yet). The listing says the piece goes into production only once enough pre-orders are in, and gives
   the brand's delivery promise (without one, the quoted lead time).
2. **The purchase order waits for real orders.** It is drafted only once pre-ordered units reach the production plan
   (or the chosen supplier's MOQ, if that is higher). If the window closes short of it, no purchase order is drafted
   and the orders stay open in Shopify for the brand to cancel or refund. For live demos, a small stage threshold
   (`DEMAND_STAGE_THRESHOLD`) can stand in for the plan and the MOQ as the unlock point (it is 5 on our demo
   deployments), and the screen shows both.
3. **Statistics, not a language model, answer "how many should we make?"** Pre-orders follow a Bass-diffusion launch
   curve (its shape is an assumption). Real orders update a Gamma prior on demand (Gamma–Poisson), predicted demand is
   negative binomial, and the quantity is the newsvendor optimum, never below the MOQ. The size split is smoothed
   toward a base size curve. There is no random sampling, every assumption is labelled and editable, and no
   recommendation is made until enough of the window has passed and enough orders are in. The forecast advises; the
   production plan, which the purchase order follows, is set by a person.
4. **People make the taste calls; agents do the paperwork.**

| A person decides | The agents do |
|---|---|
| Which trend and which design to take forward (or uploads their own sketch) | Read mood boards and sketches (Gemma 4 on AMD) |
| How to direct the design, in plain words | Write the costed tech pack, citing the brand's own documents |
| Whether to approve it, and the production plan | Send RFQs in each mill's language and read the quote documents into data |
| Every exception to the brand's rules: approve anyway (logged as an override), switch supplier, or negotiate | Check every quote against the rules by plain arithmetic, and draft the counter-offer at a computed price |
| What happens to the pre-orders when a window misses | Publish the pre-order, count real orders, send the purchase order |

Mills don't get the brand's economics: each RFQ is written from a supplier-safe view of the tech pack (materials,
measurements, quantity, required lead time) with no target cost, retail price or margin, and the agent is instructed
never to mention them (an instruction, not a filter on the sent text). A counter-offer states the computed target
unit price, and the agent is told never to reveal the margin floor behind it.

**Pre-ordering already works for some labels.**

- In 2020, the New York made-to-measure menswear label Stòffa earned over 90% of its revenue from made-to-order or
  made-to-measure pieces produced only after the customer had paid
  ([The Business of Fashion, "The 'Zero Inventory' Solution"](https://www.businessoffashion.com/articles/retail/zero-inventory-fashion-business/),
  September 2020; members-only). That is a 2020 figure, not a current one.
- The labels Prabal Gurung and Antonio Berardi attributed 20–25% of their revenue to pre-order and made-to-order sales
  ([Glossy](https://www.glossy.co/fashion/pre-order-is-catching-on-as-a-solution-to-fashions-overproduction-problem/),
  21 April 2021, citing Vogue Business). It is second-hand and dated, so indicative only.

**Caveats.**

- **MOQs still apply.** Without a stage threshold, the purchase-order threshold is never below the chosen mill's MOQ,
  and the purchase order itself is never for less than the MOQ. A style with 120 pre-orders against a 300-piece MOQ
  does not unlock: the brand negotiates a lower MOQ (mills may charge more per piece for that) or cancels and refunds
  the pre-orders in Shopify. With `DEMAND_STAGE_THRESHOLD` set (it is 5 in `backend/.env.example` and on our local and
  hosted demo deployments; 0 turns it off), the stage threshold replaces both the plan and the MOQ as the unlock point.
- **Selling before a physical sample.** Listing from a sketch or render before a physical sample exists carries
  consumer-protection risk. The safer framing is a deposit-backed pre-order or a waitlist that says "made to order,
  ships in N weeks". Today Atelier's listing says the piece is made only once enough pre-orders are in and gives the
  delivery promise, but the customer pays the full price at checkout; deposits and waitlists are not built.

## What works end to end today

On 17 October 2026 we ran the whole loop once against the live services, from a mood board to a purchase order. The
backend ran on a laptop and a rehearsal script drove each step through Atelier's own API; where the agent stopped for
a person, we made the call. The numbers below are measured on that run. The backend was the build from before the 17
October audit fixes (d853c4d, 839b541, 90071ce, 5dd33c1); for example, its Shopify listing said "Ships about 8 weeks
after the pre-order window closes" (the quoted 6 weeks plus a padded 2), where the current build states the brand's
own 6-week delivery promise.

**What ran.** Gemma 4 (`Gemma-4-31B-IT`, Google's open model) on AMD GPUs through **AMD Token Factory**. It did the
vision work (mood board, sketch) and is the model behind the Evolus agent (tech pack, RFQs, counter-offer,
customer-voice summary). **Evolus**: the agent, a knowledge library attached to it (brand book, brand profile,
supplier catalogue), the document extractor for quote PDFs, one email workflow for RFQs and counter-offers, and one
for purchase orders. The library is attached to the agent in the Evolus workspace; the chat transport this run used
returns no library citations, so nothing in the run shows whether the agent consulted it. **Shopify**: a development
store priced in EUR, reached through the Admin API. Not connected: a diffusion server (so no AI concept renders), a
direct vLLM backup, and the Evolus inbound-email and Shopify workflows.

| Step | What runs it | Result on 17 Oct 2026 | Time |
|---|---|---|---|
| Mood board → trend | Gemma 4 vision (AMD Token Factory) | Read the pilot's "Senator" board (four AI-generated inspiration images) as "Modern Afro-Minimalist Tailoring", with a five-colour palette | 20.9 s |
| Sketch → design brief | Gemma 4 vision | A flat demo sketch of a long-line senator tunic with written notes, read as: mandarin collar, half placket with 4 buttons, single chest patch pocket, 12 cm side slits, long sleeves, tonal embroidery (four of the six are written on the sketch). The sketch became the design; no image model was used | 75.4 s |
| Customer voice | Fixed rules count the themes; the Evolus agent writes the summary | 200 public reviews; the four most frequent of the 33 themes the rules found: comfortable, quality praised, true to size, runs large. The changes were applied to the design before approval | 59.8 s |
| Approve → tech pack | Evolus agent | 7 bill-of-materials lines, a proposed retail price of EUR 276.92, 3 citations to the brand's own documents, a downloadable PDF | 44.2 s model call |
| → RFQs sent | The Evolus agent drafts; an Evolus email workflow sends | One RFQ in Italian to the Italian fabric-mill entry, one in English to the maker in Nigeria | **114.4 s (1 min 54 s)** from pressing Approve |
| Quote → data | Evolus document extractor | Quote 1: EUR 320 per unit, MOQ 50, 6 weeks | – |
| Guardrail check | Plain arithmetic, no model | Quote 1 broke two rules: a −15.6% gross margin against a 60% floor, and a unit cost above the EUR 250 cap. The agent stopped before Shopify and handed the decision to a person, with the numbers | – |
| Negotiate | Atelier computes the price; the Evolus agent drafts; the Evolus workflow sends | Target EUR 276.92 × (1 − 60%) = EUR 110.768, rounded down to EUR 110.76 (65.4% below the quote). The cost cap was higher, so the margin floor set the target. Drafted in English, the supplier's language | 30.3 s to draft; sent 32.1 s after pressing Negotiate |
| Revised quotes | Quote upload and reading, then guardrails | Revision 1: EUR 180, inside the cost cap but only 35.0% gross margin, so the agent stopped and asked again. Revision 2: EUR 105.77 (61.8% margin, 6 weeks, MOQ 50) passed every rule; the Evolus document extractor read it at 100% confidence | – |
| Pre-order | Shopify Admin API | Live at EUR 276.92 in sizes S–XXL, with a 14-day pre-order window | about 25 s after the passing revision was uploaded |
| Orders → purchase order | Shopify order poll; Evolus purchase-order workflow | One test order of 5 units crossed the stage threshold of 5. PO-00001: 60 units × EUR 105.77 = EUR 6,346.20, with the 6-week lead time as quoted | – |

### Read the numbers with these conditions

- **No mill was emailed.** Both suppliers in the pilot's workspace are demo entries whose address is our own inbox.
  Every email in the run was really sent, but no mill received one.
- **We wrote the quotes.** They were PDFs headed "[Atelier TEST] Supplier quotation", with quote numbers starting
  TEST-, uploaded through the same endpoint the Quotes panel uses. The log shows the Evolus document extractor reading
  quote 1 and the final revision (the latter at 100% confidence); it doesn't record which engine read revision 1. The
  Italian mill entry never answered, so we closed the quote round with one supplier.
- **The order was a test.** We placed one order ourselves: 5 units in size S, EUR 1,384.60, through Shopify's test
  payment gateway. The app counts it and labels it a test order. `DEMAND_STAGE_THRESHOLD=5` let 5 pre-ordered units
  unlock the purchase order while the production plan stayed at 60 units. Without that setting, the threshold is the
  whole production plan (or the supplier's MOQ, if that is higher).
- **The costs are the model's.** The pilot has not loaded a material price list, so the model costed the 7
  bill-of-materials lines (EUR 94.00 a garment) and proposed EUR 276.92 retail: a 66.1% gross margin, against the
  brand's own 65% target margin. The code does not check the proposed price against that target. The 3 citations are
  passages Atelier retrieves from the brand's own documents (the brand profile's commercial rules and two brand-book
  pages), not citations returned by the Evolus library.
- **The reviews are not the pilot's.** They are 200 real, anonymised reviews from a public dataset (the "Knits &
  sweaters" sample of Women's E-Commerce Clothing Reviews, CC0, via Kaggle and OpenML). They review women's knitwear
  and the design is menswear, so this shows how the mechanism works, not evidence about this garment.
- **The guardrails are the pilot's own**, set and reviewed in its workspace: gross margin at least 60%, unit cost at
  most EUR 250, lead time at most 8 weeks, MOQ at most 100 pieces per colour (no certificate rule).
- **The plain-words direction step was not part of this run.** The backend running at the time predated the change
  that lets a sketch be directed without a diffusion server (commit d853c4d), so the call returned "Diffusion model
  not connected" and the run continued with the sketch as uploaded. The hosted build includes the change. Only the
  short note typed with the upload ("TEST rehearsal: keep the half placket, add tonal embroidery on the collar")
  reached the tech pack, where it is printed as the creative direction; the vision model did not see it.
- **The last step is from the app's own log.** Read back through Atelier's API before the backend was restarted, the
  run's step log recorded PO-00001 as sent through the Evolus purchase-order workflow to our inbox, and the run as
  completed. Runs are kept in memory, so the restart lost the step log and audit trail; what stays on disk is the
  brand's PO counter (now at 1), its style counter and the three uploaded quote PDFs. We deleted the test product
  from the store afterwards.
- **One run.** Each figure in the table is a single measurement. On 16 October a timing script, on an earlier build,
  approved 9 designs (a mood-board image stood in for the design) and stopped each run once the RFQs were sent:
  approval to both RFQs sent took a median of 64 s (50–73 s) over the 8 runs that completed, and the ninth failed
  when the Evolus agent call failed. In the same session, 9 mood-board reads took a median of 10 s (7.9–38.2 s) and
  one more timed out. Those are the figures quoted in [docs/SUBMISSION.md](docs/SUBMISSION.md); the per-run times
  are in our working notes, not in this repository.

### Latency on a shared queue

AMD Token Factory is a shared queue and its waits are unpredictable. On 17 October the same small Gemma 4 call took
2.4 s, 11.7 s and 34.7 s in a row, and one customer-voice call through the Evolus agent took 128 s. Atelier therefore
hedges: when a call hasn't answered after a set time (10 s for vision in this deployment, 45 s for the Evolus agent),
it sends one identical second request, uses whichever answers first and cancels the other. An error reply never wins
over a request that is still running, and both requests are real calls to the same model.

On the hosted site on 17 October, two mood-board reads by a signed-out visitor took 12.8 s and 17.4 s of model time,
as shown on the trend card. They are examples, not a benchmark.

### The integrations

| Service | What Atelier uses it for | In this deployment |
|---|---|---|
| **AMD Token Factory**: Gemma 4 (`Gemma-4-31B-IT`) on AMD GPUs | Reading mood boards and sketches; the model behind the Evolus agent | Connected |
| **Evolus** agent | Tech pack, RFQs, counter-offers, creative direction, customer-voice summary | Connected |
| **Evolus** knowledge library | Brand book, brand profile and supplier catalogue, attached to the agent | In the workspace |
| **Evolus** document extractor | Supplier quote documents into data | Connected |
| **Evolus** email workflows | One for RFQs and counter-offers, one for purchase orders | Connected |
| **Shopify Admin API** | The pre-order product with size variants, publishing, counting orders | Connected (development store, EUR) |
| **ECB euro reference rates** | Converting a quote in another currency | Not exercised on 17 Oct: every quote was in EUR |
| Diffusion server (FLUX.1-schnell) on our own AMD GPU | Four AI concept renders per trend, collections | Not connected (optional) |
| Direct vLLM (Gemma 4) on our own AMD GPU | A backup for the agent: Atelier calls the model directly if the Evolus agent fails | Not connected (optional) |
| Evolus inbound-email and Shopify workflows | Quotes by email; listing through Evolus | Supported, not set up |

The model name the app shows is the one Atelier calls on the endpoint (a wrong name would make the call fail). AMD
Token Factory doesn't report which GPU served a request, so the GPU line is the operator's `AMD_GPU_LABEL`, here "AMD
GPUs (AMD Token Factory)"; the app names a specific AMD device only when that label does. The self-hosted path in
[deploy/](deploy/) (vLLM serving Gemma 4, plus FLUX.1-schnell, on an AMD Instinct MI300X on AMD Developer Cloud) has
not been run on real AMD hardware yet. Every Gemma 4 call measured here ran on AMD Token Factory.

## Business model

**Planned, not yet tested with a paying brand:** a subscription per brand, plus a fee per drop or per purchase order
Atelier sends. Prices are not set yet; we publish no price points.

**Who pays.** Direct-to-consumer and small-batch fashion brands that design their own pieces and sell through their
own online store. The first use: going from a sketch to a pre-sold drop without the paperwork.

**Why they would pay.**

| The brand's problem | What Atelier changes |
|---|---|
| Capital is committed before demand is known: samples and a full production run are ordered before the first sale | The purchase order goes out only after real pre-orders reach the production plan |
| Time and skilled work between an approved design and a supplier quote: tech packs, RFQ emails in other languages, quote spreadsheets | In our 17 October run, the costed tech pack was written and both RFQs sent 1 min 54 s after Approve. Mills still take their own time to quote, and sampling and production still take weeks |
| Dead stock, which ties up cash and which large EU companies may no longer destroy | Styles whose pre-orders miss the threshold are never made |

**What each fee maps to in the product.**

| Fee | What the brand gets | How Atelier counts it |
|---|---|---|
| Subscription, per brand | The brand's workspace (profile, brand book, suppliers, price list, guardrails, past sales) and the studio | One workspace per brand; today one backend holds one brand's workspace |
| Usage fee, per drop | An approved design taken through tech pack, RFQs, quotes, guardrails and a Shopify pre-order | Each approval starts a run |
| or per purchase order | A purchase order sent to a mill once real orders clear the threshold | Purchase orders are numbered per brand (PO-00001, …) |

**Market context.**

- 847,486 live Shopify stores sell apparel: 27.0% of the 3,143,979 live Shopify stores tracked by
  [Store Leads](https://storeleads.app/reports/shopify) (report updated 9 October 2026). That is a third-party
  tracker's estimate, not an official Shopify figure, and it counts stores, not brands that design their own
  collections.
- In March 2023, McKinsey estimated that within three to five years generative AI could add USD 150 billion
  (conservatively) and up to USD 275 billion to the operating profits of the apparel, fashion and luxury sectors
  ([McKinsey, "Generative AI: Unlocking the future of fashion"](https://www.mckinsey.com/industries/retail/our-insights/generative-ai-unlocking-the-future-of-fashion)).
  That is a projection, not a measured result. McKinsey also estimates that as much as one-fourth of generative AI's
  potential value in fashion may come from design and product development (BoF and McKinsey & Company,
  [The State of Fashion 2024](https://www.mckinsey.com/industries/retail/our-insights/state-of-fashion-2024),
  November 2023).

### Illustrative example: a 10-style capsule

> **Illustrative; every number here is an assumption, not a measurement or a forecast.** Adapted from
> [docs/BUSINESS_VALUE.md](docs/BUSINESS_VALUE.md) so that production follows Atelier's rule: a style is ordered from
> the mill only when its pre-orders reach the production plan, or the MOQ if that is higher.

Assumptions, in US dollars: 10 styles; an MOQ of 300 pieces per style, which is also the production plan; unit cost
$25; retail $100; 3 sample rounds per style at $300 each. Made before demand: 60% sells at full price, 30% at 50% off,
10% doesn't sell. Pre-sold: one physical proto per style before listing, and 6 of the 10 styles reach 300 pre-orders.

| | Make first | Pre-sell first (Atelier's rule) |
|---|---|---|
| Committed before any demand signal | $75,000 of production (10 × 300 × $25) and $9,000 of sampling (10 × 3 × $300) | $3,000: one proto per style (10 × $300) |
| Styles made | 10 (3,000 pieces) | 6 (1,800 pieces, all pre-sold) |
| Committed once demand is shown | – | $45,000 of production (6 × 300 × $25) and $3,600 of further sampling (6 × 2 × $300) |
| Left over | 300 pieces unsold ($7,500 at cost), and 900 sold at 50% off ($45,000 below full price) | No surplus from production; $1,200 of protos on the 4 styles that missed |

The example compares capital at risk before demand is known, not profit. It leaves out the sales the 4 dropped styles
might have made, cancelled or returned pre-orders, and customers who won't wait.

## How it works

**It runs on a real brand's data.** Nothing brand-specific is built in: the brand profile, brand book, supplier
directory, material price list, guardrails and (optionally) past sales are imported in the **Brand workspace**
(header → *Brand workspace*, or `/workspace`), stored in SQLite under `ATELIER_DATA_DIR` (default `backend/var/`,
git-ignored; a Docker volume in compose) and shown with their provenance ("Imported from suppliers.csv on …"). One
backend holds one brand's workspace. The studio can't approve a design until the workspace has a brand profile, at
least one supplier whose contacts the brand confirmed, and reviewed guardrails, because approving emails the brand's
suppliers (or the per-supplier *RFQ override* inbox the brand sets for a pilot). What to ask a pilot brand for:
[docs/PILOT_DATA.md](docs/PILOT_DATA.md). API: [CONTRACT.md "v5 — Brand workspace"](CONTRACT.md#v5--brand-workspace).

**Mood boards, read live.** There are nine preset boards: four from the pilot brand (AI-generated inspiration,
labelled as such) and five of openly licensed photographs (New York Fashion Week Fall/Winter 2010 runway shots, CC BY
2.0 via Wikimedia Commons, and 19th-century coats and jackets from The Met's Open Access collection, CC0). Picking a
board sends its images to the vision model on AMD, the same path as an upload. Nothing about a board is pre-written,
and the analysis says which model and host produced it. Without a vision endpoint the trend step says **"Vision model
not connected"** instead of inventing a trend.
- **Image credits.** Every image's author, source, licence and modifications (downscaled, re-encoded) are listed in
  [backend/static/moodboards/ATTRIBUTION.md](backend/static/moodboards/ATTRIBUTION.md) and `manifest.json`, and shown
  under **Image credits** in the picker. CC BY 2.0 requires that credit to stay with the photos if you redistribute
  them. Garments and logos in the photos belong to their owners.
- To rebuild or change the boards: `backend/scripts/build_moodboards.py` (it checks each licence at the source).

**The design: the designer's sketch first, concepts optional.** Without a diffusion server, the designer uploads
their own sketch or photo; Gemma 4 reads it (garment type, silhouette, collar, closure, pockets, details) into the
tech-pack brief, the creative director directs it in plain words ("three-quarter sleeves, gold thread on the collar"),
and the agent reads the direction back and carries it into the tech pack's measurements and materials. The sketch
becomes the Shopify product image. AI concept renders ("Generate four concepts",
"Compose a collection") need a diffusion server on our own AMD GPU ([deploy/](deploy/): FLUX.1-schnell on an AMD
Instinct MI300X, AMD Developer Cloud) and are offered only when one is connected.

**Customer voice.** The brand uploads its own reviews (CSV, TSV or PDF), or picks one of three public review samples
(200 real, anonymised reviews each, CC0). Fixed rules count the recurring themes and quote customers word for word;
the Evolus agent phrases the summary and the tech-pack change each theme calls for. Changes applied to a design reach
the tech pack with their evidence.

**Supplier quotes are real documents.** After the RFQs go out through the Evolus outreach workflow, the quotes step
waits ("Awaiting replies - 1 of 3 received") until the quotes arrive. In this deployment they are uploaded on the
Quotes panel; quotes by email (an Evolus inbound workflow that calls Atelier's webhook) are supported but not set up.
The Evolus document extractor reads each one; if it fails, the Evolus agent (Gemma 4 on AMD) reads the PDF's text,
and if that fails too, a plain parser does. Each quote says which one read it. A field the document doesn't state is
shown as **not stated**, never assumed (one exception, flagged on the quote: a quote that names no currency is read
in the brand currency), and a quote without a unit price is rejected. Quotes in another currency are converted with
the ECB's daily euro reference rates; if those can't be loaded, the quote stays in its own currency and says so.

**The agent knows when to hand the case to a person.** The brand's own guardrails (set in the Brand workspace: a
gross-margin floor, a unit-cost cap, maximum lead time and MOQ, required certificates; unset rules aren't checked) are
checked against every quote by plain arithmetic, with no model involved. If a quote doesn't state a value a rule
needs, the check fails as "not stated" and goes to a person. When the agent's pick breaks a rule, the run stops before
Shopify and explains, with the numbers. You approve (recorded as an override), switch supplier, or negotiate. The
counter-offer price is computed, not generated: the lower of retail × (1 − margin floor) and the unit-cost cap,
rounded down to the cent; for a quote in another currency it is converted at the ECB reference rate and rounded down
again. The Evolus agent writes the email in the mill's language with an English version alongside. A draft that
doesn't state that exact price is rejected, and the agent is instructed never to reveal the margin floor. The revised
quote is re-checked when it lands. Everything goes into an audit trail.

**Pre-orders are real.** Once a quote passes, Atelier creates the product in the brand's Shopify store (size
variants, published to the Online Store) and the demand panel shows a QR code so an audience can pre-order with a test
card. It counts those real orders through the Admin API (a hosted copy can also receive Shopify's `orders/create`
webhook once it is registered with `backend/scripts/check_shopify.py --register-webhook`); test orders are labelled as
such. Without a store, the Shopify step says **"Shopify not connected"**.

**The purchase order is real.** When the threshold is crossed, Atelier drafts a PO with the next number of the
brand's persisted sequence (PO-00001, …), for the production plan as it stands at that moment, and sends it to the
selected mill's address through an Evolus workflow (`EVOLUS_PO_WORKFLOW_ID`, else the outreach workflow). Without
Evolus it stays **"Draft - not sent"**, with a send button.

**"How many should we make?"** Every real order feeds the explained production forecast described in
[the thesis](#the-thesis-make-only-whats-already-sold). Its assumptions are labelled model parameters you can edit;
fit them to the brand's own past launches by hand (past sales imported in the Brand workspace are stored, but the
forecast does not read them yet).

## Latest development (16–17 Oct 2026)

- **Live end-to-end run (17 Oct).** Mood board → sketch → customer voice → tech pack → bilingual RFQs → two
  guardrail hand-offs and a negotiation → Shopify pre-order → test order → PO-00001, on AMD Token Factory, Evolus and
  Shopify. Approve to both RFQs sent: 1 min 54 s. Details and conditions are [above](#what-works-end-to-end-today).
- **Hosted public demo (16–17 Oct).** https://atelier.netlayerlabs.com. Signed-out visitors can read a mood board,
  upload a sketch and have it read, direct it in plain words, and run customer voice on three public review samples;
  approving and everything after it need the admin token. The dashboard calls its API on the same origin, so one build
  serves any domain pointed at the server. It runs with Docker Compose on a shared server: both containers listen only
  on 127.0.0.1 behind nginx over HTTPS, with memory caps of 768 MB for the API and 384 MB for the dashboard. Last
  deployed on 17 October, after commit 5dd33c1. (95e0077, e8dab9d, 6637b5f)
- **Security hardening (17 Oct).** Model calls are limited per visitor (15 per 10 minutes by default, 40 on the
  hosted site) and to 120 per 10 minutes in total; a request rejected before it reaches the model doesn't count. For
  signed-out visitors, email addresses in API responses are masked to the first letter, three dots and the domain.
  Visitor uploads pause once the uploads folder holds 1 GB, images over 40 megapixels are refused before decoding,
  and sketches are limited to 12 MB. The admin cookie is Secure behind HTTPS and object ids are 48-bit.
  (e8dab9d, 839b541)
- **Sketch first, diffusion optional (16–17 Oct).** Without a diffusion server, a design starts from the designer's
  own sketch or photo. Gemma 4 reads the garment type, silhouette and visible details into the tech-pack brief, the
  creative director can direct the design in plain words without re-rendering it, and the sketch becomes the Shopify
  product image. "Generate four concepts" and "Compose a collection" are offered only when a diffusion server is
  connected. Uploads must be PNG, JPEG or WebP, up to 12 MB, with the type checked from the file's content.
  (7b7f4c0, d853c4d, 839b541, 5dd33c1)
- **Hedged model calls (17 Oct).** A second, identical request when AMD Token Factory's queue is slow; an error reply
  never beats a request that is still running ([how it works](#latency-on-a-shared-queue)). (5b3aafb)
- **Pre-pitch audit (17 Oct).** A multi-agent AI code review in which every reported problem had to be reproduced
  before it counted: 31 of 44 reports were confirmed (7 high, 12 medium, 12 low severity). Six of the 7 high-severity
  findings are fixed. The seventh, the submission text in docs/SUBMISSION.md, is fixed except for three placeholders
  (the demo-video link, the slides and the closing measured result), which wait for the recording and the deck. Most
  medium and low findings are fixed too, with regression tests in `backend/tests/test_audit_17oct.py`.
  (d853c4d, 839b541, 90071ce, 5dd33c1)
  - *Orders and money:* the purchase order uses the production plan as it stands when the threshold is crossed. A
    quote arriving after the guardrail check can no longer quietly switch the order to a mill that breaks a
    guardrail; it is held and logged. One failed Evolus status check no longer forces re-sending every RFQ: the
    outcome counts as unknown only after 4 failed checks in a row. A partly failed email send names who was not
    emailed and keeps those RFQs as drafts. The Shopify listing states the brand's own delivery promise instead of a
    padded estimate.
  - *Screens and docs:* the dashboard leads with the sketch path when no diffusion server is connected, the
    "AI-generated inspiration" label stays on screen during analysis, visitors see "Apply (admin)" instead of a
    surprise sign-in, and a configured service that fails shows its error instead of a setup hint for variables that
    are already set. The docs describe what is actually deployed (AMD Token Factory), and the original plan documents
    are marked historical.
  - *Still open:* an order cancelled after it was counted stays in the demand count; the forecast's refusal message
    for very large order lists points at the wrong settings; the nginx config in `deploy/vps/` sends no HSTS header;
    visitors behind one shared address (venue Wi-Fi) share one model-call budget, which is why the hosted site allows
    40 calls per 10 minutes; a run can be read without the token by anyone who has its 48-bit id.
- **Fixes from rehearsals on live services (16–17 Oct).** A slow model now shows "timed out" with a Retry button
  instead of a setup hint (1c2ea4c, 77041e6). When the Evolus extractor fails, the Evolus agent reads the quote's PDF
  text before the plain parser (b169cf1). A counter-offer draft is accepted when it states the target price in any
  written form (246.0 EUR, €246, 246,00) and still rejected when it states a different price (edde3f8). Shopify
  access tokens are refreshed when permissions were granted after the token was issued (1c2ea4c), and the order poll
  no longer needs customer-data access (af4bc55). The email workflows receive only the fields they send, which keeps
  bilingual RFQs small (a826630).
- **Honest system status (17 Oct).** The landing page and the System panel show only what is running. Optional
  backups that are not connected (the direct vLLM path, the Evolus Shopify workflow, and the diffusion server while
  the sketch path works) are left out of both, so no setup hint appears for them; `/api/health` still reports them,
  marked optional rather than missing. (90071ce, 5dd33c1)
- **Forecast hardening (17 Oct).** The forecast refuses more than 1,000,000 observed pre-order units before
  allocating memory (in testing, an order list of 20,000 × 10,000 units froze the server). It also caps the size of
  its exact probability table and runs in a worker thread, so the API stays responsive. (d853c4d, e8dab9d)
- **Tests and a clean build (17 Oct).** All 395 backend tests pass (`uv run pytest -q`, 44 s). They run against
  local test doubles of every upstream service, which mark their responses as fake, so no live service is called. A
  fresh clone (commit 5b447ec) built and started with `docker compose up --build`; the API reported healthy and, with
  no `.env`, every service showed "not connected". Later commits were not rebuilt from a clean clone.

## Run it

```bash
./dev.sh
```

Opens the dashboard at http://localhost:3100 and the API at http://localhost:8787 (docs at `/docs`).
Requires `uv` and `pnpm`. Ports can be changed with `BACKEND_PORT` / `FRONTEND_PORT`.

**Nothing is mocked.** Every trend read, sketch reading, concept, tech pack, RFQ, quote, order and purchase order
comes from a real service: the AMD-hosted model (and a diffusion server when one is connected), the Evolus agent
and workflows, and a Shopify store. A service that isn't configured shows **not connected** in the header with the
variable to set (optional backups that are not connected are left out instead, and a configured service that fails
shows its error, not a setup hint); the features that need it show an honest error with a retry, never made-up
output. With no `.env` at all the app runs and tells you what to connect. **Inference** in the header opens per-call
stats (model, GPU, latency, and tokens/sec for calls that stream; calls through the Evolus agent show latency only)
once real calls have happened.

**Guided tour** (Shift+D, the tour button in the header or *Guided tour* in the menu, or `/?demo=1`): a tour of the
real UI against the real services. Where a beat needs a person (a supplier's quote document, a pre-order), it pauses
with a prompt and continues when the real data arrives. It never sends anything itself: before Approve (which emails
the brand's suppliers) and before a counter-offer it names every address the email goes to and waits for you to press
the button. The stage script, pre-show checklist and the recommended fallback (a pre-recorded video of a live run)
are in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

To go live:
- [docs/AMD_SETUP.md](docs/AMD_SETUP.md): AMD Token Factory (the hackathon setup: `AMD_VISION_ENDPOINT`,
  `AMD_VISION_MODEL=Gemma-4-31B-IT`, and the key in `AMD_VLLM_API_KEY`, which the app also sends to the vision
  endpoint; `AMD_GPU_LABEL` says what serves it), or your own vLLM for Gemma 4 (text + vision, one server) plus FLUX
  diffusion on AMD Developer Cloud. The scripts are in [deploy/](deploy/). The app reads the key only from
  `AMD_VLLM_API_KEY`, not `AMD_TOKEN_FACTORY_KEY`.
- [docs/EVOLUS_SETUP.md](docs/EVOLUS_SETUP.md): the Evolus workspace.
  - **The brain** is an Evolus agent whose model is Gemma 4 on AMD (AMD Token Factory in this deployment, registered
    in the Evolus workspace as our own model). The brand book, brand profile and supplier catalogue sit in an Evolus
    knowledge library attached to the agent; Atelier also retrieves passages from the same documents into each
    prompt, and those are the citations shown on the tech pack.
  - **Quotes** are read by a document extractor.
  - **Two email workflows** send RFQs and counter-offers, and purchase orders. Quotes by email (an inbound workflow)
    and an Evolus Shopify workflow are supported but not set up; Atelier creates the Shopify product through the
    Admin API.
  - API reference with sources: [docs/EVOLUS_API_NOTES.md](docs/EVOLUS_API_NOTES.md).
- [docs/SHOPIFY_SETUP.md](docs/SHOPIFY_SETUP.md): free dev store, Dev Dashboard app, test payments, real pre-orders.

Verify with `backend/scripts/check_amd.py`, `check_evolus.py` and `check_shopify.py`. To rehearse the plumbing
without credentials, `backend/tests/fake_upstreams.py` starts **test doubles** of every upstream; they mark their
responses, so the header shows them in red as "FAKE UPSTREAM - not real" and never shows the credits. More details
in [backend/README.md](backend/README.md).

## Run with Docker

```bash
docker compose up --build
```

Same URLs: dashboard at http://localhost:3100, API at http://localhost:8787. With no `.env` it starts and shows
every service as "not connected" (checked from a fresh clone at commit 5b447ec on 17 October 2026). If `backend/.env`
exists (copy `backend/.env.example`), the backend loads it. Inside the container, an SSH tunnel on the host is
`host.docker.internal`, e.g. `AMD_VLLM_ENDPOINT=http://host.docker.internal:18000/v1`.

To use other host ports: `BACKEND_PORT=8890 FRONTEND_PORT=3190 docker compose up --build`.

**Access.** Both ports are published on `127.0.0.1` only, and without `ATELIER_ADMIN_TOKEN` the API accepts changes
from this machine only (`GET /api/health` says so under `security`). Changes must also come from the dashboard's own
origin (`CORS_ORIGINS`): a cross-site form post is refused. To host Atelier for others, set `ATELIER_ADMIN_TOKEN` in
`backend/.env` (signed-out visitors can then run only the steps with no outside effect, rate-limited, and the
dashboard asks for the token when a step needs it; scripts send `Authorization: Bearer <token>`); edit
`docker-compose.yml` so that `PUBLIC_BASE_URL` and `CORS_ORIGINS` under `backend.environment` (these override
`backend/.env`) and the frontend build arg `NEXT_PUBLIC_API_BASE` (the public API URL, or `same-origin` behind a
proxy that serves `/api` and `/static`) name the public URLs; and publish on all interfaces with
`BACKEND_BIND=0.0.0.0 FRONTEND_BIND=0.0.0.0`. Behind a reverse proxy or tunnel, always set the token. Supplier
quote documents and brand files are private (served only to signed-in / local clients); webhooks stay open to their
senders and are verified by signature / shared secret. Details: [CONTRACT.md "Access, uploads and quote
integrity"](CONTRACT.md#v5--access-uploads-and-quote-integrity-qa-fixes). For a server behind nginx,
[deploy/vps/](deploy/vps/) handles this with its own compose file and env file (see below).

Next.js inlines `NEXT_PUBLIC_API_BASE` into the browser bundle at build time, so compose passes it as a build
arg (`http://localhost:$BACKEND_PORT`). The backend URL is fixed per build: change it, then rebuild. The value
`same-origin` makes the dashboard call `/api` on its own host instead, which is what the hosted copy uses behind nginx.

**The hosted copy** (https://atelier.netlayerlabs.com) is deployed with [deploy/vps/](deploy/vps/):
`VPS=user@host HOST=your.domain deploy/vps/deploy.sh` builds the dashboard on your machine (same-origin API), uploads
it with the backend, and starts both containers on the server, listening on 127.0.0.1 only with memory caps, behind
nginx. It needs `backend/.env.vps` (your `backend/.env` plus `ATELIER_ADMIN_TOKEN`, `PUBLIC_BASE_URL=https://$HOST`
and `CORS_ORIGINS=https://$HOST`), Docker Compose on the server, and `deploy/vps/nginx-atelier.conf` installed once.

## Submission

- Containerized: `backend/Dockerfile` (FastAPI on Python 3.12, uv-locked deps, non-root, healthcheck) and
  `frontend/Dockerfile` (Next.js standalone build, non-root). `docker-compose.yml` wires them together and
  starts the dashboard once the API is healthy.
- To run it: clone the repo, run `docker compose up --build`, open http://localhost:3100. The header shows which
  services are connected; set up the Brand workspace (`/workspace`) and configure `backend/.env` (AMD endpoints,
  Evolus, Shopify) to run the flow end to end. The image includes the preset mood boards (`backend/static/moodboards`);
  the brand's data and PO / style numbers persist on the `atelier-data` volume.
- No keys are committed. Configuration lives in git-ignored `.env` files; only the example templates are in the repo.
- The submission form text, tracks and demo-video script: [docs/SUBMISSION.md](docs/SUBMISSION.md). The stage
  script: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Layout

- [backend/](backend/): FastAPI orchestrator: vision, the agent's brain, diffusion, Evolus and Shopify adapters,
  guardrails and the forecast (real services only). Module map: [backend/README.md](backend/README.md).
  - `backend/scripts/`: live checks (`check_amd.py`, `check_evolus.py`, `check_shopify.py`), Evolus provisioning,
    the mood-board and knowledge builders, and the review-dataset fetcher
  - `backend/tests/`: the test suite and the test doubles (`fake_upstreams.py`)
  - `backend/static/moodboards/`: the preset boards, `manifest.json` and `ATTRIBUTION.md`
- [frontend/](frontend/): Next.js dashboard: landing page, studio and Brand workspace (`/workspace`)
- [deploy/](deploy/): the self-hosted AMD path (vLLM for Gemma 4, the FLUX diffusion server, SSH tunnel; not yet run
  on real AMD hardware). [deploy/vps/](deploy/vps/): the hosted copy (Compose, nginx site, deploy script)
- [docs/](docs/): setup guides for [AMD](docs/AMD_SETUP.md), [Evolus](docs/EVOLUS_SETUP.md) and
  [Shopify](docs/SHOPIFY_SETUP.md); [sources for the business case](docs/BUSINESS_VALUE.md);
  [pilot data checklist](docs/PILOT_DATA.md); [stage script](docs/DEMO_SCRIPT.md);
  [submission text](docs/SUBMISSION.md); [design system](docs/DESIGN.md). `docs/pilot/` holds the pilot's brand book
  (AI-generated imagery, labelled)
- [CONTRACT.md](CONTRACT.md): the API contract between backend and frontend
- [PROJECT_SPEC.md](PROJECT_SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md): the original plan of 12 October, kept as
  history; the shipped stack differs
- `dev.sh` and `docker-compose.yml`: local run. [LICENSE](LICENSE): MIT

## Tests

```bash
(cd backend && uv run pytest -q)
(cd frontend && pnpm lint && pnpm build)
```

The backend suite (395 tests; all passed on 17 October 2026 in 44 s) runs against local test doubles of every
upstream (`backend/tests/fake_upstreams.py`), which mark their responses as fake, so no live service is called and no
email is sent. It includes the regression tests for the 17 October audit (`backend/tests/test_audit_17oct.py`).

Against the real services (from `backend/`, with `backend/.env` set): `uv run python scripts/check_amd.py`,
`uv run python scripts/check_evolus.py` (`--no-execute` runs no workflow and uses no extractor credits) and
`uv run python scripts/check_shopify.py` (`--no-write` is read-only).
