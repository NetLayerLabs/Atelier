"use client";

import { useRef, type CSSProperties, type ReactNode } from "react";
import { useHealth } from "@/lib/health";
import { AtelierLockup, cx, Label } from "./ds";
import { PoweredBy } from "./Header";
import { REVEAL_RISE, STAGGER, useArm } from "./landing/primitives";
import { PartnerStrip } from "./PartnerLogos";

const REPO = "https://github.com/NetLayerLabs/Atelier";
const X_URL = "https://x.com/NetLayerLabs";

type FooterLink = { label: string; href: string };

/** In-page sections live on the studio home ("/"), so they work from /workspace too. */
const COLUMNS: { title: string; links: FooterLink[] }[] = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/#landing-how" },
      { label: "The agents", href: "/#landing-agents" },
      { label: "Human + AI direction", href: "/#landing-direction" },
      { label: "Architecture", href: "/#landing-stack" },
    ],
  },
  {
    title: "Powered by",
    links: [
      { label: "AMD GPUs (AMD AI Developer Program)", href: "https://www.amd.com/en/developer.html" },
      { label: "Gemma 4 by Google", href: "https://deepmind.google/models/gemma/" },
      { label: "Evolus", href: "https://evolus.ai" },
      { label: "Shopify", href: "https://www.shopify.com" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "GitHub", href: REPO },
      { label: "Docs", href: `${REPO}#readme` },
      { label: "Demo script", href: `${REPO}/blob/main/docs/DEMO_SCRIPT.md` },
      { label: "Image credits", href: `${REPO}/blob/main/backend/static/moodboards/ATTRIBUTION.md` },
    ],
  },
];

const external = (href: string) => /^https?:\/\//.test(href);

/*
 * Entrance, once, as the footer scrolls in. The footer also renders on /workspace (outside MotionConfig), so it is
 * CSS only: <footer> carries a stage reveal's data-reveal (useArm) and each block hides only while that says "armed",
 * so the server HTML, no-JS and reduced motion show the footer exactly as it is. The tape edge draws first, then the
 * lockup, blurb and social links rise, then the three columns (label first, then its links), then the "Built with"
 * strip (its logos one by one) and the legal line. Beats are ms after the footer is shown; the last block settles by
 * about 1.35 s.
 */
const BEAT = { lockup: 150, columns: 300, partners: 520, legal: 640 } as const;

/** When column `c` starts: 80 ms between columns. Its links follow its label 40 ms apart. */
const columnAt = (c: number) => BEAT.columns + c * STAGGER.sibling;

/** Rise 8px into place, held back by the block's --fd once shown. */
const RISE = cx(REVEAL_RISE, "in-data-[reveal=shown]:delay-(--fd)");

/** The legal line only fades: it carries a hairline, and a moving hairline reads as a layout shift. */
const FADE =
  "transition-opacity duration-700 ease-thread in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-(--fd)";

/** Start a block `ms` after the footer is shown. Children inherit it unless they set their own. */
const at = (ms: number) => ({ "--fd": `${ms}ms` }) as CSSProperties;

/** Footer links lift to ink, with the measured underline drawn under them on hover / focus. */
const LINK = "link-measure hover:text-fg focus-visible:text-fg";

/**
 * Site footer: the lockup, what Atelier does, X and GitHub, then Product / Powered by / Resources, a "Built with"
 * strip of the partner logos (AMD | Gemma 4 | evolus) and the legal line with the live credit and trademark notice. Same type as the
 * rest of the app (Inter: body text, and the small section labels the menu uses). Its top edge is ruled like a
 * tailor's tape; links lift to ink with a measured underline.
 */
