"use client";

import { Badge, Button, Chip, cx, Eyebrow, IconArrowDown, IconArrowUpRight, StatusDot } from "@/components/ds";
import { useDemo } from "@/lib/demo";
import { SERVICE_ORDER, SERVICE_SHORT, useHealth } from "@/lib/health";
import { scrollToId } from "../ui";
import { HeroGauge } from "./HeroGauge";
import { serviceBadge } from "./primitives";

export const LANDING_CONTENTS = [
  { id: "landing-problem", label: "The problem" },
  { id: "landing-how", label: "How it works" },
  { id: "landing-agents", label: "The agents" },
  { id: "landing-direction", label: "Human + AI" },
  { id: "landing-stack", label: "Under the hood" },
  { id: "landing-value", label: "Business value" },
] as const;

const TOPICS = ["Customer voice", "Creative direction", "Supplier quotes", "Pre-orders", "Forecast"];

/**
 * The first screen, Scenar-style: a giant thin-line gauge spanning the viewport (an illustration, labelled as one),
 * fragments of a director ↔ mill negotiation floating around it, and the copy at the foot: eyebrow, a huge light
 * headline, two pills and the topic chips. Below it: one honest paragraph and the live system status.
 */
export function Hero() {
  const startDemo = useDemo((s) => s.start);
  const demoOn = useDemo((s) => s.status !== "idle");

  return (
    <>
      <section
        id="landing-hero"
        data-landing
        aria-labelledby="landing-hero-title"
        // Full-bleed: breaks out of the page container and slides up under the floating app bar.
        className="relative isolate -mt-[4.5rem] ml-[calc(50%-50vw)] flex min-h-[100svh] w-screen flex-col justify-end overflow-hidden"
      >
        <HeroGauge />

        <div className="hero-foot rise relative z-10 px-4 pt-28 pb-7 sm:px-8 md:pt-44 md:pb-10" style={{ animationDelay: "500ms" }}>
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between md:gap-10">
            <div className="min-w-0">
              <Eyebrow className="rise" as="p">
                <span className="sm:hidden">AI agent for fashion · AMD Hackathon ACT III</span>
                <span className="max-sm:hidden">AI agent for fashion brands · AMD Developer Hackathon ACT III</span>
              </Eyebrow>
              <h1
                id="landing-hero-title"
                className="rise mt-4 text-[clamp(2.5rem,5.6vw,4.75rem)] leading-none font-light tracking-[-0.03em] text-fg"
                style={{ animationDelay: "300ms" }}
              >
                <span className="block">Make only what&rsquo;s</span> <span className="block">already sold.</span>
              </h1>
              <div className="rise mt-7 flex flex-wrap gap-2.5 md:mt-8" style={{ animationDelay: "500ms" }}>
                <Button
                  onClick={() => scrollToId("chapter-trend")}
                  trailing={<IconArrowUpRight size={14} strokeWidth={2.2} />}
                  data-demo="enter-studio"
                >
                  Launch studio
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => startDemo()}
                  disabled={demoOn}
                  title="A guided tour that drives the real UI against the real services (Shift+D)"
                >
                  {demoOn ? "Tour running" : "Take the tour"}
                </Button>
              </div>
            </div>
            <ul className="rise flex flex-wrap gap-1.5 md:max-w-[36rem] md:justify-end md:pb-2.5" aria-label="What Atelier covers" style={{ animationDelay: "500ms" }}>
              {TOPICS.map((t) => (
                <li key={t}>
                  <Chip size="sm" className="h-7 px-3 text-[0.64rem]">
                    {t}
                  </Chip>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-6 text-micro text-fg-faint md:mt-8">
            Illustration - the gauge is a scale, not a reading. Every number in the studio below is measured or shown as “-”.
          </p>
        </div>
      </section>

      <section aria-label="What Atelier does" className="pt-16 pb-6 sm:pt-24">
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-6">
            <Eyebrow>What it does</Eyebrow>
            <p className="mt-5 max-w-xl text-[clamp(1.35rem,2.2vw,1.85rem)] leading-[1.25] font-light tracking-[-0.02em] text-balance text-fg">
              Atelier reads a trend from a mood board, sketches the garments and takes your direction in plain words.
              <span className="text-fg-muted">
                {" "}
                Its agents write the tech pack, brief the mills and open a pre-order - production is ordered only once
                pre-orders cover it.
              </span>
            </p>
          </div>
          <div className="lg:col-span-6">
            <StatusStrip />
          </div>
        </div>

        <nav aria-label="On this page" className="mt-12 sm:mt-16">
          <ol className="flex flex-wrap gap-1.5">
            {LANDING_CONTENTS.map((c, i) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => scrollToId(c.id)}
                  className="group inline-flex h-9 items-center gap-2 rounded-full border border-line-strong px-3.5 text-[0.74rem] font-medium text-fg transition-colors hover:border-line-bold hover:bg-paper-2"
                >
                  <span className="text-fg-faint tabular">{String(i + 1).padStart(2, "0")}</span>
                  {c.label}
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={() => scrollToId("chapter-trend")}
                className="inline-flex h-9 items-center gap-2 rounded-full bg-inverse px-3.5 text-[0.74rem] font-medium text-on-inverse transition-colors hover:bg-inverse-hover"
              >
                The studio · I–IV
                <IconArrowDown size={13} />
              </button>
            </li>
          </ol>
        </nav>
      </section>
    </>
  );
}

/** One honest line from GET /api/health: which services are connected, unreachable, not connected or fake. */
export function StatusStrip({ className }: { className?: string }) {
  const health = useHealth((s) => s.health);
  const services = health.kind === "ok" ? health.data.services : [];
  const ordered = [
    ...SERVICE_ORDER.map((n) => services.find((s) => s.name === n)).filter((s) => !!s),
    ...services.filter((s) => !(SERVICE_ORDER as readonly string[]).includes(s.name)),
  ];
  const counted = services.filter((s) => !s.optional || s.status === "connected"); // optional backups aren't "missing"
  const connected = counted.filter((s) => s.status === "connected" && !s.fake).length;
  const fake = services.filter((s) => s.fake).length;
  const all = counted.length > 0 && connected === counted.length;

  // Group services by state so the strip stays short on a phone; every service is still named.
  const groups = (["fake", "connected", "unreachable", "not-connected"] as const)
    .map((status) => {
      const names = ordered
        .filter((s) => !(s.optional && s.status !== "connected"))
        .filter((s) => serviceBadge(s, "ok").status === status)
        .map((s) => ({
          name: SERVICE_SHORT[s.name] ?? s.name,
          title: [s.detail, s.status !== "connected" ? s.hint : undefined].filter(Boolean).join(" - ") || undefined,
        }));
      return { status, label: serviceBadge(ordered.find((s) => serviceBadge(s, "ok").status === status), "ok").label, names };
    })
    .filter((g) => g.names.length > 0);

  let summary: string;
  if (health.kind === "checking") summary = "Checking services…";
  else if (health.kind === "down") summary = "Backend offline - start it with ./dev.sh";
  else if (health.kind === "error") summary = "Health check failed";
  else summary = `${connected}/${counted.length} connected`;

  return (
    <div className={cx("rounded-card border border-line bg-surface p-5 shadow-e2 sm:p-6", className)}>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <Eyebrow
          tone={health.kind === "ok" ? (fake ? "bad" : all ? "ok" : connected ? "warn" : "faint") : health.kind === "checking" ? "faint" : "bad"}
          live={health.kind === "ok" && connected > 0 && !fake}
        >
          System status <span className="text-fg-faint">· live from /api/health</span>
        </Eyebrow>
        <p className={cx("text-small font-medium tabular", health.kind === "down" || health.kind === "error" ? "text-bad" : "text-fg")}>
          {summary}
        </p>
      </div>
      {groups.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2.5">
          {groups.map((g) => (
            <li key={g.status} className="flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:gap-3">
              <Badge status={g.status} className="self-start sm:min-w-[7.5rem]">
                {g.label} · {g.names.length}
              </Badge>
              <p className="text-small text-pretty text-fg-muted">
                {g.names.map((n, i) => (
                  <span key={n.name} title={n.title}>
                    {i > 0 && <span className="text-fg-faint"> · </span>}
                    {n.name}
                  </span>
                ))}
              </p>
            </li>
          ))}
        </ul>
      )}
      {health.kind === "ok" && connected < counted.length && (
        <p className="mt-3 flex items-center gap-2 text-micro text-fg-faint">
          <StatusDot tone="faint" size={6} />
          {fake > 0
            ? `${fake} endpoint${fake > 1 ? "s are" : " is"} the local test double, labelled FAKE wherever it is used.`
            : "Steps that need a missing service stop with an error and a setup hint - nothing is filled in."}
        </p>
      )}
    </div>
  );
}
