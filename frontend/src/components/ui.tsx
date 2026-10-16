"use client";

import { motion } from "framer-motion";
import { useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import {
  Badge,
  Button as DsButton,
  Chip,
  Eyebrow,
  InlineAlert,
  SetupHint as DsSetupHint,
  Spinner as DsSpinner,
} from "./ds";
import { resolveAssetUrl, type ConnectionStatus } from "@/lib/api";

import { cx } from "./ds/tokens";

export { cx };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "quiet";
  loading?: boolean;
};

/**
 * Legacy button API, now rendered by the design-system pill (components/ds/Button).
 * primary → primary (ink), ghost → secondary (outline), quiet → ghost. New code: import { Button } from "./ds".
 */
export function Button({ variant = "primary", ...rest }: ButtonProps) {
  return <DsButton variant={variant === "ghost" ? "secondary" : variant === "quiet" ? "ghost" : "primary"} {...rest} />;
}

export function Spinner({ className }: { className?: string }) {
  return <DsSpinner className={className} />;
}

export function ErrorNotice({
  title = "Something went wrong",
  message,
  hint,
  onRetry,
  retryLabel = "Retry",
  retrying,
}: {
  title?: string;
  message?: string;
  /** v5: how to set up / fix the service behind a 503. */
  hint?: string;
  onRetry?: () => void;
  retryLabel?: string;
  retrying?: boolean;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <InlineAlert
        tone="bad"
        title={title}
        hint={hint}
        action={
          onRetry && (
            <DsButton variant="secondary" size="sm" onClick={onRetry} loading={retrying}>
              {retryLabel}
            </DsButton>
          )
        }
      >
        {message}
      </InlineAlert>
    </motion.div>
  );
}

/** v5: the setup hint a 503 / health entry carries ("Set AMD_VISION_ENDPOINT …"). */
export function SetupHint({ hint, className }: { hint: string; className?: string }) {
  return <DsSetupHint hint={hint} className={className} />;
}

/**
 * v5: connection state of a real service. Not connected (grey), Unreachable (amber), Connected (sage);
 * `fake` (the local test double) always wins and shows red "FAKE UPSTREAM - not real".
 */
export function ServiceBadge({
  status,
  fake,
  className,
}: {
  status: ConnectionStatus;
  fake?: boolean;
  className?: string;
}) {
  return (
    <Badge
      className={className}
      status={fake ? "fake" : status === "connected" ? "connected" : status === "unreachable" ? "unreachable" : "not-connected"}
      title={
        fake
          ? "This endpoint is the local test double, not a real service"
          : status === "connected"
            ? "Configured and answering"
            : status === "unreachable"
              ? "Configured but not answering"
              : "Not configured"
      }
    />
  );
}

/** v5: which real path produced a result, e.g. "evolus-agent → AMD vLLM" | "direct vLLM". */
export function RouteBadge({ route, className }: { route?: string | null; className?: string }) {
  if (!route) return null;
  return (
    <span
      title="Which real service produced this"
      className={cx(
        "inline-flex h-6 items-center gap-1.5 rounded-full bg-ok-soft px-2.5 font-mono text-[0.65rem] text-ok",
        className,
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-ok" />
      {route}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <Chip>{children}</Chip>
  );
}

/** Plain <img> - remote hosts and data:/SVG URLs vary, so we skip next/image optimisation. */
export function SmartImage(props: {
  src: string;
  alt: string;
  className?: string;
  imgClassName?: string;
}) {
  // Re-mount on src change so load state resets.
  return <SmartImageInner key={props.src} {...props} />;
}

function SmartImageInner({
  src,
  alt,
  className,
  imgClassName,
}: {
  src: string;
  alt: string;
  className?: string;
  imgClassName?: string;
}) {
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");
  const url = resolveAssetUrl(src);
  return (
    <div className={cx("relative overflow-hidden bg-paper-2", className)}>
      {state === "loading" && <div className="ds-skeleton absolute inset-0" aria-hidden />}
      {state === "error" || !url ? (
        <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-micro text-fg-muted">
          Image unavailable
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={alt}
          loading="lazy"
          decoding="async"
          onLoad={() => setState("loaded")}
          onError={() => setState("error")}
          className={cx(
            "h-full w-full object-cover transition-opacity duration-700",
            state === "loaded" ? "opacity-100" : "opacity-0",
            imgClassName,
          )}
        />
      )}
    </div>
  );
}

export function Chapter({
  id,
  numeral,
  title,
  kicker,
  children,
  aside,
}: {
  id: string;
  numeral: string;
  title: string;
  kicker: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <motion.section
      id={id}
      data-chapter
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      className="relative pt-16 pb-20 sm:pt-24 sm:pb-28"
      aria-labelledby={`${id}-title`}
    >
      {/* A hairline where one chapter hands over to the next. */}
      <div aria-hidden className="absolute inset-x-0 top-0 h-px bg-line" />
      <header className="mb-10 flex flex-col gap-6 sm:mb-14 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          {/* Scenar-style "● I · Trend ingestion" eyebrow, then the light display title. */}
          <Eyebrow numeral={numeral}>
            <span className="sr-only">Chapter {numeral} · </span>
            {kicker}
          </Eyebrow>
          <h2 id={`${id}-title`} className="mt-4 text-display-l text-balance text-fg">
            {title}
          </h2>
        </div>
        {aside && <div className="flex shrink-0 flex-wrap items-center gap-2">{aside}</div>}
      </header>
      {children}
    </motion.section>
  );
}

export const ease = [0.16, 1, 0.3, 1] as const;

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function scrollToId(id: string) {
  const el = document.getElementById(id);
  el?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
}
