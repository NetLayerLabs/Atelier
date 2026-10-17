import type { CSSProperties } from "react";
import { cx } from "./ds";

/*
 * The partner logos: the companies' own artwork in public/brand/partners/, used as CSS masks painted in
 * currentColor (as ds/Logo.tsx does with the Atelier logo), so they follow the theme: ink on light, white on dark,
 * inverted inside .ds-inverse. Every file is single-colour with its geometry untouched, and comes from:
 *   amd.svg     https://www.amd.com/content/dam/code/images/header/amd-header-logo.svg (the amd.com site header)
 *   evolus.png  https://evolus.ai/images/evolus-logo-brand.png (Evolus AI, the logo evolus.ai declares;
 *               no vector of the full logo is published; the mascot's eyes are kept as holes)
 *   gemma.svg   https://storage.googleapis.com/gdm-deepmind-com-prod-public/media/images/footer_gemma__light_j46lu5D_ChuL4ZZ.max-24x24.svg
 *               (the Gemma sparkle in the site footers of deepmind.google/models/gemma/ and ai.google.dev/gemma;
 *               there is no official vector wordmark, so "Gemma 4" is always live text next to it, never the icon alone)
 * AMD's brand rules: black or white only (no grey, tint or opacity), at least 72 px wide on screen, and clear space
 * on every side equal to the white square in the arrow (0.447 x the logo's height). Partner-led layouts (this is
 * Atelier's page) separate the logos with a thin "|" rule: AMD's "x" multiplier is reserved for its own lockups.
 */

export type Partner = "amd" | "evolus" | "gemma";

type Art = {
  /** Accessible name. */
  name: string;
  src: string;
  /** Width / height of the artwork. */
  ratio: number;
  /** Height of the wordmark's baseline above the artwork's bottom edge, as a share of its height. */
  baseline: number;
};

export const PARTNER_ART: Record<Partner, Art> = {
  // viewBox 139.72 x 33.32; the letters sit on y = 31.11 and the arrow fills the full height.
  amd: { name: "AMD", src: "/brand/partners/amd.svg", ratio: 139.72 / 33.32, baseline: 2.21 / 33.32 },
  // 537 x 140 px; the wordmark's baseline is row 108, the mascot fills the full height.
  evolus: { name: "Evolus", src: "/brand/partners/evolus.png", ratio: 537 / 140, baseline: 32 / 140 },
  // 15 x 15, the sparkle with no text.
  gemma: { name: "Gemma 4", src: "/brand/partners/gemma.svg", ratio: 1, baseline: 0 },
};

/** AMD's minimum digital size is 72 px wide; this is the height that gives. */
export const AMD_MIN_HEIGHT = 72 / PARTNER_ART.amd.ratio;

/**
 * The logos in the small "Powered by ... · Orchestrated by ..." credit line (components/Header.tsx). AMD at its
 * minimum size; evolus a little taller, as its wordmark is lowercase (balanced by eye).
 */
export const CREDIT_LOGO_HEIGHT = { amd: AMD_MIN_HEIGHT, evolus: 19 } as const;

/**
 * One partner logo, `height` px tall (width from its aspect), painted in currentColor. It is an image named "AMD",
 * "Evolus" or "Gemma 4"; pass `decorative` when the name is already given as text next to it. `baseline` sits the
 * wordmark on the surrounding text's baseline, for a logo inside a line of text.
 */
export function PartnerLogo({
  partner,
  height,
  decorative,
  baseline,
  className,
}: {
  partner: Partner;
  height: number;
  decorative?: boolean;
  baseline?: boolean;
  className?: string;
}) {
  const art = PARTNER_ART[partner];
  const mask = `url(${art.src}) center / contain no-repeat`;
  return (
    <span
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : art.name}
      aria-hidden={decorative || undefined}
      className={cx(
        // Forced colours would repaint the background (and so the whole logo) in the page colour: use the text colour.
        "inline-block shrink-0 bg-current forced-color-adjust-none forced-colors:bg-[CanvasText]",
        className,
      )}
      style={{
        width: +(height * art.ratio).toFixed(2),
        height,
        mask,
        WebkitMask: mask,
        verticalAlign: baseline ? -+(art.baseline * height).toFixed(2) : undefined,
      }}
    />
  );
}

/**
 * Google lists product icons under "Ask first" (Brand Resource Center: approval through the Partner Marketing Hub),
 * and the Gemma terms (4.2) grant no right to its logos. Until Google approves, Gemma is credited in plain text only;
 * set this to true once it has, and the sparkle (public/brand/partners/gemma.svg) shows before "Gemma 4".
 */
const GEMMA_ICON_APPROVED = false;

/** The "built with" strip: the three technologies Atelier runs on, linked to their official pages. */
const STRIP: { partner: Partner; href: string; title: string }[] = [
  { partner: "amd", href: "https://www.amd.com/en/developer.html", title: "AMD Developer Program" },
  { partner: "gemma", href: "https://deepmind.google/models/gemma/gemma-4/", title: "Gemma 4, by Google DeepMind" },
  { partner: "evolus", href: "https://evolus.ai/en", title: "Evolus, the AI agent platform" },
];

/**
 * Sizes balanced by eye and by ink: AMD's capitals are heavy, so it is the shortest (its capitals about as tall as
 * the evolus wordmark's tallest letters); the evolus wordmark is lowercase beside a large mascot, so it stands
 * taller; the Gemma sparkle is as tall as "Gemma 4" with its ascenders. AMD at 18 px is 75.5 px wide, above its
 * 72 px minimum.
 */
const H = { amd: 18, evolus: 23, gemma: 19 } as const;

/**
 * AMD | Gemma 4 | evolus in a row, like an event's partner strip: single-colour logos in currentColor and a thin
 * faint rule between them. Each rule leads its logo and sits in the strip's clipped left margin, so a line that
 * wraps (narrow phones) never starts with one. `amd` is false until /api/health verifies the AMD hardware (as the
 * "Powered by" credit does), and AMD's licence covers its logo only on products that include an AMD processor.
 * `itemClassName` / `itemStyle` let a parent animate each logo.
 */
export function PartnerStrip({
  amd,
  className,
  itemClassName,
  itemStyle,
}: {
  amd: boolean;
  className?: string;
  itemClassName?: string;
  itemStyle?: (index: number) => CSSProperties | undefined;
}) {
  const items = amd ? STRIP : STRIP.filter((s) => s.partner !== "amd");
  return (
    // Clipped sideways only, with 4px of room for the links' focus rings; vertical overflow stays visible.
    <div className={cx("-mx-1 overflow-x-clip px-1", className)}>
      <ul className="-ml-(--sep) flex flex-wrap items-center gap-y-4 [--sep:30px] sm:[--sep:52px]">
        {items.map((s, i) => (
          <li key={s.partner} className={cx("flex items-center", itemClassName)} style={itemStyle?.(i)}>
            <span aria-hidden className="w-(--sep) shrink-0 select-none">
              <span className="mx-auto block h-5 w-px bg-fg-dim" />
            </span>
            <a
              href={s.href}
              target="_blank"
              rel="noreferrer"
              title={s.title}
              className="link-measure inline-flex items-center py-2 text-fg"
            >
              {s.partner === "gemma" ? (
                <span className="inline-flex items-center gap-2">
                  {GEMMA_ICON_APPROVED && <PartnerLogo partner="gemma" height={H.gemma} decorative />}
                  <span className="text-[1.125rem] leading-none font-medium tracking-[-0.01em]">Gemma 4</span>
                </span>
              ) : (
                <PartnerLogo partner={s.partner} height={H[s.partner]} />
              )}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
