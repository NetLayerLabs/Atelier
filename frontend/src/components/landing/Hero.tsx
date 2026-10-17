"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import {
  Badge,
  Button,
  Chip,
  cx,
  DUR,
  EASE,
  Eyebrow,
  IconArrowDown,
  IconArrowUpRight,
  INSTANT,
  StatusDot,
} from "@/components/ds";
import { useDemo } from "@/lib/demo";
import { SERVICE_ORDER, SERVICE_SHORT, useHealth } from "@/lib/health";
import { scrollToId } from "../ui";
import { HeroGauge } from "./HeroGauge";
import { useReducedMotionSafe } from "./motion";
import { Reveal, REVEAL_RISE, REVEAL_TYPESET, serviceBadge } from "./primitives";

export const LANDING_CONTENTS = [
  { id: "landing-problem", label: "The problem" },
  { id: "landing-how", label: "How it works" },
  { id: "landing-agents", label: "The agents" },
  { id: "landing-direction", label: "Human + AI" },
  { id: "landing-stack", label: "Under the hood" },
  { id: "landing-value", label: "Business value" },
] as const;

const TOPICS = ["Customer voice", "Creative direction", "Supplier quotes", "Pre-orders", "Forecast"];

/** A headline line's mask: the padding (taken back by the margin) keeps the descenders of "only" and "already". */
const LINE_MASK = "-mb-[.12em] block overflow-hidden pb-[.12em]";

/**
 * The first screen, Scenar-style: a giant thin-line gauge spanning the viewport (an illustration, labelled as one),
 * fragments of a director ↔ mill negotiation floating around it, and the copy at the foot: eyebrow, a huge light
 * headline, two pills and the topic chips. Below it: one honest paragraph and the live system status.
 *
 * The copy enters in CSS (.hero-in / .hero-line, beats in --hero-at), so it plays and ends visible without JS: the
 * eyebrow at 0.2 s, the headline line by line out of its masks at 0.35 / 0.47 s, the pills at 0.6 s, the chips 40 ms
 * apart, the caption last - while the gauge ignites behind it.
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

        <div className="hero-foot relative z-10 px-4 pt-28 pb-7 sm:px-8 md:pt-44 md:pb-10">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between md:gap-10">
            <div className="min-w-0">
              <Eyebrow className="hero-in [--hero-at:200ms]" as="p">
                <span className="sm:hidden">AI agent for fashion · AMD Hackathon ACT III</span>
                <span className="max-sm:hidden">AI agent for fashion brands · AMD Developer Hackathon ACT III</span>
              </Eyebrow>
              <h1
                id="landing-hero-title"
                className="mt-4 text-[clamp(2.5rem,5.6vw,4.75rem)] leading-none font-light tracking-[-0.03em] text-fg"
              >
                <span className={LINE_MASK}>
                  <span className="hero-line block [--hero-at:350ms]">Make only what&rsquo;s</span>
                </span>{" "}
                <span className={LINE_MASK}>
                  <span className="hero-line block [--hero-at:470ms]">already sold.</span>
                </span>
              </h1>
              <div className="hero-in mt-7 flex flex-wrap gap-2.5 [--hero-at:600ms] md:mt-8">
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
            <ul className="flex flex-wrap gap-1.5 md:max-w-[36rem] md:justify-end md:pb-2.5" aria-label="What Atelier covers">
              {TOPICS.map((t, i) => (
                <li key={t} className="hero-in" style={{ ["--hero-at" as string]: `${640 + i * 40}ms` }}>
                  <Chip size="sm" className="h-7 px-3 text-[0.64rem]">
                    {t}
                  </Chip>
                </li>
              ))}
            </ul>
          </div>
          <p className="hero-in mt-6 text-micro text-fg-faint [--hero-at:840ms] md:mt-8">
            Illustration - the gauge is a scale, not a reading. Every number in the studio below is measured or shown as “-”.
          </p>
        </div>
      </section>

      <section aria-label="What Atelier does" className="pt-16 pb-6 sm:pt-24">
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">
          {/* Below the fold it opens like a section head: the eyebrow rises, the ink sentence is set, and the muted
              remainder follows as a second beat (+250 ms; opacity only, it is inline). */}
          <Reveal variant="stage" className="lg:col-span-6">
            <Eyebrow className={REVEAL_RISE}>What it does</Eyebrow>
            <p
              className={cx(
                "mt-5 max-w-xl text-[clamp(1.35rem,2.2vw,1.85rem)] leading-[1.25] font-light tracking-[-0.02em] text-balance text-fg",
                REVEAL_TYPESET,
                "in-data-[reveal=shown]:delay-[150ms]",
              )}
            >
              Atelier reads a trend from a mood board, sketches the garments and takes your direction in plain words.
              <span className="text-fg-muted transition-opacity duration-700 ease-thread in-data-[reveal=armed]:opacity-0 in-data-[reveal=shown]:delay-[400ms]">
                {" "}
                Its agents write the tech pack, brief the mills and open a pre-order - production is ordered only once
                pre-orders cover it.
              </span>
            </p>
          </Reveal>
          <Reveal variant="stage" className="lg:col-span-6">
            <StatusStrip className={cx(REVEAL_RISE, "lg:in-data-[reveal=shown]:delay-[250ms]")} />
          </Reveal>
        </div>

        <nav aria-label="On this page" className="mt-12 sm:mt-16">
          {/* The pills cascade in 40 ms apart (STAGGER.chip). */}
          <Reveal as="ol" variant="stage" className="flex flex-wrap gap-1.5">
            {LANDING_CONTENTS.map((c, i) => (
              <li
                key={c.id}
                className={cx(REVEAL_RISE, "in-data-[reveal=shown]:delay-[calc(var(--i)*40ms)]")}
                style={{ ["--i" as string]: i }}
              >
                {/* Hover / keyboard focus: the numeral steps to ink and a grey fill is measured in from the left
                    (drawn out to the right again, like .link-measure). */}
                <button
                  type="button"
                  onClick={() => scrollToId(c.id)}
                  className="group relative isolate inline-flex h-9 items-center gap-2 overflow-hidden rounded-full border border-line-strong px-3.5 text-[0.74rem] font-medium text-fg transition-colors before:absolute before:inset-0 before:-z-10 before:origin-right before:scale-x-0 before:bg-paper-2 before:transition-[scale] before:duration-500 before:ease-thread hover:border-line-bold hover:before:origin-left hover:before:scale-x-100 focus-visible:before:origin-left focus-visible:before:scale-x-100"
                >
                  <span className="text-fg-faint tabular transition-colors group-hover:text-fg group-focus-visible:text-fg">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {c.label}
                </button>
              </li>
            ))}
            <li
              className={cx(REVEAL_RISE, "in-data-[reveal=shown]:delay-[calc(var(--i)*40ms)]")}
              style={{ ["--i" as string]: LANDING_CONTENTS.length }}
            >
              <button
                type="button"
                onClick={() => scrollToId("chapter-trend")}
                className="inline-flex h-9 items-center gap-2 rounded-full bg-inverse px-3.5 text-[0.74rem] font-medium text-on-inverse transition-colors hover:bg-inverse-hover"
              >
                The studio · I–IV
                <IconArrowDown size={13} />
              </button>
            </li>
          </Reveal>
        </nav>
      </section>
    </>
  );
}

