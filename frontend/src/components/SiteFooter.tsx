"use client";

import type { ReactNode } from "react";
import { useHealth } from "@/lib/health";
import { AtelierLockup, Label } from "./ds";
import { PoweredBy } from "./Header";

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
      { label: "AMD Developer Cloud", href: "https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html" },
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

/**
 * Site footer: the lockup, what Atelier does, X and GitHub, then Product / Powered by / Resources. Same type as the
 * rest of the app (Inter: body text, and the small section labels the menu uses); links lift to ink on hover.
 */
export function SiteFooter() {
  const health = useHealth((s) => s.health);
  const credited = health.kind === "ok" && (health.data.poweredBy.amd || health.data.poweredBy.evolus);
  return (
    <footer id="site-footer" className="border-t border-line">
      <div className="mx-auto max-w-[1400px] px-4 pt-14 pb-10 sm:px-8 lg:px-12">
        <div className="grid grid-cols-2 gap-x-8 gap-y-12 md:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]">
          <div className="col-span-2 flex max-w-md flex-col gap-6 md:col-span-1">
            <AtelierLockup height={26} className="text-fg" title="Atelier" />
            <p className="text-body text-pretty text-fg-muted">
              An AI agent for fashion brands. It reads the trend, takes the designer&rsquo;s own sketch, writes the tech
              pack, briefs suppliers in their own language and opens a real Shopify pre-order. Production starts only
              once real customers have paid.
            </p>
            <div className="flex items-center gap-2">
              <Social href={X_URL} label="NetLayerLabs on X">
                <XMark />
              </Social>
              <Social href={REPO} label="Atelier on GitHub">
                <GitHubMark />
              </Social>
            </div>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title} className="flex flex-col gap-2">
              <Label as="p">{col.title}</Label>
              <ul className="flex flex-col gap-1">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <a
                      href={l.href}
                      {...(external(l.href) ? { target: "_blank", rel: "noreferrer" } : {})}
                      className="text-body text-fg-muted transition-colors hover:text-fg"
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="mt-14 flex flex-col gap-3 border-t border-line pt-6 text-micro text-fg-faint sm:flex-row sm:items-center sm:justify-between">
          <p>
            © 2026 NetLayerLabs ·{" "}
            <a href={`${REPO}/blob/main/LICENSE`} target="_blank" rel="noreferrer" className="hover:text-fg">
              MIT licence
            </a>{" "}
            ·{" "}
            <a
              href="https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii"
              target="_blank"
              rel="noreferrer"
              className="hover:text-fg"
            >
              AMD Developer Hackathon ACT III
            </a>
          </p>
          {credited && <PoweredBy health={health} />}
        </div>
      </div>
    </footer>
  );
}

function Social({ href, label, children }: { href: string; label: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
      className="grid size-10 place-items-center rounded-full border border-line text-fg-muted transition-colors hover:border-line-bold hover:bg-paper-2 hover:text-fg"
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
