# Changelog

What changed during the hackathon build (16–18 Oct 2026), with the commits. The README has the summary.

- **Demo film (17–18 Oct).** A 2:55 film of the live run, built in code in [`video/`](../video/) (Remotion): real
  footage of the hosted site, narration and music made with ElevenLabs, and real emails from the run's inbox (cropped,
  no addresses). Model waits are shortened and marked; the agent's line is the app's real hand-off message, voiced.
  What is real and how to rebuild it: [video/README.md](../video/README.md).
- **Outreach fix found while filming (17 Oct).** The email workflow reports a send as "handed to the Evolus mailer";
  the audit's new partly-failed-send check had read that as "not sent" and stopped every run at the RFQ step. Only
  "failed" or "not sent" with a reason now mark an RFQ as unsent. Caught on a rehearsal of the hosted site, fixed with
  a regression test and redeployed the same hour. (c4987fd)
- **Landing page motion (17 Oct).** One motion language from the brand's tailor's gauge: on load the gauge's needle
  swings to 12 o'clock and becomes the Atelier mark; each section opens with a hairline drawn and a tick dropped;
  seams sew where work changes hands; the agents' list carries a scroll-linked thread to the purchase-order
  threshold; the architecture diagram assembles along the request path, and a dot travels it each time the real
  `/api/health` answers (no timers); an xl-only tape rail reads your progress. Figures rise into place rather than
  counting up. Reduced motion is fully static, and every word is visible without JavaScript. (438b1e7)
- **Custom glyphs and official partner marks (17 Oct).** The stock ✓ ⚠ ✗ ✋ ↻ ★ in agent messages are drawn as
  Atelier's own glyphs (a stitched tick, a cross-stitch, a dressmaker's pin, an open hand, a loop of thread, a star),
  with accessible labels; verbatim customer quotes are left untouched. The credit and the footer use the official
  AMD, Gemma and Evolus marks, sourced from each company's own site, with trademark attribution. (a82aba1)

- **Live end-to-end run (17 Oct).** Mood board → sketch → customer voice → tech pack → bilingual RFQs → two
  guardrail hand-offs and a negotiation → Shopify pre-order → test order → PO-00001, on AMD Token Factory, Evolus and
  Shopify. Approve to both RFQs sent: 1 min 54 s. Details and conditions are [above](../README.md#what-works-end-to-end-today).
- **Hosted public demo (16–17 Oct).** https://atelier.netlayerlabs.com. Signed-out visitors can read a mood board,
  upload a sketch and have it read, direct it in plain words, and run customer voice on three public review samples;
  approving and everything after it need the admin token. The dashboard calls its API on the same origin, so one build
  serves any domain pointed at the server. It runs with Docker Compose on a shared server: both containers listen only
  on 127.0.0.1 behind nginx over HTTPS, with memory caps of 768 MB for the API and 384 MB for the dashboard. Last
  deployed on 17 October, after commit c4987fd. (95e0077, e8dab9d, 6637b5f)
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
  never beats a request that is still running ([how it works](../README.md#latency-on-a-shared-queue)). (5b3aafb)
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
- **Tests and a clean build (17 Oct).** All 396 backend tests pass (`uv run pytest -q`, 44 s). They run against
  local test doubles of every upstream service, which mark their responses as fake, so no live service is called. A
  fresh clone (commit 5b447ec) built and started with `docker compose up --build`; the API reported healthy and, with
  no `.env`, every service showed "not connected". Later commits were not rebuilt from a clean clone.