/**
 * One honest line from GET /api/health: which services are connected, unreachable, not connected or fake. When the
 * first real answer replaces "Checking services…", its rows cascade in (.hero-arrive) and the summary crossfades;
 * later polls only animate what actually changed, and the n/m summary never counts.
 */
export function StatusStrip({ className }: { className?: string }) {
  const health = useHealth((s) => s.health);
  const reduce = useReducedMotionSafe();
  // Mounted before the first answer (the landing on load): its rows arrive. Remounted with an answer already in
  // hand (back from another page): they are simply there.
  const [arrive] = useState(() => health.kind !== "ok");
  // An optional backup that isn't connected is not part of the running system: not listed.
  const services = health.kind === "ok" ? health.data.services.filter((s) => !s.optional || s.status === "connected") : [];
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
  else if (health.kind === "down") summary = "Backend offline - reconnecting";
  else if (health.kind === "error") summary = "Health check failed";
  else summary = `${connected}/${counted.length} connected`;

  return (
    // relative: anchors the outgoing summary while it crossfades out of the layout
    <div className={cx("relative rounded-card border border-line bg-surface p-5 shadow-e2 sm:p-6", className)}>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <Eyebrow
          tone={health.kind === "ok" ? (fake ? "bad" : all ? "ok" : connected ? "warn" : "faint") : health.kind === "checking" ? "faint" : "bad"}
          live={health.kind === "ok" && connected > 0 && !fake}
        >
          System status <span className="text-fg-faint">· live from /api/health</span>
        </Eyebrow>
        <p className="text-small font-medium tabular">
          <AnimatePresence initial={false} mode="popLayout">
            <motion.span
              key={summary}
              className={cx("inline-block", health.kind === "down" || health.kind === "error" ? "text-bad" : "text-fg")}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={reduce ? INSTANT : { duration: DUR.ui, ease: EASE }}
            >
              {summary}
            </motion.span>
          </AnimatePresence>
        </p>
      </div>
      {groups.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2.5">
          {groups.map((g, i) => (
            <li
              key={g.status}
              className={cx("flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:gap-3", arrive && "hero-arrive")}
              style={{ ["--i" as string]: i }}
            >
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
        <p
          className={cx("mt-3 flex items-center gap-2 text-micro text-fg-faint", arrive && "hero-arrive")}
          style={{ ["--i" as string]: groups.length }}
        >
          <StatusDot tone="faint" size={6} />
          {fake > 0
            ? `${fake} endpoint${fake > 1 ? "s are" : " is"} the local test double, labelled FAKE wherever it is used.`
            : "Steps that need a missing service stop with an error and a setup hint - nothing is filled in."}
        </p>
      )}
    </div>
  );
}
