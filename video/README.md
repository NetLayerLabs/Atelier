# Atelier demo film

A 2:55 film of Atelier's live run, built in code with [Remotion](https://www.remotion.dev/) (React). The app's build
never sees this folder; outputs, footage and audio are git-ignored.

## What is real

- **Footage:** a screencast of the hosted site, https://atelier.netlayerlabs.com, recorded on 17 Oct 2026 while the
  app's own guided tour (`?demo=1`) ran against the real services: Gemma-4-31B-IT on AMD GPUs through AMD Token
  Factory, the Evolus agent, document extractor and email workflows, and the Shopify development store.
  `scripts/capture-live.mjs` did only what the tour leaves to a person: press Approve, upload the supplier quotes,
  press Send on the counter-offer, and place a Shopify test-gateway order.
- **Numbers:** taken from that run (`scripts/rundata.mjs` writes them to `src/data.json`): the EUR 320 quote against
  the EUR 310 shop price, the EUR 124 target, the EUR 119 revised quote and PO-00001 (300 × EUR 119). The 1 min 54 s
  figure is from the first live run that day. The industry figures are cited on screen and sourced in the main README.
- **Emails:** cropped rows of the team inbox for that run (RFQs in Italian and English, the counter-offer, the
  purchase order). No address or personal name is shown.
- **Voice and sound:** narration (ElevenLabs voice "Lily"), the agent's line (voice "Daniel", the app's real hand-off
  message, labelled on screen), music and sound effects are generated with ElevenLabs.
- **Demo conditions, stated in the film:** model waits are shortened; the supplier quotes are test documents the team
  wrote; the suppliers route to the team's own inbox; the order used Shopify's test gateway; a demo threshold of 5
  pre-orders unlocks the purchase order.

## Build it

```bash
npm install
ELEVENLABS_KEY_FILE=/path/to/.env npm run vo      # narration + word timings (the key is read from the file, never printed)
npm run music && npm run sfx                       # score and sound effects
npm run timing                                     # src/timing.json
ATELIER_TOKEN=... INBOX_EMAIL=... PLAYWRIGHT_MODULE=... FILM=1 node scripts/capture-live.mjs   # records into .cache
ATELIER_TOKEN=... node scripts/rundata.mjs && npm run encode
npm run render                                     # out/atelier-demo-1080p.mp4
npm run finish                                     # out/atelier-demo.mp4 at -14 LUFS
```

`npm run render4k` renders the 4K master; `npm run studio` previews it.
