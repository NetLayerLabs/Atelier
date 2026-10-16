# Business value: sources and claims

Research compiled 2026-10-13 for the pitch deck and landing page. Confidence: **P** = read on the primary source; **S** = credible primary, confirmed via secondary coverage or search snippets; **V** = vendor/blog/anecdote, use only as "indicative". Open the S-marked McKinsey/BoF PDFs in a browser before the deck is final.

## Use these

| Claim | Figure | Source | Conf. |
|---|---|---|---|
| Overproduction | 2.5–5 bn surplus items, worth $70–140B in sales (2023) | McKinsey & BoF, *State of Fashion 2025* — [BoF](https://www.businessoffashion.com/articles/retail/the-state-of-fashion-2025-report-inventory-excess-stock-supply-chain/), [PDF](https://www.mckinsey.com/~/media/mckinsey/industries/retail/our%20insights/state%20of%20fashion/2025/the-state-of-fashion-2025-v2.pdf) | S |
| Destruction in the EU | 4–9% of textiles on the EU market destroyed before use; up to 5.6 Mt CO2e | EEA briefing, Mar 2024 — [EEA](https://www.eea.europa.eu/en/newsroom/news/many-returned-and-unsold-textiles) | P |
| Why now | EU ban on destroying unsold apparel & footwear for large companies since 19 Jul 2026 (ESPR, Reg. 2024/1781 Art. 25); medium firms 2030 | [HLC](https://hlc.com/en/publications/stop-the-destruction-of-textiles-how-compliance-changes-from-19-july-2026), [BRC](https://brc.org.uk/news-and-events/news/sustainability/2026/ungated/sustainability-guidance-on-destruction-of-unsold-clothing/) | S |
| Slow development | Concept-to-market 28 wks (vertical) vs 44 wks (hybrid); design & development alone 11 vs 24 wks | McKinsey, *Faster fashion*, 2018 — via [Retail Dive](https://www.retaildive.com/news/Apparel-lead-times-McKinsey-vertical-integration/540838/) | S |
| Full-price sell-through | Often ~60%; 70% is the target | [Glossy](https://www.glossy.co/fashion/from-pre-orders-to-small-batches-fashion-brands-are-taking-control-of-their-inventory/), [FashionUnited](https://fashionunited.uk/news/background/from-margins-to-sell-through-important-figures-used-in-the-fashion-industry/2023112672770) | S/V |
| Pre-order works | Stòffa: >90% of revenue paid before production; Prabal Gurung, Antonio Berardi: 20–25% of revenue pre-order/MTO | [BoF](https://www.businessoffashion.com/articles/retail/zero-inventory-fashion-business/), [Glossy](https://www.glossy.co/fashion/pre-order-is-catching-on-as-a-solution-to-fashions-overproduction-problem/) | S |
| Theory | Advance selling gives the firm demand information (not always optimal) | Prasad, Stecke & Zhao, *POM* 2011; Boyacı & Özer, *Operations Research* 2010 | P |
| Gen AI value | $150–275B operating-profit potential in apparel/fashion/luxury in 3–5 yrs; up to ~25% in design & product development | [McKinsey 2023](https://www.mckinsey.com/industries/retail/our-insights/generative-ai-unlocking-the-future-of-fashion), [State of Fashion 2024](https://www.mckinsey.com/de/news/presse/2023-11-28-state-of-fashion-2024) | S |
| Market | 847,486 Shopify stores sell apparel (27% of live stores, Oct 2026) | [StoreLeads](https://storeleads.app/reports/shopify) | P (tracker; definitions vary) |
| System waste (context only, post-consumer) | One garbage truck of textiles landfilled/burned every second; ~$500B/yr lost to underuse and non-recycling | Ellen MacArthur Foundation, *A New Textiles Economy*, 2017 | S, dated |

Indicative only (V): tech pack 2–8 h of skilled work per style; 3–5 sample rounds at $150–600 each; overseas MOQ 300–1,000 units/style; RFQ response windows 5–7 business days.

## Do not use

- **"30% of clothes are never sold"**: traces to an unsourced claim about *returned* items (FashionUnited/ACTA 2018–19). Very weak.
- **"Fashion is 10% of global emissions"**: mistranslation; UNEP gives 2–8%.
- **"Trend-to-market 6 months → 24 hours"** (from our own PROJECT_SPEC.md): not defensible, since sampling and production still take weeks.
- Vendor claims like "40–60% fewer sample revisions" or "60–80% of shoppers will pre-order".

## Known gaps (say them openly)

No credible study exists for apparel RFQ cycle time, pre-order conversion/deposit norms, or the % time saved by gen AI on tech packs. That's why Atelier reports its own measured numbers.

## Measurable-gain slide

1. **Approved concept → tech pack + RFQs sent.** Baseline: design & development 11–24 wks (McKinsey); tech pack 2–8 h/style (vendor). Atelier: **our measurement**: median/p90 wall-clock from "Approve" to tech pack ready and RFQs queued, over ≥10 *live* runs, plus human review minutes. Score 3–5 tech packs against a checklist with someone who has garment-tech experience.
2. **Capital committed before demand is proven.** Baseline: MOQ × styles upfront; $70–140B of surplus in 2023. Atelier: production only after the pre-order threshold (our estimate, below).
3. **Samples per style that sells.** Baseline: 3–5 rounds × $150–600 (vendor). Atelier: concepts that miss the threshold never get past the proto.
4. **Units at risk.** Baseline: 4–9% of EU textiles destroyed; ~60% full-price sell-through; destruction now banned for large EU firms. Atelier: units ≈ max(pre-orders, MOQ), and the forecast sets the quantity.

## ROI story: 10-style capsule (illustrative, every number an assumption)

- **Traditional:** 10 styles × 300 MOQ × $25 = **$75,000 committed before any demand signal**; sampling 10 × 3 × $300 = $9,000; ~50 h of tech-pack work. At $100 retail with 60/30/10 full-price/markdown/unsold → 300 dead units ($7,500 cost) and $45,000 of markdown revenue forgone.
- **With Atelier:** same-day tech packs and RFQs (to be measured); each concept goes up as a deposit-backed pre-order. If 6 of 10 reach a 150-order threshold, only 6 go to sampling ($5,400, saving $3,600) and production ($45,000, committed after 900 units are presold). Capital at risk before demand drops from $75,000 to ~$1,200 (one proto for each of the 4 cut styles).

## Caveats to state on stage

- MOQs still apply: 120 pre-orders against a 300 MOQ means holding 180 units or paying a low-MOQ premium. The forecast's MOQ note addresses this.
- Selling on AI renders before a physical sample carries consumer-protection risk. Frame the listing as a deposit-backed pre-order or waitlist, with "made to order, ships in X weeks".
