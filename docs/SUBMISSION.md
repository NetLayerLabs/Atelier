# lablab.ai submission: Atelier

Text for the AMD Developer Hackathon: ACT III submission form, matching what is deployed on 18 Oct 2026. Only measured or sourced numbers (see [BUSINESS_VALUE.md](BUSINESS_VALUE.md)).

## Project title

Atelier: from signal to storefront, made only once it's sold

## Short description

An AI agent for independent fashion brands: it reads the trend from a mood board or the designer's own sketch with Gemma 4 on AMD, writes the tech pack, briefs and negotiates with suppliers in their language through Evolus, checks every quote against the brand's own rules, opens a real Shopify pre-order, and only then sends the purchase order. Make only what's already sold.

## Long description

Fashion commits to production months before it knows what will sell. The industry made an estimated 2.5–5 billion surplus items in 2023, worth $70–140 billion in sales (McKinsey & BoF, *State of Fashion 2025*), and since 19 July 2026 large companies in the EU may no longer destroy unsold clothing. Meanwhile design and development alone takes 11–24 weeks (McKinsey, 2018), much of it tech packs, emails and spreadsheets.

Atelier is an agent that runs that process end to end while a human creative director keeps every taste decision:

1. **Signal.** Gemma 4 (Google's open model) on AMD GPUs reads the trend from a mood board: the pilot brand's own boards (AI-generated inspiration, labelled as such) or real, openly licensed runway photos. The brand can also upload its customer reviews; Atelier counts recurring issues with explainable rules, quotes customers word for word, and turns the patterns into cited tech pack changes.
2. **The design.** The designer uploads their own sketch or photo; Gemma 4 reads it (collar, closure, pockets, details) into the tech-pack brief, so the factory makes the designer's design, not a guess. With a diffusion server connected, the same model can also render four concepts or a capsule collection.
3. **Vibe check.** The creative director directs in plain words ("three-quarter sleeves, gold thread on the collar"). The agent reads the direction back and carries it into measurements and materials.
4. **Production.** After approval, five agents take over:
   - an Evolus agent on our open model (Gemma 4 on AMD, connected to the Evolus workspace as our own model) writes the tech pack, grounded in the brand book through an Evolus knowledge library;
   - an Evolus workflow sends RFQs to the brand's suppliers in their own language (Italian with the English alongside);
   - supplier quote PDFs (uploaded or emailed) are read into data by an Evolus document extractor and ranked;
   - if the best quote breaks the brand's guardrails (margin floor, cost cap, lead time, MOQ, certifications), the agent stops and hands the decision to a person: approve, switch mill, or negotiate with a counter-offer whose target price is computed from the margin floor;
   - a real Shopify pre-order with size variants goes live, and real orders feed an explained production forecast (Gamma–Poisson on a Bass launch curve, newsvendor quantity, size split from real orders; no language model in the maths). Once demand passes the threshold, the purchase order is sent to the mill through an Evolus workflow.

There is no mock mode: every number on screen comes from a live model call, a real document, a real order or a labelled, editable assumption. Brand, supplier and price data come from the pilot brand's own workspace.

**Measured on live runs (16 Oct 2026, AMD Token Factory + Evolus + Shopify):** approval to tech pack written and RFQs sent to two suppliers, 64 s median (p90 73 s, 8 runs); a mood-board trend read, 10 s median (p90 38 s, 9 runs); a quote above the brand's cost cap stopped the agent and a counter-offer went out in 18 s. **Pilot brand:** UGO SARTORIA, Igbo menswear with Italian tailoring, priced in EUR; its demo suppliers route to the team's own inbox, so every email in the demo is real.

## Track and partners

- Main track: **Reinvent Commerce**
- Partner track: **Evolus: Business Agents on AMD**
- Also eligible: **Vibe Generation special prize**

Evolus building blocks used, all driven from the app through the Evolus API: the agent (chat on our own AMD-hosted model), a knowledge library holding the brand book, a document extractor for supplier quotes, and two email workflows (RFQs and counter-offers; purchase orders).

## Technology tags

AMD Token Factory, AMD GPUs, Gemma 4 (Gemma-4-31B-IT), Google, Evolus, Shopify, FastAPI, Next.js, Docker, MIT.

## Links

- Public repo: https://github.com/NetLayerLabs/Atelier
- App URL: https://atelier.netlayerlabs.com (visitors can try every step up to Approve; approving sends real supplier emails and opens a real Shopify pre-order, so it needs the admin token - the live pitch shows it end to end)
- Demo video: (add the link once recorded)
- Slides: (PDF export of the pitch deck)

## Demo video script (4:30–5:00, recorded on a live run)

lablab's rubric scores a video under 3 minutes as "Limited" and expects every feature shown, under 5 minutes (MP4, under 300 MB). Record against live AMD Token Factory, Evolus and Shopify. Show AMD proof on screen: the header's live status, the trend card's "Analysed by Gemma-4-31B-IT on developer.amd.com.cn · AMD GPUs (AMD Token Factory)" line, and the Inference panel (model, host, latency). Say "Gemma 4 on AMD" out loud (Google prize); only say "MI300X" if the droplet is connected on the day.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Landing hero, problem slide numbers | "Fashion makes before it knows: 2.5 to 5 billion surplus items in 2023. Atelier makes only what's already sold." |
| 0:20–0:40 | Brand workspace: the pilot's profile, suppliers (contacts confirmed), guardrails | "Atelier runs on the brand's own data: its brand book, its suppliers, its prices, its rules." |
| 0:40–1:05 | Customer voice: the pilot's reviews export, themes, cited changes | "We start from what customers said: counted with explainable rules, quoted word for word." |
| 1:05–1:25 | Pick the UGO SARTORIA board; trend read live ("Analysed by Gemma-4-31B-IT on AMD GPUs") | "Gemma 4, Google's open model, on AMD GPUs reads the trend from the brand's own board." |
| 1:25–1:55 | Start from my sketch: a photo of a hand drawing, Gemma's reading, a direction, "Atelier heard…" | "Most designers already have a drawing. Gemma 4 reads what I drew, not a guess. I direct it in plain words and the agent reads it back." |
| 1:55–2:20 | Approve; tech pack with brand-book citations; the Inference panel | "An Evolus agent on our AMD-hosted model writes the tech pack, grounded in the brand book." |
| 2:20–2:45 | RFQs in Italian with English alongside; a real quote PDF read by the Evolus extractor; ECB FX conversion | "RFQs go out in the mill's language; replies are turned into data by the Evolus document extractor." |
| 2:45–3:15 | Guardrail hand-off → negotiate → counter-offer in Italian → revised quote → audit trail | "When a quote breaks the brand's rules, the agent stops and hands the decision to a person." |
| 3:15–3:45 | Shopify pre-order with sizes; real test orders arriving; QR | "A real Shopify pre-order goes live. Every order is real." |
| 3:45–4:15 | Forecast: projection, newsvendor quantity, size split, "How this was calculated" | "How many to make: classic statistics from real orders, no language model in the maths." |
| 4:15–4:35 | PO-00001 sent via Evolus workflow; tech pack PDF | "The purchase order goes to the mill through Evolus." |
| 4:35–4:55 | Measured gain slide + close | "[Measured result.] Make only what's already sold." |

## Cover image

1920×1080 (check the form's required size): the tailor's-table image F1 (AI-generated inspiration, our own asset) with the Atelier lockup and the line "Make only what's already sold." in the app's monochrome style. No third-party brand logos.
