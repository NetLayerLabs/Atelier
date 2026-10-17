"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from "react";
import { Badge, cx, DUR, EASE, Eyebrow, INSTANT, Label, type BadgeStatus } from "@/components/ds";
import { useHealth } from "@/lib/health";
import type { ServiceStatus } from "@/lib/types";
import { prefersReducedMotion } from "../ui";
import { useReducedMotionSafe } from "./motion";

/*
 * The landing's motion language, in milliseconds. One easing everywhere (EASE / var(--ease-thread) / Tailwind
 * `ease-thread`); these are the beats a section opens with and the gaps between siblings, so every section keeps the
 * same tempo. Hidden states only ever apply while an element is armed (see useArm).
 */

/** When each part of a section's opening plays, from the moment it scrolls into view. */
export const LANDING_SEQ = { rule: 0, tick: 150, eyebrow: 0, title: 150, em: 450, lede: 500 } as const;

/** Gaps between siblings that enter together: list items, figures, chips. */
export const STAGGER = { sibling: 80, figure: 120, chip: 40 } as const;

/**
 * For a child of <Reveal variant="stage">: fades in and rises 8px into place (0.7s) once the stage is shown. Add
 * its beat, e.g. `in-data-[reveal=shown]:delay-[500ms]`. Static, no-JS and reduced motion: untouched.
 */
export const REVEAL_RISE =
  "transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:translate-y-[8px] in-data-[reveal=armed]:opacity-0";

/**
 * For a display heading under <Reveal variant="stage">: typeset top to bottom, a clip-path wipe plus a 0.35em rise
 * over 0.9s. At rest the clip sits at generous negative insets, so descenders and accents are never shaved and only
 * the armed state sets anything (no armed/shown tug-of-war under nested stages). An <Em> inside fades in as a second
 * beat (opacity only: Em is inline). Add both beats, e.g. `in-data-[reveal=shown]:delay-[150ms]
 * in-data-[reveal=shown]:[&_em]:delay-[450ms]`.
 */
export const REVEAL_TYPESET =
  "[clip-path:inset(-0.2em_-0.2em_-0.35em_-0.2em)] transition-[translate,clip-path] duration-[900ms] ease-thread in-data-[reveal=armed]:translate-y-[0.35em] in-data-[reveal=armed]:[clip-path:inset(0_0_100%_0)] [&_em]:transition-opacity [&_em]:duration-700 [&_em]:ease-thread in-data-[reveal=armed]:[&_em]:opacity-0";

/** "static": never hidden (SSR, no JS, reduced motion, already on screen). "armed": below the fold, waiting. */
export type ArmState = "static" | "armed" | "shown";

export type ArmOptions = {
  /** Arm only if the element's top is below this fraction of the viewport height at hydration. Default 0.92. */
  fold?: number;
  /** IntersectionObserver rootMargin that decides "in view". Default "0px 0px -8% 0px". */
  rootMargin?: string;
  /** Safety net: once any part of it is on screen, show it within this many ms regardless. Default 12 000. */
  safetyMs?: number;
};

/**
 * Reveal's contract as a hook: nothing is hidden in the server HTML. After hydration, an element that is still below
 * the fold becomes "armed" and turns "shown" once it scrolls into view; anything else stays "static" for good. Never
 * arms under reduced motion or without IntersectionObserver. Write the state to a data attribute and style from it.
 */
export function useArm(ref: RefObject<Element | null>, opts?: ArmOptions): ArmState {
  const fold = opts?.fold ?? 0.92;
  const rootMargin = opts?.rootMargin ?? "0px 0px -8% 0px";
  const safetyMs = opts?.safetyMs ?? 12_000;
  const [state, setState] = useState<ArmState>("static");

  useEffect(() => {
    const node = ref.current;
    if (!node || prefersReducedMotion() || typeof IntersectionObserver === "undefined") return;
    if (node.getBoundingClientRect().top < window.innerHeight * fold) return; // already on screen: leave it be
    setState("armed");
    let net: ReturnType<typeof setTimeout> | undefined;
    const show = () => {
      setState("shown");
      stop();
    };
    const inView = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) show();
      },
      { rootMargin },
    );
    // Safety net: anything that is partly on screen (say, parked in the bottom 8%) shows within safetyMs. The clock
    // only runs while it is on screen, so a reader who takes a minute to get here still sees the entrance.
    const onScreen = new IntersectionObserver((entries) => {
      const visible = entries[entries.length - 1].isIntersecting;
      if (visible && net === undefined) net = setTimeout(show, safetyMs);
      if (!visible && net !== undefined) {
        clearTimeout(net);
        net = undefined;
      }
    });
    const stop = () => {
      inView.disconnect();
      onScreen.disconnect();
      clearTimeout(net);
    };
    inView.observe(node);
    onScreen.observe(node);
    return stop;
  }, [ref, fold, rootMargin, safetyMs]);

  return state;
}

