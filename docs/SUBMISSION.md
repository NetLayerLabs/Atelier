# lablab.ai submission: Atelier

Draft text for the AMD Developer Hackathon: ACT III submission form. Bracketed values must be filled before submitting; only use measured or sourced numbers (see [BUSINESS_VALUE.md](BUSINESS_VALUE.md)).

## Project title

Atelier: from signal to storefront, made only once it's sold

## Short description

An AI agent for independent fashion brands that turns trends and the brand's own customer reviews into designs, writes the tech pack, sources and negotiates with mills in their language, opens a real Shopify pre-order, and sizes production from real orders. Open models on AMD Instinct, orchestrated by Evolus.

## Long description

Fashion commits to production months before it knows what will sell. The industry made an estimated 2.5–5 billion surplus items in 2023, worth $70–140 billion in sales (McKinsey & BoF, *State of Fashion 2025*), and since 19 July 2026 large companies in the EU may no longer destroy unsold clothing. Meanwhile design and development alone takes 11–24 weeks (McKinsey, 2018), much of it tech packs, emails and spreadsheets.

Atelier is an agent that runs that process end to end while a human creative director keeps every taste decision:

1. **Signal.** A vision model on AMD reads trends from mood boards (real, openly licensed photos) or the brand's own references. The brand can also upload its reviews, returns and support tickets; Atelier counts recurring issues with explainable rules, quotes customers word for word, and turns the patterns into cited tech pack changes.
2. **Concepts.** A diffusion model on AMD renders concepts or a whole collection.
3. **Vibe check.** The creative director directs by voice or text ("make it darker, cropped, more Margiela"). The agent reads the direction back, renders new variations with lineage, and carries the direction into measurements and materials.
4. **Production.** After approval, five agents take over:
   - an Evolus agent running our open model on AMD writes the tech pack, grounded in the brand book through an Evolus knowledge library;
   - an Evolus workflow sends RFQs to the brand's suppliers in their own language (Italian, Portuguese, English);
   - supplier quote PDFs (uploaded or emailed) are read into data by an Evolus document extractor and ranked;
   - if the best quote breaks the brand's guardrails (margin floor, cost cap, lead time, MOQ, certifications), the agent stops and hands the decision to a person: approve, switch mill, or negotiate with a counter-offer whose target price is computed from the margin floor;
   - a real Shopify pre-order with size variants goes live, and real orders feed an explained production forecast (Gamma–Poisson on a Bass launch curve, newsvendor quantity, size split from real orders; no language model in the maths). Once demand passes the threshold, the purchase order is sent to the mill through an Evolus workflow.

There is no mock mode: every number on screen comes from a live model call, a real document, a real order or a labelled, editable assumption. Brand, supplier and price data come from the pilot brand's own workspace.

**Measured result:** [__ min median from approval to tech pack and RFQs sent, over __ live runs on AMD]. **Pilot:** [pilot brand and outcome].

## Track and partners

- Main track: **Reinvent Commerce**
- Partner track: **Evolus: Business Agents on AMD**
- Also eligible: **Vibe Generation special prize**

Evolus building blocks used: agent chat with our own AMD-hosted model, knowledge library, document extractor, workflows (outreach, inbound quotes, negotiation, purchase order), AI Tool.

## Technology tags

AMD Developer Cloud, AMD Instinct MI300X, ROCm, vLLM, Gemma 4, Google, gemma-4-26B-A4B-it, FLUX, Evolus, Shopify, FastAPI, Next.js, Docker. [Confirm the model actually served before submitting: `check_amd.py` must show PASS gemma-4.]

## Links

- Public repo: https://github.com/NetLayerLabs/[repo]
- App URL: [app URL]
- Demo video: [video URL]
- Slides: [PDF export of the pitch deck]

## Demo video script (4:30–5:00, recorded on a live run)

lablab's rubric scores a video under 3 minutes as "Limited" and expects every feature shown, under 5 minutes (MP4, under 300 MB). Record against live AMD, Evolus and Shopify. Show AMD proof on screen: the header's live status, the inference panel (model id, tokens/s), and one shot of `rocm-smi` / the vLLM model list on the droplet. Say "Gemma 4 on AMD Instinct MI300X" out loud (Google prize).

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Landing hero, problem slide numbers | "Fashion makes before it knows: 2.5 to 5 billion surplus items in 2023. Atelier makes only what's already sold." |
| 0:20–0:40 | Brand workspace: the pilot's profile, suppliers (contacts confirmed), guardrails | "Atelier runs on the brand's own data: its brand book, its suppliers, its prices, its rules." |
| 0:40–1:05 | Customer voice: the pilot's reviews export, themes, cited changes | "We start from what customers said: counted with explainable rules, quoted word for word." |
| 1:05–1:25 | Pick a mood board; trend read live ("Analysed by gemma-4 on AMD") | "Gemma 4, Google's open model, on our AMD MI300X reads the trend from real photos." |
| 1:25–1:55 | Concepts, collection view, spoken direction, "Atelier heard…" | "The creative director directs by voice. The agent reads it back, then renders new options." |
| 1:55–2:20 | Approve; tech pack with brand-book citations; inference panel; `rocm-smi` cut-in | "An Evolus agent running our own vLLM endpoint writes the tech pack, grounded in the brand book." |
| 2:20–2:45 | RFQs in Italian with English alongside; a real quote PDF read by the Evolus extractor; ECB FX conversion | "RFQs go out in the mill's language; replies are turned into data by the Evolus document extractor." |
| 2:45–3:15 | Guardrail hand-off → negotiate → counter-offer in Italian → revised quote → audit trail | "When a quote breaks the brand's rules, the agent stops and hands the decision to a person." |
| 3:15–3:45 | Shopify pre-order with sizes; real test orders arriving; QR | "A real Shopify pre-order goes live. Every order is real." |
| 3:45–4:15 | Forecast: projection, newsvendor quantity, size split, "How this was calculated" | "How many to make: classic statistics from real orders, no language model in the maths." |
| 4:15–4:35 | PO-00001 sent via Evolus workflow; tech pack PDF | "The purchase order goes to the mill through Evolus." |
| 4:35–4:55 | Measured gain slide + close | "[Measured result.] Make only what's already sold." |

## Cover image

1920×1080 (check the form's required size): the Atelier wordmark in Fraunces italic on near-black (#0E0D0B), the line "Make only what's already sold." in champagne (#D9BE8C), and one real board photo or a real concept rendered on AMD. No third-party brand logos.