export function SiteFooter() {
  const health = useHealth((s) => s.health);
  const credited = health.kind === "ok" && (health.data.poweredBy.amd || health.data.poweredBy.evolus);
  const ref = useRef<HTMLElement>(null);
  const reveal = useArm(ref);
  return (
    <footer ref={ref} id="site-footer" data-reveal={reveal} className="relative">
      <TapeEdge />
      <div className="mx-auto max-w-[1400px] px-4 pt-14 pb-10 sm:px-8 lg:px-12">
        <div className="grid grid-cols-2 gap-x-8 gap-y-12 md:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]">
          {/* The lockup has no style prop: it inherits this column's --fd. */}
          <div className="col-span-2 flex max-w-md flex-col gap-6 md:col-span-1" style={at(BEAT.lockup)}>
            <AtelierLockup height={26} className={cx("text-fg", RISE)} title="Atelier" />
            <p className={cx("text-body text-pretty text-fg-muted", RISE)} style={at(BEAT.lockup + STAGGER.sibling)}>
              An AI agent for fashion brands. It reads the trend, takes the designer&rsquo;s own sketch, writes the tech
              pack, briefs suppliers in their own language and opens a real Shopify pre-order. Production starts only
              once real customers have paid.
            </p>
            <div className={cx("flex items-center gap-2", RISE)} style={at(BEAT.lockup + 2 * STAGGER.sibling)}>
              <Social href={X_URL} label="NetLayerLabs on X">
                <XMark />
              </Social>
              <Social href={REPO} label="Atelier on GitHub">
                <GitHubMark />
              </Social>
            </div>
          </div>
          {COLUMNS.map((col, c) => (
            <nav key={col.title} aria-label={col.title} className="flex flex-col gap-2" style={at(columnAt(c))}>
              <Label as="p" className={RISE}>
                {col.title}
              </Label>
              <ul className="flex flex-col gap-1">
                {col.links.map((l, i) => (
                  // The rise sits on the <li>, so its delay never slows the link's own hover transition.
                  <li key={l.label} className={RISE} style={at(columnAt(c) + (i + 1) * STAGGER.chip)}>
                    <a
                      href={l.href}
                      {...(external(l.href) ? { target: "_blank", rel: "noreferrer" } : {})}
                      className={cx("text-body text-fg-muted", LINK)}
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        {/* What Atelier runs on, as an event's partner strip: the logos in ink with a thin rule between them. */}
        <nav
          aria-label="Built with"
          className={cx("mt-14 flex flex-col gap-3 border-t border-line pt-7 pb-1 sm:flex-row sm:items-center sm:gap-12", FADE)}
          style={at(BEAT.partners)}
        >
          <Label as="p" className={RISE}>
            Built with
          </Label>
          <PartnerStrip
            amd={health.kind === "ok" && health.data.poweredBy.amd}
            itemClassName={RISE}
            itemStyle={(i) => at(BEAT.partners + (i + 1) * STAGGER.chip)}
          />
        </nav>
        <div
          className={cx(
            "mt-7 flex flex-col gap-3 border-t border-line pt-6 text-micro text-fg-faint sm:flex-row sm:items-center sm:justify-between",
            FADE,
          )}
          style={at(BEAT.legal)}
        >
          <p>
            © 2026 NetLayerLabs ·{" "}
            <a href={`${REPO}/blob/main/LICENSE`} target="_blank" rel="noreferrer" className={LINK}>
              MIT licence
            </a>{" "}
            ·{" "}
            <a
              href="https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii"
              target="_blank"
              rel="noreferrer"
              className={LINK}
            >
              AMD Developer Hackathon ACT III
            </a>
            <span className="mt-1 block">
              AMD and the AMD Arrow logo are trademarks of Advanced Micro Devices, Inc. Gemma is a trademark of Google
              LLC. Evolus is a trademark of CodeDesign S.r.l.
            </span>
          </p>
          {credited && <PoweredBy health={health} />}
        </div>
      </div>
    </footer>
  );
}

/**
 * The footer's top edge, ruled like a tailor's tape (decoration only): a hairline with faint ticks every 8px and a
 * longer tick every 64px hanging from it. Each tick layer is one small tile repeated, so every tick lands on a whole
 * pixel. It draws left to right over 1.2 s as the footer scrolls in; otherwise it is simply there.
 */
function TapeEdge() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 h-[7px] [clip-path:inset(0)] transition-[clip-path] duration-1200 ease-thread in-data-[reveal=armed]:[clip-path:inset(0_100%_0_0)]"
      style={TAPE}
    />
  );
}

const TAPE: CSSProperties = {
  backgroundImage: [
    "linear-gradient(90deg, var(--tick) 0 1px, transparent 1px)",
    "linear-gradient(90deg, var(--tick-faint) 0 1px, transparent 1px)",
    "linear-gradient(var(--line), var(--line))",
  ].join(", "),
  backgroundSize: "64px 7px, 8px 4px, 100% 1px",
  backgroundRepeat: "repeat-x, repeat-x, no-repeat",
};

function Social({ href, label, children }: { href: string; label: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
      className="grid size-10 place-items-center rounded-full border border-line text-fg-muted transition-[color,border-color,scale] duration-160 ease-thread hover:border-fg hover:text-fg focus-visible:border-fg focus-visible:text-fg active:scale-95"
    >
      {children}
    </a>
  );
}

function XMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function GitHubMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <path d="M12 .5C5.73.5.75 5.48.75 11.76c0 4.97 3.22 9.18 7.69 10.67.56.1.77-.24.77-.54v-1.9c-3.13.68-3.79-1.51-3.79-1.51-.51-1.3-1.25-1.65-1.25-1.65-1.02-.7.08-.69.08-.69 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.73.39-1.22.71-1.5-2.5-.28-5.13-1.25-5.13-5.57 0-1.23.44-2.24 1.16-3.03-.12-.28-.5-1.43.11-2.98 0 0 .95-.3 3.1 1.16a10.7 10.7 0 0 1 5.64 0c2.15-1.46 3.1-1.16 3.1-1.16.61 1.55.23 2.7.11 2.98.72.79 1.16 1.8 1.16 3.03 0 4.33-2.64 5.28-5.15 5.56.4.35.76 1.03.76 2.08v3.08c0 .3.2.65.78.54 4.46-1.49 7.68-5.7 7.68-10.67C23.25 5.48 18.27.5 12 .5z" />
    </svg>
  );
}