/**
 * Scroll reveal that degrades to "always visible": nothing is hidden in the server HTML. After hydration, only an
 * element that is still below the fold is armed and it settles once it scrolls into view.
 *
 * - variant "rise" (default): the whole block fades and rises 18px.
 * - variant "stage": the block itself never fades or moves; it only writes data-reveal so its children choreograph
 *   themselves with Tailwind's `in-data-[reveal=armed]:` / `in-data-[reveal=shown]:` variants, e.g.
 *   `transition-[opacity,translate] duration-700 ease-thread in-data-[reveal=armed]:opacity-0
 *   in-data-[reveal=armed]:translate-y-2 in-data-[reveal=shown]:delay-[300ms]`. Hidden states then apply only while
 *   armed, so the server HTML, no-JS and reduced motion all show the final state.
 *
 * `delay` (ms) holds the reveal back once it is shown: "rise" delays its own transition; "stage" exposes it to its
 * children as `--reveal-delay`.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as: Tag = "div",
  variant = "rise",
  style: styleProp,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li" | "figure" | "article" | "ul" | "ol" | "p" | "header" | "footer" | "aside" | "blockquote";
  variant?: "rise" | "stage";
} & Omit<HTMLAttributes<HTMLElement>, "children" | "className">) {
  const ref = useRef<HTMLElement>(null);
  const state = useArm(ref);

  let style: CSSProperties | undefined = styleProp;
  if (delay && state === "shown") {
    style =
      variant === "stage"
        ? ({ ...styleProp, "--reveal-delay": `${delay}ms` } as CSSProperties)
        : { ...styleProp, transitionDelay: `${delay}ms` };
  }
  return (
    <Tag
      ref={ref as never}
      data-reveal={state}
      style={style}
      className={cx(variant === "rise" && "reveal", className) || undefined}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/**
 * Landing section header: "● 01 · The problem" eyebrow, a light display title (one <Em> at most) and a lede that
 * sits beside the title on wide screens. Below the fold it opens in sequence (LANDING_SEQ): the eyebrow rises, the
 * title is typeset, its <Em> half follows as a second beat, then the lede.
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
    <Reveal variant="stage" className="mb-12 grid gap-5 sm:mb-16 lg:grid-cols-12 lg:items-end lg:gap-12">
      <div className="lg:col-span-7">
        <Eyebrow className={REVEAL_RISE}>
          <span className="font-mono text-fg-faint tabular">{index}</span>
          <span aria-hidden className="mx-2 text-fg-faint">
            ·
          </span>
          {kicker}
        </Eyebrow>
        {/* Beats: LANDING_SEQ.title (150ms) and .em (450ms). */}
        <h2
          id={id}
          className={cx(
            "mt-4 text-display-l text-balance text-fg",
            REVEAL_TYPESET,
            "in-data-[reveal=shown]:delay-[150ms] in-data-[reveal=shown]:[&_em]:delay-[450ms]",
          )}
        >
          {title}
        </h2>
      </div>
      {lede && (
        <p
          className={cx(
            "max-w-xl text-body-l text-pretty text-fg-muted lg:col-span-5 lg:pb-1",
            REVEAL_RISE,
            "in-data-[reveal=shown]:delay-[500ms]", // LANDING_SEQ.lede
          )}
        >
          {lede}
        </p>
      )}
    </Reveal>
  );
}

/**
 * A landing section. Its top hairline is measured out left to right as it scrolls in, and the mark's one tick drops
 * at its start (LANDING_SEQ.rule / .tick). It arms with its own data-rule, never data-reveal, so the
 * `in-data-[reveal=…]` hooks inside the section only ever see their own Reveal. Static: today's hairline + the tick.
 */
export function LandingSection({
  id,
  children,
  className,
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const rule = useArm(ref);
  return (
    <section
      ref={ref}
      id={id}
      data-landing
      data-rule={rule}
      aria-labelledby={`${id}-title`}
      className={cx("relative py-20 sm:py-28 lg:py-32", className)}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px origin-left scale-x-100 bg-line transition-[scale] duration-[1100ms] ease-thread in-data-[rule=armed]:scale-x-0"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute top-0 left-0 h-[8px] w-px origin-top scale-y-100 bg-line-bold transition-[scale] duration-500 ease-thread in-data-[rule=armed]:scale-y-0 in-data-[rule=shown]:delay-[150ms]"
      />
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

/**
 * Connection badge for one backend service, read from the shared health poll (never assumed). Only a real change of
 * status settles in (fade + 3px rise); the server HTML and first paint never animate, and polls that report the same
 * status leave it alone.
 */
export function ServiceMode({ name, label: prefix, className }: { name: string; label?: string; className?: string }) {
  const health = useHealth((s) => s.health);
  const reduce = useReducedMotionSafe();
  const svc = health.kind === "ok" ? health.data.services.find((s) => s.name === name) : undefined;
  const b = serviceBadge(svc, health.kind);
  const title = svc
    ? [svc.detail, svc.status !== "connected" ? svc.hint : undefined].filter(Boolean).join(" - ") || undefined
    : "Status from GET /api/health";
  return (
    // The label's own wrapper (Badge's last child) anchors the outgoing label while it pops out of the layout.
    <Badge status={b.status} title={title} className={cx("[&>span:last-child]:relative", className)}>
      <AnimatePresence initial={false} mode="popLayout">
        <motion.span
          key={`${b.status}:${b.label}`}
          className="inline-block align-top whitespace-nowrap" // never truncated: a cut-off status hides the truth
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -3 }}
          transition={reduce ? INSTANT : { duration: DUR.ui, ease: EASE }}
        >
          {prefix ? `${prefix} · ${b.label}` : b.label}
        </motion.span>
      </AnimatePresence>
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
          className="underline decoration-line-bold underline-offset-2 transition-colors duration-[160ms] ease-thread hover:text-fg hover:decoration-fg focus-visible:text-fg focus-visible:decoration-fg"
        >
          {children}
        </a>
      ) : (
        children
      )}
    </p>
  );
}
