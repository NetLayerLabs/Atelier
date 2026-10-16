# Stage script: Atelier, live

This is for whoever presents Atelier on stage. **Nothing in the app is mocked** (CONTRACT.md "v5"): every concept,
tech pack, RFQ, quote, order and purchase order comes from a real service. Demo mode is a guided tour that drives
the real UI against those real services — it clicks, types and scrolls for you, but it never injects a document, an
order or a number, and it never sends an email. Where a beat needs a person (a supplier's quote, a pre-order), it
**pauses with a prompt** and carries on when the real data arrives. At **Approve** it pauses and lists every
supplier and address the RFQs will go to (RFQ override inboxes marked); **you** press Approve. The counter-offer
works the same way (you press Send), and before the pre-order wait it tells you which mill and address the PO goes to
once the threshold is crossed.

Because everything is live, the stage fallback is **a pre-recorded video of a live run**, not a simulation (see
"Fallback" below).

## Before the show

- [ ] Start the app: `./dev.sh` (dashboard http://localhost:3100, API :8787). For the most stable run use a
      production build of the frontend: `cd frontend && pnpm build && pnpm start`. The hosted copy
      (`deploy/vps/deploy.sh`) needs the admin token to change anything: sign in on the dashboard first.
- [ ] Connect everything and check it:
      - AMD: vLLM, the VLM and the diffusion server (`backend/scripts/check_amd.py`), `AMD_GPU_LABEL` set to what
        `rocm-smi` really shows.
      - Evolus: agent (brain), extractor, outreach workflow, the PO workflow (`EVOLUS_PO_WORKFLOW_ID`, or the
        outreach one), and the inbound-email workflow if quotes will arrive by email (`check_evolus.py --quote-pdf
        <a real quote>`).
      - Shopify dev store (`check_shopify.py`), `DEMAND_STAGE_THRESHOLD=5`.
- [ ] Open the **System** popover in the header. Every service must read **connected** (green). Anything
      **not connected** or **unreachable** will stop its step with an error and a retry — fix it before the show.
      Anything in **red as FAKE UPSTREAM — not real** means `.env` still points at the test doubles: never present
      that. The credit line "Powered by AMD Instinct · Orchestrated by Evolus" only appears when those real services
      are connected — and "AMD Instinct" only when the hardware is verified (`AMD_GPU_LABEL` naming the AMD GPU, or the
      diffusion server reporting one); otherwise the header says "Model connected — hardware not verified".
- [ ] **Brand workspace** (`/workspace`, docs/PILOT_DATA.md): the brand profile, the supplier directory with real
      contacts (or a per-supplier *RFQ override* inbox you monitor for the pilot) **confirmed**, and the guardrails
      **reviewed**. Until then approving is refused (409) and the tour **pauses at Approve** and points to
      `/workspace` (it opens in a new tab; the tour continues by itself once the workspace is ready).
- [ ] Arrange the two human inputs:
      - **Supplier quotes.** Real quote documents from the suppliers you RFQ (a pilot supplier who agreed to take
        part in the demo is fine — **say so on stage**). Have the PDFs on the laptop to drop onto the Quotes panel, or
        have the supplier reply by email to the monitored inbox (Evolus inbound workflow → extractor → webhook).
        Atelier never generates a quote.
      - **Pre-orders.** Phones ready to scan the QR code and pay with the dev store's test card. Test orders are
        counted and labelled "test order" on screen — say so.
- [ ] Guardrails: check them in **Edit guardrails** (the hand-off beat only happens if a real quote breaks one — it is
      not scripted).
- [ ] Do one full rehearsal with `http://localhost:3100/?demo=1`, then **Start over**. Record it (see Fallback).
- [ ] Close every other app, Do Not Disturb on, notifications off.
- [ ] Projector: Chrome full screen, zoom 110–125 %.
- [ ] Internet is required (the models, Evolus, Shopify and the ECB rates for currency conversion are online).

### Demo controls

| Key | Action |
|---|---|
| Shift+D or header **Tour** | Start / exit the tour |
| Space | Pause / resume |
| → | Skip the rest of the current beat |
| C | Presenter captions on/off |
| Esc | Exit. The app stays where it is and you can keep clicking by hand |

`?demo=1` starts the tour on load; `&pace=…` changes how long it holds on each screen; `&captions=1` turns captions
on. If a service is not connected the tour shows that step's error and waits: fix it and press **Retry**, or Esc.

## Honesty rules

- Everything on screen is real or it is an error. If a step shows **not connected** / **unreachable**, say so; don't
  talk over it as if it worked.
- Name the source of each document: "this quote is the mill's own PDF, read by the Evolus extractor" (the card says
  which engine read it). Fields the quote doesn't state show **not stated** — that's the point, not a bug.
- Currency: converted at the ECB reference rate of the day (the card shows the date); if the rates couldn't be
  loaded the quote stays in its own currency, marked "not converted".
- The hand-off happens only if a real quote breaks a guardrail (or doesn't state what a guardrail needs). If none
  does, say "inside the guardrails, so it carries on".
- Pre-orders are real orders on a dev store with test payments; the stage threshold (e.g. five pre-orders) is on
  screen next to the production plan. Say both.
- The purchase order is sent to the mill's address through the Evolus workflow; the card says "sent via Evolus
  workflow …". If Evolus is not connected it says **draft — not sent**: say exactly that.
- "Live on AMD": say it when the **Inference** panel shows measured calls with the model and GPU. It shows nothing
  until real calls exist.
- Don't quote throughput or time savings you haven't measured on that run.

## The script

Timings depend on the models and on the people in the room; rehearse to know yours.

| # | Beat | On screen | Say |
|---|---|---|---|
| 1 | Opening | Landing, then the studio | "Fashion brands still take months and a dozen tools to go from a trend to a product. Most of that is paperwork. Atelier is an agent that does the paperwork so the creative director can keep the taste." |
| 2 | Mood board | The pilot brand's board *UGO SARTORIA - Ceremonia* (labelled **AI-generated inspiration**), or a real runway board (openly licensed photos, credits under the picker) | "We start where a designer starts: a mood board. This is our pilot brand's own board - AI-generated inspiration, and labelled so - and Gemma 4 on AMD reads it live." |
| 3 | Trend read | *The signal* from the vision model | "A vision model on AMD reads it: the silhouettes, the palette, the fabrics." |
| 4 | Customer voice | The brand's own reviews: counts, shares, quotes; *Apply to design* | "And what our customers already told us. Counted and quoted, never paraphrased — those become tech pack changes." |
| 5 | Concepts **or your sketch** | *Start from my sketch*: drop a photo of a real hand drawing; Gemma 4 reads it (garment, silhouette, the details it can see). Or four concepts from the diffusion model, when it is connected | "Most designers already have a drawing. Gemma 4 reads what I drew - not a guess - and that reading goes into the tech pack." |
| 6 | Pick + direct | A concept picked, an instruction typed | "Now the human comes in. I pick one and direct it the way I'd brief a studio." |
| 7 | Atelier heard… | The brain's read-back | "The agent reads it back — what it will change, and what goes into the tech pack." |
| 8 | Approve | Approve for production | "I approve it. From here the agents take over, inside the guardrails I set." |
| 9 | Tech pack | The brain's tech pack | "The tech pack carries my direction and the customers' evidence." |
| 10 | RFQs | RFQs in each mill's language, sent through Evolus: open the Italian one and its English copy side by side | "The RFQs go out in each mill's own language, through the Evolus workflow. Our pilot's demo suppliers are our own inbox - say so." |
| 11 | **Pause: quotes** | The tour waits: *"Waiting for a supplier quote — upload or email one"* | Drop the mills' PDFs on the Quotes panel (or let the email arrive). "These are the mills' own documents. The Evolus extractor reads each one; what a quote doesn't say stays *not stated*." The tour continues when the quotes are in (or when you click *Stop waiting & recommend*). |
| 12 | Recommendation | Scores, the brain's rationale | "The agent scores them — price, MOQ fit, lead time — and explains its pick." |
| 13 | Hand-off (only if a quote breaks a guardrail) | *Your call* with the numbers | "It stops. It explains, with the numbers: approve anyway, negotiate, or switch. Nothing reaches Shopify until I decide." Negotiating drafts a counter-offer in the mill's language at a computed target price, sent through Evolus; the revised quote is another real document. |
| 14 | **Pause: pre-orders** | The QR code; the tour waits: *"Waiting for a real pre-order — scan the QR code"* | "This is a real Shopify pre-order. Scan the code, pay with the test card. For the stage, the PO unlocks at five pre-orders; the production plan is on screen." |
| 15 | Purchase order | *Production unlocked*, PO-000NN sent via the Evolus workflow | "Demand is validated, and the purchase order — numbered from our own sequence — goes to the mill through Evolus." |
| 16 | Forecast | How many to make, with the maths and its assumptions | "And how many to make: the maths is shown, and the assumptions are labelled and editable — fitted to our own past launches." |
| 17 | Inference | The Inference panel | "Every model call is measured: model, GPU, tokens per second." |
| 18 | Tech pack PDF | *Download PDF* | "And the factory gets the tech pack PDF. From a mood board to a purchase order, and the agent knew when to hand the call to a person." |

**Close:** "The creative director keeps the taste and the agents do the rest. Thank you."

## Rehearsal: the live pre-order moment

The strongest beat: the room pre-orders, the gauge crosses the threshold, and the purchase order leaves through Evolus.

- [ ] `DEMAND_STAGE_THRESHOLD=5` in `backend/.env` (restart the backend after changing it). Five people, one order each.
- [ ] The Shopify store currency is EUR and the payment provider is the **Bogus** test gateway. Test card: number
      **1**, any future expiry, any CVV, any name. Say "test payment" on stage.
- [ ] The QR panel shows the **store password** (Shopify dev stores keep a password page). Read it out, or put it
      on the slide behind you.
- [ ] Rehearse with two phones: scan, enter the password, pick a size, pay with card 1. The order count on screen
      updates within a few seconds (Shopify polling, `SHOPIFY_POLL_INTERVAL`); the size chart fills by size.
- [ ] At five orders: *Production unlocked*, and the purchase order goes to the mill's address through the Evolus PO
      workflow - check that it arrives in the demo inbox.
- [ ] Phones on the venue Wi-Fi or mobile data: if the venue blocks the store, use mobile data.
- [ ] Ask the five volunteers before the pitch starts, and have them ready with the QR code page open.

## Fallback

**Record a video of a full live run** at the rehearsal (screen + voice, or screen only and narrate live) and keep it
on the laptop and on a USB stick. If the network, a GPU box, Evolus or Shopify fails on stage, switch to the video
and say "this is a recording of a live run from earlier today". Do not switch to the test doubles: they are canned
and the app labels them "FAKE UPSTREAM — not real".

## If something goes wrong

- **A step shows not connected / unreachable:** say which service; if you can fix it (tunnel, key), fix it and press
  **Retry** on the step — the run resumes there. Otherwise switch to the video.
- **The tour waits for quotes:** that's by design. Drop the PDFs, or click *Stop waiting & recommend* once one is in.
- **No hand-off appears:** the pick passed every guardrail. Say so and carry on.
- **The PO shows draft — not sent:** Evolus is not connected; say it, connect it, and press **Send PO**.
- **You lose your place:** Space pauses. Esc hands you the controls; every button still works by hand.
