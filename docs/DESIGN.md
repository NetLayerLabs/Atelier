# Atelier design system — "Scenar fidelity, made for fashion"

Atelier is a creative director's studio that runs a supply chain. Its interface deliberately belongs to the same
design family as **Scenar** (the team's earlier app, tryscenar.xyz): pure white, near-black ink, Inter, pill
controls, soft white cards, generous whitespace and very little text — with colour used **only** for meaning.
What makes it Atelier is the subject, not a different palette: the instruments read margin, cost and demand, the
chat is a creative director briefing a studio, and one quiet seam marks where the work changes hands.

- **Code:** `frontend/src/components/ds/*` (import from `@/components/ds`)
- **Tokens:** `frontend/src/app/globals.css`
- **Showcase:** `/design` — **dev only** (`pnpm dev`; it 404s in a production build and nothing links to it,
  because it renders primitives with illustrative values)
- **Scenar reference:** the Scenar repo's `src/app/globals.css`, `HeroVisual`, `TensionMeter`, `NavMenu`,
  `LaunchButton` (read-only). Never copy Scenar's logo, name or wordmark — only its visual language.

---

## 1. Principles

1. **Monochrome; colour means something.** White page, ink type, black pills. Green / amber / red appear only for
   state (connected, needs you, breach/fake) and as the **tension gradient** (green → amber → red) on instruments
   that judge a number against a limit. There is no brand hue: the `accent` role is ink.
2. **One giant instrument, then calm cards.** The first screen is a single thin-line gauge spanning the viewport;
   everything after it is white cards with a soft border, one idea each.
3. **Honest by construction.** No mocked data anywhere. Every primitive has an empty/unknown state (`value={null}`
   → "—", `NotConnected`, `Badge status="unknown"`). Illustrations say so ("Illustration — the gauge is a scale,
   not a reading"). A fake upstream is always loud (`Badge status="fake"`).
4. **The human's call is the loudest thing on screen.** Approve, send, overrule: the black `inverse` card with one
   white pill, or the primary ink pill. Everything the agent did reads quieter.
5. **Light and sparse.** Inter 300 display with -0.03em tracking, lots of air, 24px card radii, hairlines at 8%
   black, pill controls, sentence-case labels. Mono (Geist Mono) only for measured values and codes.
6. **Calm motion.** Things rise 20px and fade in on Scenar's curve `cubic-bezier(0.16, 1, 0.3, 1)`. Only needles
   use a spring. Everything respects `prefers-reduced-motion`.
7. **Projector and phone.** Light is the default; dark is the clean inverse (near-black page, white ink) for the
   projector. Root size is 17px (18px from 1280px). Nothing scrolls sideways at 390px.

---

## 2. Scenar → Atelier

| Scenar | Atelier (same language, made for fashion) |
|---|---|
| `#ffffff` page, `#0a0a0a` ink, `#f4f4f6` grey pills/wells, lines `rgba(0,0,0,.08/.12/.35)` | identical tokens (`--paper`, `--fg`, `--paper-2`, `--line*`) |
| Inter 300–600, display 300 / -0.03em, Geist Mono | identical; the Fraunces serif and indigo accent are gone |
| Colour only for meaning + the tension gradient | identical; the gradient reads **margin vs floor** and guardrails |
| Hero: giant semicircle tension gauge, floating speech pills | Hero: the same thin-line gauge, ticked like a tailor's tape (80 divisions), with a creative director (black bubble) and a mill (grey bubble) negotiating around it; labelled as an illustration |
| "● eyebrow", huge light headline, black "Launch app ↗" + outlined pill, tag chips | "● AI agent for fashion brands · AMD Developer Hackathon ACT III", "Make only what's already sold.", black "Launch studio ↗" + outlined "Take the tour", topic chips |
| Header: logo + wordmark, black "+ Menu" pill · Sandbox \| ● Live toggle · black "Launch app ↗" · account pill | Header: Atelier mark + wordmark, black "+ Menu" pill · Studio \| ● Workspace toggle · black "Launch studio ↗" · **System · n/9** pill (opens services) · small round tour/theme buttons |
| Chat: grey bubbles for the counterpart, black for you | Grey bubbles for Atelier (with its mark), black for the creative director |
| TensionMeter, report ring, monochrome radar | `Dial`, `Ring`, `Radar` restyled to match; `TapeMeasure` is the gauge unrolled |
| — | The one fashion touch: a faint dashed **seam** (`Stitch`) where work passes between you and the agent, and the angled `GarmentTag` for named things (looks, SKUs, mills) |

---

## 3. Tokens

All colours are CSS variables in `globals.css`, mapped to Tailwind (`bg-paper`, `text-fg-muted`, …). Never
hard-code a hex in a component (SVG uses `C.*` from `tokens.ts`).

### Colour

| Token | Light | Dark | Role |
|---|---|---|---|
| `paper` | `#ffffff` | `#0a0a0a` | page |
| `paper-2` / `surface-muted` | `#f4f4f6` | `#1c1c1e` | grey pills, tracks, wells, Atelier's chat bubbles |
| `surface` | `#ffffff` | `#121212` | cards, popovers |
| `fg` | `#0a0a0a` | `#fafafa` | ink |
| `fg-muted` | `#5f5f63` (≈ ink @ .62; 6.4:1 on white, 5.8:1 on paper-2) | `#a8a8ad` | secondary text |
| `fg-faint` | `#6e6e73` (≈ ink @ .55; 5.1:1 / 4.6:1) | `#8e8e93` | meta, captions |
| `fg-dim` | ink @ .38 | white @ .38 | **decoration only** (gauge numbers) — never body text |
| `line` / `line-strong` / `line-bold` | black @ .08 / .12 / .35 | white @ .10 / .16 / .42 | hairlines, outlines |
| `inverse` / `on-inverse` / `inverse-hover` | `#0a0a0a` / `#fff` / `#262626` | `#fafafa` / `#0a0a0a` / `#e4e4e7` | primary pill, director bubble, decision card |
| `accent` (+ `-strong`, `-soft`, `on-accent`) | = ink (`soft` = ink @ .06) | = white | selected / current / focus. A role, not a hue |
| `ok` · `warn` · `bad` (+ `-soft`) | `#15803d` · `#b45309` · `#c42020` | `#4ade80` · `#fbbf24` · `#f87171` | state only |
| `tension-good` · `-mid` · `-bad`, `--tension-grad` | `#10b981` → `#f59e0b` (55%) → `#ef4444` | same | instruments judged against a limit |
| `tick` · `tick-faint` · `tick-major` | ink @ .24 · .12 · .50 | white @ .28 · .14 · .60 | instrument ticks |
| `veil` | white @ .78 | `#0a0a0a` @ .78 | the app bar's blurred veil (plain rgba on purpose) |

Muted inks are solid hex equivalents of Scenar's alpha inks so small text keeps AA on both white and `#f4f4f6`.

**Inverse surface (`.ds-inverse`, `Card variant="inverse"`).** The black card in light (white in dark). Inside it
every ink, line, surface and tick token is re-pointed, the **state colours become the opposite theme's**
(`--inv-ok/-warn/-bad` + `-soft`: the dark theme's greens/ambers/reds on the black card, the light theme's on the
white one) so badges, dials and alerts keep AA, `color-scheme` flips for native controls, and a **primary** button
becomes the white pill with black text — exactly Scenar's approve card. Use it for the human's decision only
(chapter III approve, the chapter IV hand-off, the closing CTA).

### Type
- **Inter** (next/font, self-hosted; 300/400/500/600) for everything. There is no serif and no italic emphasis;
  `font-serif`/`font-display` only survive as aliases that resolve to upright Inter (don't use them).
- Display: `text-display-xl` clamp(2.5rem, 5.6vw, 4.75rem) · `display-l` clamp(2rem, 4vw, 3.4rem) ·
  `display-m` clamp(1.6rem, 2.6vw, 2.35rem) — all weight 300, tracking -0.03em, line-height ≈ 1.
- UI: `title` 500 · `body-l` · `body` · `small` · `micro`. Button/pill labels are small (≈ 12–14px), weight 500.
- **Geist Mono** only for measured values, codes and model names (`font-mono`, `tabular`).
- `Em` inside a headline drops the words to muted ink (no italics, no colour).

### Radii
chip 8 · field 12 · panel 20 · card 24 · sheet 28 · pill (`rounded-full`) for every control.

### Elevation
`e1` `0 1px 2px rgba(0,0,0,.04)` · `e2` (cards) `+ 0 8px 24px -12px rgba(0,0,0,.12)` · `e3` (overlays, hover)
`0 2px 4px …, 0 24px 60px -24px rgba(0,0,0,.25)`.

### Motion
- Curve `ease-thread` = `cubic-bezier(0.16, 1, 0.3, 1)`; `ease-settle` = `cubic-bezier(0.34, 1.56, 0.64, 1)`.
- Entrances: rise 20px + fade, 0.8–1s (`.rise`, `RISE`, `Reveal`).
- Needles: `NEEDLE_SPRING` (stiffness 70, damping 13). The hero gauge drifts on a 26s loop and pauses off-screen.
- Pills: hover lifts 1px, press scales to .97; arrow badges rotate 45°.
- Reduced motion: entrances and needles jump to their final state; the hero shows two static bubbles.

### Textures
- None on surfaces: the page is pure white (or near-black). The earlier cutting-mat grid, paper grain and the
  legacy colour aliases (`ivory`, `champagne`, `ink*`, `.eyebrow`) have been removed from `globals.css`.
- `ds-stitch`: a faint 4/4 dashed seam at 35% — the single fashion touch; use it only where work changes hands.

---

## 4. Components (`@/components/ds`)

Every component is typed, theme-aware and documented with JSDoc in its file.

| Component | File | Use | Don't |
|---|---|---|---|
| `Button` (`primary` · `secondary` · `ghost` · `accent` · `danger`; `sm`/`md`/`lg`; `icon`, `trailing`, `trailingBadge`, `loading`) | `Button.tsx` | primary = Scenar's black pill (white inside `.ds-inverse`); secondary = outlined pill; ghost for Cancel/More; `accent` is the same ink pill kept as a role for the human's decisive step; `trailing={<IconArrowUpRight/>}` for "Launch ↗", `trailingBadge` for the round white arrow badge | two primaries side by side; uppercase labels |
| `LinkButton`, `buttonClass()` | `Button.tsx` | navigation styled as a button | `<a>` styled by hand |
| `IconButton` (`solid`/`soft`/`outline`/`ghost`, `dot`, `dotLive`) | `Button.tsx` | round controls; always pass `label` | icon-only buttons without `label` |
| `Card` (`surface`/`muted`/`inverse`/`outline`; `pad`; `interactive`), `CardHeader` | `Card.tsx` | white, 8% border, soft `e2` shadow; `inverse` = the black decision card, one per screen | cards in cards in cards (use `muted` wells inside) |
| `Eyebrow` (`numeral`, `tone`, `live`), `StatusDot`, `Label`, `SectionHeading` (`xl`/`l`/`m`), `Em` | `Eyebrow.tsx` | Scenar's "● label" (ink dot, muted text) starts every section/card; `numeral` → "● I · Trend ingestion"; `Label` = small muted sentence-case label; `Em` = muted words in a headline | uppercase tracked eyebrows (legacy `.eyebrow`), serif/italic emphasis |
| `Chip`, `ChipButton` (`selected`, `onRemove`) | `Chip.tsx` | Scenar's tag pill (outline) or grey pill (`soft`); selected = ink | statuses (use Badge) |
| `GarmentTag` (`code`, `tone` default/ink) | `Chip.tsx` | the sparing fashion touch for named things: look names, SKUs, sizes, the chosen mill | long text (truncates); decoration |
| `Badge` (`status`: connected, not-connected, unreachable, unverified, fake, measured, sent, received, draft, pending, running, approved, rejected, failed, unknown) | `Chip.tsx` | every state label in the app: one vocabulary | ad-hoc coloured spans |
| `Swatch` (`xs`–`lg`, `name`, `code`), `SwatchStrip` (weights) | `Swatch.tsx` | trend palettes, BOM colourways, brand-book colours | UI decoration |
| `Stat`, `StatGroup`, `CountUp` | `Stat.tsx` | big light numerals with a label; `value="—"` + `caption` when unknown | invented placeholder numbers |
| `Field`, `Input` (`prefix`/`suffix`), `Textarea`, `Select`, `FileDrop` (`layout` stack/row, `aria-label` for the file input, `zoneLabel`, `busy`) | `Field.tsx` | all forms; currency via `prefix={currencySymbol(c)}`; every upload is a `FileDrop` (the quote upload is the `row` layout with `aria-label="Upload supplier quote"`) | inputs without a Field label; hand-made drop zones |
| `Tabs` (`count`, `content`), `Segmented` | `Tabs.tsx` | Tabs switch panels in a card; Segmented switches views (2–4 options) | Segmented for navigation between pages |
| `Disclosure` (`leading`, `meta`, `variant` card/row) | `Disclosure.tsx` | RFQ emails, evidence, "why this number?"; root takes `data-demo`, first child is the toggle button | nesting disclosures |
| `InlineAlert` (`info`/`ok`/`warn`/`bad`, `hint`, `action`), `SetupHint` | `Alert.tsx` | service errors with the backend's setup hint; guardrail breaches | toasts for errors that need action |
| `toast()`, `ToastViewport` (mounted in layout) | `Toast.tsx` | transient confirmations ("Tech pack saved") | anything the user must act on |
| `EmptyState`, `NotConnected` (`service`, `hint`, `onRetry`) | `EmptyState.tsx` | nothing yet / service not configured | fake previews |
| `Skeleton`, `SkeletonText` | `Skeleton.tsx` | loading shapes; pair long waits with a sentence ("Gemma is reading the board…") | spinners on large areas |
| `Modal`, `Sheet` (`side` right/bottom; `ariaLabel`, `eyebrow`, `title`, `footer`, `headerActions`) | `Modal.tsx` | confirmations, sign-in (Modal); evidence, telemetry (Sheet). Portaled, focus-trapped, Esc closes | custom fixed overlays |
| `Table`, `THead`, `TBody`, `Tr` (`selected`, `muted`), `Th`/`Td` (`numeric`) | `Table.tsx` | BOM, measurements, quotes, sales lines. Heads are small muted sentence case (like `Label`); numbers mono, right-aligned. The wrapper is `relative` + `overflow-x-auto`, so `sr-only` cells never widen the page | wide tables without the wrapper; uppercase heads |
| `Timeline` (status per step: done/running/waiting/error/pending/skipped), `Stepper` (`reachable` reached/all, `variant` plain/well, per-step `marker` + `srStatus`), `StepNode` | `Timeline.tsx` | the pipeline (Timeline); chapter progress (Stepper, linear: only reached steps are clickable); workspace sections (`reachable="all"`, `variant="well"`). The current step scrolls into view on phones | |
| `Stitch` (`label`) | `Divider.tsx` | the faint seam where work passes between you and the agent ("You → agent") | every divider (use hairlines) |
| `ThemeToggle`, `ThemeSegmented`, `useTheme`, `setThemePreference` | `ThemeToggle.tsx`, `theme.ts` | theme switching | reading `localStorage` yourself |
| `AtelierMark`, `Wordmark` | `Logo.tsx` | header, favicon-sized marks (≥ 20px) | recolouring or rotating the mark |
| Icons (`IconPlus`, `IconNeedle`, `IconRuler`, `IconTag`, `IconSwatch`, `IconSpool`, `IconHanger`, …) | `icons.tsx` | 24 grid, 1.75 stroke, currentColor; 14–20px | mixing in another icon set |

### Instruments

| Instrument | File | Use for | Key props |
|---|---|---|---|
| **TapeMeasure** (monochrome, thin ticks, ink pointer with a dot) | `instruments/TapeMeasure.tsx` | one quantity on a scale: landed unit cost vs target band, pre-orders vs MOQ, lead time vs launch | `min`, `max`, `value` (null = no reading), `target {from,to,label}`, `markers [{value,label,tone}]`, `format`, `tone` |
| **Dial** (Scenar's TensionMeter) | `instruments/Dial.tsx` | a ratio judged against a floor: margin vs guardrail floor, sell-through vs plan. Thin ticks, light numbers, needle with a dot, a thick arc in the tension gradient (red below the floor → amber at it → green with 20% headroom) and an "Above / Below floor" pill | `value`, `floor {value,label}`, `zones`, `tone` (solid override), `format`, `caption`, `size` |
| **Ring** (Scenar's report ring: grey track, thick ink arc, big light numeral) | `instruments/Ring.tsx` | 0–1 confidence/completeness: forecast confidence, workspace readiness, voice coverage | `value` (null = unknown), `display`, `caption`, `tone`, `size` |
| **Radar** (monochrome: grey rings/spokes, ink outline over a light fill) | `instruments/Radar.tsx` | 3–8 themes: customer-voice fit radar, trend attributes; comparison series dashed | `axes` (≤ 12 chars), `series [{name, values, dashed}]`, `max`, `format` |
| **FanChart** | `instruments/Charts.tsx` | explained forecast: observed (ink) + median (ink) + grey bands + MOQ threshold | `points [{x,p50,lo,hi,lo2,hi2,actual}]`, `threshold` |
| **Sparkline** | `instruments/Charts.tsx` | small trends: orders per day, mentions per week | `values`, `tone`, `area` |
| **ProgressBar** | `instruments/ProgressBar.tsx` | progress to a target; `stitch` = planned; no `value` = working | `value`, `label`, `detail`, `tone` |

Instrument rules: colour (the tension gradient or ok/bad) appears only on the reading (arc behind the needle,
pointer); the scale stays ink. Always state the limit (floor, MOQ, target) in words next to it. All instruments expose
`role="meter"`/`img` with a text value for screen readers. Server and client render the same first frame: the
motion `initial` never depends on the reduced-motion preference (only known in the browser); under reduced motion
the reading settles with the zero-length `INSTANT` transition instead.

---

## 5. Header & Menu (implemented)

`components/Header.tsx`, `components/Menu.tsx`. Sticky, 4.5rem tall, full-width (16px / 32px gutters like Scenar),
over a blurred white veil (`--veil`) that fades out downward. The landing hero slides up underneath it.

- **Left:** the Atelier mark + "Atelier" wordmark (Inter semibold; back to start; wordmark from md) · the black
  **"+ Menu"** pill with a round white plus (turns 45° when open).
- **Right:** the credit line (`PoweredBy`, 2xl only) · *Start over* (ghost, xl+, once there is progress) · on lg+, a
  small segmented **Studio | ● Workspace** toggle (grey well, ink thumb where you are; the dot is amber while the
  workspace still needs something, green when ready) · the black **"Launch studio ↗"** pill with a round white
  arrow badge (scrolls to chapter I on `/`, navigates there elsewhere; icon-only below md) · **Inference** (only once
  a real call exists) · the **System · n/9** pill (grey pill, black circle with a status dot; opens the services
  popover; `data-demo="system-pill"`) · small round **Tour** and **Theme** buttons (sm+; both also in the Menu).
- **Menu sheet** (dropdown card on desktop, near-full-width card on mobile): Studio chapters I–IV (unreached
  chapters disabled), Overview (landing sections 01–06), Brand workspace (readiness), Tools (Guided tour with
  Shift D, Inference stats, System status with badge, Sign in when the backend requires a token, Start over), and a
  footer with Light/Dark/System and the credit line.
- Shared state: `lib/ui.ts` (`menuOpen`, `inferenceOpen`, `healthOpen`) so the Menu can open the Inference sheet
  and the System popover. The Inference sheet keeps `aria-label="Inference statistics"` (the tour's Esc logic
  looks for it). The first `<header>` in the DOM is still the app bar (the tour's caption placement reads it).

---

## 6. Page-by-page direction

Each page keeps every `id` and `data-demo` attribute exactly (see §8).

### Landing (`components/landing/*`)
- **Hero (`Hero.tsx` + `HeroGauge.tsx`):** full-bleed first screen. A giant semicircle gauge spans the viewport
  (thin ticks — 80 divisions like a tape, majors every quarter — light scale numbers 0/25/50/75/100, a needle that
  fades towards the hub with a dot at its tip, and a tension-gradient arc up to the needle). Fragments of a
  negotiation float around it: the creative director in black bubbles ("Make it darker, cropped, more Margiela."),
  a mill in grey ("Our price is €58 a unit…"). It is decorative (`aria-hidden`) and captioned "Illustration — the
  gauge is a scale, not a reading". At the foot: "● AI agent for fashion brands · AMD Developer Hackathon ACT III",
  the headline "Make only what's already sold.", black "Launch studio ↗" (`data-demo="enter-studio"`) + outlined
  "Take the tour", and the topic chips (Customer voice · Creative direction · Supplier quotes · Pre-orders ·
  Forecast).
- **What it does:** one light paragraph (second half muted) beside the live **StatusStrip** card (badges from
  /api/health), then the "on this page" pills.
- **Problem / How it works / Agents / Human + AI / Architecture / Value:** Scenar's rhythm — "● 01 · Kicker"
  eyebrow, a light display title with an `Em` half, a muted lede, then white cards. Cited figures keep their
  sources; connection states stay live badges. The orchestrator node is the black card.
- **Closing CTA:** a black `ds-inverse` sheet with the white "Launch studio" pill and an outlined "Take the tour".

### Studio chapter I — the signal (TrendStage, CustomerVoice, TrendAnalysisView)
- Chapter header via `Chapter` (already uses `SectionHeading` + `Eyebrow numeral`).
- **Mood boards:** source switch = `Tabs` (Mood boards / Upload / Image URLs). Boards are interactive Cards
  (`rounded-card`, image grid inside with 8px gaps and `rounded-panel` images); meta with `Label`
  ("Board 01 · 4 photos"), title `text-title`, credit `text-micro` underlined. Keep `data-demo="preset-*"`.
  Upload = `FileDrop`; URLs = `Textarea` in a Field.
- **Analysing:** keep the scanline over the images; add `ProgressBar value={null}` and a sentence of what the
  model is doing; `Skeleton` for the result layout.
- **Trend analysis:** hero card with the trend name (`display-m`) + `GarmentTag`s for silhouettes; palette as
  `SwatchStrip` + `Swatch` cards (real hexes); fabrics as `Chip`s; viability as a **Ring** (if the backend gives a
  score) with the reasoning beside it; `RouteBadge`/`RouteTag` for provenance.
- **Customer voice:** inputs (`Textarea`, sample `ChipButton`s with `data-demo="voice-sample-*"`), the result as a
  **Radar** of themes (only themes the backend returned) + quote cards with `Citations`. Apply button =
  `accent` (`data-demo="voice-apply"`). Not configured → `NotConnected`.
- Actions row: `Generate four concepts` (primary, `data-demo="generate"`), `Compose a collection` (secondary),
  `Read a different trend` (ghost).

### Chapter II — concepts / collection (Designs, Collection)
- `Segmented` to switch Four concepts / Collection when both exist.
- Concept cards: image `aspect-[3/4] rounded-panel`, `GarmentTag` "Look A–D", prompt in a `Disclosure`, seed in
  mono. Selected = ink ring + black "Selected" pill. Loading = `Skeleton` in the image's aspect.
- Collection: a lookbook grid with a `SwatchStrip` header for the shared palette.

### Chapter III — vibe check / direction / approve (VibeStage, Direction)
- Two-column: the selected look (large image card) | the direction composer: `Textarea` with mic `IconButton`,
  sent with primary `Direct it` (`data-demo="direct-submit"`), wrapper `data-demo="direction"`.
- **The conversation** is Scenar's chat: Atelier's turns are grey bubbles beside its mark in a black circle; the
  director's briefs are black bubbles on the right.
- **"Atelier heard"** (`data-demo="heard"`): a white card with a soft border on Atelier's side, a `Stitch label="You → agent"`
  on top; parsed changes as rows (prompt additions as black pills, removals struck through, palette as Swatches,
  silhouette, tech-pack notes).
- Variations: 4 cards like chapter II.
- **Approve** (`data-demo="approve"`, button `data-demo="approve-button"`): the black `inverse` card, the decision
  moment: `display-m` question, the look's GarmentTag, and one white pill "Approve for production" (a `primary`
  Button — `.ds-inverse` turns it white). `WorkspaceGate`
  (`data-demo="workspace-gate"`) becomes an `InlineAlert tone="warn"` with a LinkButton to the workspace.

### Chapter IV — production (PipelineStage and children)
- **Pipeline timeline:** `Timeline` with one item per agent step; meta = duration + `RouteTag`; `StepTelemetry`
  under each. Running step = ink node with a breathing ring; waiting on the human = amber.
- **Tech pack + editor** (`data-demo="techpack"`, PDF link `data-demo="pdf"`): Card with `Tabs`
  (BOM / Measurements / Construction / Costing). BOM and measurements as `Table` (`numeric` cells, mono);
  BOM colours as `Swatch xs`; edits use `Input` inside cells; costing as a **TapeMeasure** of unit cost vs the
  brand's target band. Save = primary + `toast`.
- **RFQs / emails** (`data-demo="outreach"`, each `data-demo="rfq-<lang>"`, toggle `data-demo="show-english"`):
  `Disclosure` per mill (leading = flag/IconMail, meta = `Badge status="sent"|"draft"|"unknown"`); body in a
  `muted` well, monospace headers; "Show English" as a ghost button.
- **Quotes panel** (`data-demo="quotes"`, upload `data-demo="quote-upload"`, breach `data-demo="guardrail-breach"`,
  audit `data-demo="audit"`): `Table` of quotes (selected row = chosen supplier with an accent `GarmentTag`);
  each quote's landed cost on a **TapeMeasure** against target/ceiling; unverified numbers `Badge unverified`;
  unmatched quotes in an `InlineAlert warn`; upload = `FileDrop`; empty = `EmptyState` "No replies yet".
- **Hand-off DecisionPanel** (`data-demo="decision"`, `decision-negotiate`, `counter-offer`, `counter-local`,
  `counter-math`, `counter-send`): the `inverse` Card. Left: what broke (InlineAlert bad + **Dial** margin vs
  floor). Right: the options as large radio Cards; the counter-offer math in a mono `Table`; `Send counter`
  = accent. A `Stitch label="Agent → you"` at the top.
- **Shopify / demand tracker** (`data-demo="storefront"`, `data-demo="demand"`, QR `data-demo="preorder-qr"`):
  storefront card with product image + `Badge`; demand: **TapeMeasure** pre-orders vs MOQ, `Sparkline` per day,
  `StatGroup` (orders, units, revenue in brand currency). QR on a white tile (keep it white in dark mode for
  scanning). Store not connected → `NotConnected service="Shopify dev store"`.
- **Forecast panel:** **FanChart** (observed + median + bands + MOQ), **Ring** for confidence, and "why" as a
  list of drivers in `Disclosure`s ("Why this number?"). No forecast without evidence: EmptyState.
- **PO card** (`data-demo="po"`): a document-like Card (`rounded-card`, mono line items `Table`, total as Stat,
  GarmentTag for the PO number, `Badge` for state). Place PO = accent.

Implemented: reference screens `docs/design/production-*.png`. The hand-off card is a `.ds-inverse` surface (its
state colours are remapped, see §3), so the amber eyebrow, the red breach values and the Dial's tension arc keep
their contrast on black (light) and white (dark). Each step's measured calls render with `StepTelemetry` (tags on
their own line on phones, beside the numbers from `sm`). Quotes render as stacked cards below `md`; the quote
upload is the ds `FileDrop` (`layout="row"`).

### Brand workspace (`/workspace`, BrandWorkspace + steps)
- Page header: `SectionHeading size="l"` with brand name; a **Ring** of readiness (sections done / 6) with
  "Still needed: …" text.
- Steps I–VI as a `Stepper` (horizontal scroll on mobile), each step a Card with Fields. Suppliers and price list
  as `Table`s; imports via `FileDrop` (ImportPanel); guardrails as Inputs with units + a live **Dial** preview of
  the margin floor; brand-book colours as `Swatch`es; sales history import → `Sparkline`.
- Implemented: `docs/design/workspace-*.png`. The step row is the ds `Stepper` with `reachable="all"` and
  `variant="well"`: every section stays reachable and shows done (green check) / required-missing (amber dot) /
  optional, with the current section's status line underneath.

### Inference panel (implemented)
`Sheet` with Eyebrow, the GPU label as title (or "Measured calls" when none is claimed), service cards with
`Stat` + key/value rows, recent calls with `RouteTag` + `TruthTag`. FAKE calls → `InlineAlert bad`.

### AdminLogin (implemented)
`Modal` with Eyebrow "Admin token", `Field` + password `Input`, ghost "Not now" + primary "Sign in" with
`IconKey`. Opens on load when required, or on a 401 (and from Menu → Sign in).

### Error / not-connected states
- A step whose service is not configured: `NotConnected` with the service name, the backend's hint verbatim and
  Retry. Never a preview.
- A failed call: `InlineAlert tone="bad"` (legacy `ErrorNotice` already renders this) with `hint` and Retry.
- Backend down: `BackendBanner` (bad-soft band under the header). FAKE upstream: the bordered red `Badge` and banner.
- Unknown values: "—" plus a caption saying why ("Store not connected").

### Tour overlay (DemoController; restyled)
- Status box: bottom-left white card, Inter, ink beat dots.
- Caption: centred white card, Inter light, avoids controls (logic unchanged).
- Spotlight: a 2px ink `rounded-panel` ring with a soft halo.

---

## 7. Accessibility

- Text pairs meet WCAG AA in both themes (values above). Don't put `fg-faint` on `paper-2` for body text.
- Focus: 2px ink outline (`:focus-visible`), inputs add a 4px ink-6% ring.
- Never use `fg-dim` for text; gauge numbers that use it are decorative and `aria-hidden`.
- Touch targets ≥ 40px (buttons `md` are 44px). Icon-only controls must have `label`.
- Instruments expose `role="meter"` with `aria-valuetext`; charts expose a text summary.
- Dialogs trap focus, close on Esc, restore focus. Menu closes on Esc and returns focus to the pill.
- Reduced motion: all entrances and needles jump to their final state.

---

## 8. Rules for page agents

1. Import from `@/components/ds`. The legacy classes (`ivory*`, `champagne`, `ink*`, `.eyebrow`, `ds-mat`,
   `.grain`) no longer exist; don't use `font-display`/`font-serif`, italic emphasis or uppercase tracked labels
   (labels are `Label`/`Eyebrow`, sentence case). Colour is for meaning only: don't reach for `accent` to
   decorate — it is ink.
2. **Keep every `id` and `data-demo` attribute** on an element with the same role (the guided tour clicks and
   spotlights them; `data-demo="rfq-*"` must keep its toggle `<button aria-expanded>` as its first child —
   `Disclosure` does this). Keep `section[data-chapter]` ids `chapter-trend|ideation|vibe|production` and landing ids.
3. No new colours, radii or shadows. If something is missing, add a token in `globals.css` and document it here.
4. No mocked data, sample numbers or placeholder images. Unknown = "—" + reason, or `NotConnected`.
5. Mobile first: test at 390px; tables go in `<Table>`; long rows wrap; never `w-[…px]` wider than 358px.
6. Use `money()`/`currencySymbol()` from `Sheet.tsx` for amounts; never assume "$".
