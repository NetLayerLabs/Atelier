"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Badge, cx, Eyebrow, Label, type BadgeStatus } from "@/components/ds";
import { useHealth } from "@/lib/health";
import type { ServiceStatus } from "@/lib/types";
import { prefersReducedMotion } from "../ui";

/**
 * Scroll reveal that degrades to "always visible": nothing is hidden in the server HTML. After hydration, only an
 * element that is still below the fold is armed (faded + nudged down) and it settles once it scrolls into view.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li" | "figure" | "article";
}) {
  const ref = useRef<HTMLElement>(null);
  const [state, setState] = useState<"static" | "armed" | "shown">("static");

  useEffect(() => {
    const node = ref.current;
    if (!node || prefersReducedMotion() || typeof IntersectionObserver === "undefined") return;
    if (node.getBoundingClientRect().top < window.innerHeight * 0.92) return; // already on screen: leave it be
    setState("armed");
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setState("shown");
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(node);
    // Safety net: never leave content hidden (e.g. a jump-scroll that skips the observer).
    const t = setTimeout(() => setState("shown"), 12_000);
    return () => {
      io.disconnect();
      clearTimeout(t);
    };
  }, []);

  const style: CSSProperties | undefined = delay && state === "shown" ? { transitionDelay: `${delay}ms` } : undefined;
  return (
    <Tag ref={ref as never} data-reveal={state} style={style} className={cx("reveal", className)}>
      {children}
    </Tag>
  );
}

/**
 * Landing section header: "● 01 · The problem" eyebrow, a light display title (one <Em> at most) and a lede that
 * sits beside the title on wide screens.
 */
export function SectionHead({
  index,
  kicker,
  title,
  lede,
  id,
}: {
  index: string;
  kicker: string;
  title: ReactNode;
  lede?: ReactNode;
  id: string;
}) {
  return (
    <Reveal className="mb-12 grid gap-5 sm:mb-16 lg:grid-cols-12 lg:items-end lg:gap-12">
      <div className="lg:col-span-7">
        <Eyebrow>
          <span className="font-mono text-fg-faint tabular">{index}</span>
          <span aria-hidden className="mx-2 text-fg-faint">
            ·
          </span>
          {kicker}
        </Eyebrow>
        <h2 id={id} className="mt-4 text-display-l text-balance text-fg">
          {title}
        </h2>
      </div>
      {lede && <p className="max-w-xl text-body-l text-pretty text-fg-muted lg:col-span-5 lg:pb-1">{lede}</p>}
    </Reveal>
  );
}

export function LandingSection({
  id,
  children,
  className,
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      id={id}
      data-landing
      aria-labelledby={`${id}-title`}
      className={cx("border-t border-line py-20 sm:py-28 lg:py-32", className)}
    >
      {children}
    </section>
  );
}

/** Map one service from GET /api/health onto the design system's Badge vocabulary. */
export function serviceBadge(svc: ServiceStatus | undefined, kind: "checking" | "ok" | "down" | "error"): {
  status: BadgeStatus;
  label: string;
} {
  if (!svc) {
    if (kind === "checking") return { status: "pending", label: "Checking…" };
    if (kind === "ok") return { status: "not-connected", label: "Not reported" };
    return { status: "unreachable", label: "Backend offline" };
  }
  if (svc.fake) return { status: "fake", label: "FAKE upstream - not real" };
  if (svc.status === "connected") return { status: "connected", label: "Connected" };
  if (svc.status === "unreachable") return { status: "unreachable", label: "Unreachable" };
  return { status: "not-connected", label: "Not connected" };
}

/** Connection badge for one backend service, read from the shared health poll (never assumed). */
export function ServiceMode({ name, label: prefix, className }: { name: string; label?: string; className?: string }) {
  const health = useHealth((s) => s.health);
  const svc = health.kind === "ok" ? health.data.services.find((s) => s.name === name) : undefined;
  const b = serviceBadge(svc, health.kind);
  const title = svc
    ? [svc.detail, svc.status !== "connected" ? svc.hint : undefined].filter(Boolean).join(" - ") || undefined
    : "Status from GET /api/health";
  return (
    <Badge status={b.status} title={title} className={className}>
      {prefix ? `${prefix} · ${b.label}` : b.label}
    </Badge>
  );
}

/** A small "Source:" line under a cited figure. External links open in a new tab. */
export function Source({ children, href, className }: { children: ReactNode; href?: string; className?: string }) {
  return (
    <p className={cx("text-micro text-fg-faint", className)}>
      <Label className="mr-1.5">Source</Label>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="underline decoration-line-bold underline-offset-2 transition-colors hover:text-fg"
        >
          {children}
        </a>
      ) : (
        children
      )}
    </p>
  );
}
