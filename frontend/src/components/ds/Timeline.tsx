"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { IconAlert, IconCheck } from "./icons";
import { cx } from "./tokens";

export type StepStatus = "done" | "running" | "waiting" | "error" | "pending" | "skipped";

const STATUS_LABEL: Record<StepStatus, string> = {
  done: "Done",
  running: "In progress",
  waiting: "Waiting on you",
  error: "Failed",
  pending: "Not started",
  skipped: "Skipped",
};

/** The node on a timeline rail: ink check when done, an ink ring that breathes while running, etc. */
export function StepNode({ status, index, size = 28 }: { status: StepStatus; index?: number; size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cx(
        "relative z-10 grid shrink-0 place-items-center rounded-full text-micro font-medium",
        status === "done" && "bg-inverse text-on-inverse",
        status === "running" && "border-[1.5px] border-accent bg-surface text-accent",
        status === "waiting" && "border-[1.5px] border-warn bg-warn-soft text-warn",
        status === "error" && "bg-bad text-on-accent",
        status === "pending" && "border border-line-strong bg-surface text-fg-faint",
        status === "skipped" && "border border-dashed border-line-strong bg-paper text-fg-faint",
      )}
    >
      {status === "done" ? (
        <IconCheck size={14} strokeWidth={2.4} />
      ) : status === "error" ? (
        <IconAlert size={13} strokeWidth={2.2} />
      ) : status === "running" ? (
        <>
          <span className="absolute inset-[-5px] rounded-full border border-accent/40 ds-live" />
          <span className="size-2 rounded-full bg-accent" />
        </>
      ) : index != null ? (
        <span className="tabular">{index}</span>
      ) : null}
    </span>
  );
}

export type TimelineItem = {
  id: string;
  title: ReactNode;
  status: StepStatus;
  /** Right-aligned meta: a time, a duration, a route badge. */
  meta?: ReactNode;
  description?: ReactNode;
  /** Expanded content under the step (a card, an email, telemetry). */
  children?: ReactNode;
  "data-demo"?: string;
};

/**
 * Vertical timeline (the agent pipeline: tech pack → RFQs → quotes → hand-off → pre-orders → forecast → PO).
 * A stitched rail joins the nodes; the rail turns solid ink up to the last finished step. Each step announces
 * its status in text for screen readers.
 */
export function Timeline({ items, numbered = true, className }: { items: TimelineItem[]; numbered?: boolean; className?: string }) {
  return (
    <ol className={cx("relative flex flex-col", className)}>
      {items.map((it, i) => {
        const last = i === items.length - 1;
        const solid = it.status === "done" && items[i + 1] && items[i + 1].status !== "pending";
        return (
          <li key={it.id} data-demo={it["data-demo"]} className="relative flex gap-4 pb-8 last:pb-0 sm:gap-5">
            {!last && (
              <span
                aria-hidden
                className={cx("absolute top-8 bottom-1 left-[13.5px] w-px", solid ? "bg-fg" : "ds-stitch-v opacity-80")}
              />
            )}
            <StepNode status={it.status} index={numbered ? i + 1 : undefined} />
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <p className={cx("text-body font-medium", it.status === "pending" || it.status === "skipped" ? "text-fg-muted" : "text-fg")}>
                  {it.title}
                  <span className="sr-only"> - {STATUS_LABEL[it.status]}</span>
                </p>
                {it.meta && <div className="flex shrink-0 flex-wrap items-center gap-2 text-micro text-fg-faint">{it.meta}</div>}
              </div>
              {it.description && <p className="mt-1 text-small text-fg-muted">{it.description}</p>}
              {it.children && <div className="mt-4">{it.children}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export type StepperStep = {
  id: string;
  label: ReactNode;
  numeral?: string;
  status: "done" | "current" | "upcoming";
  disabled?: boolean;
  /** Small trailing mark after the label, e.g. an amber dot for "required and missing". Pair it with `srStatus`. */
  marker?: ReactNode;
  /** Status read to screen readers after the label (" - done", " - required"). */
  srStatus?: string;
};

/**
 * Horizontal stepper (chapters I–IV, workspace steps). Steps joined by a seam; the current one is an ink pill.
 * Scrolls horizontally on mobile and keeps the current step in view. Pass `onSelect` to make steps clickable:
 * by default only reached steps are (`reachable="reached"`, a linear flow); `reachable="all"` keeps every step
 * clickable, for independent sections such as the Brand workspace. `variant="well"` sets the row in a grey pill well.
 */
export function Stepper({
  steps,
  onSelect,
  label = "Progress",
  reachable = "reached",
  variant = "plain",
  className,
}: {
  steps: StepperStep[];
  onSelect?: (id: string) => void;
  label?: string;
  reachable?: "reached" | "all";
  variant?: "plain" | "well";
  className?: string;
}) {
  const nav = useRef<HTMLElement>(null);
  const currentId = steps.find((s) => s.status === "current")?.id;
  useEffect(() => {
    const n = nav.current;
    const el = n?.querySelector<HTMLElement>('[aria-current="step"]');
    if (!n || !el || n.scrollWidth <= n.clientWidth) return;
    n.scrollTo({ left: Math.max(0, el.offsetLeft - (n.clientWidth - el.offsetWidth) / 2) });
  }, [currentId]);
  const well = variant === "well";
  return (
    <nav ref={nav} aria-label={label} className={cx("relative max-w-full overflow-x-auto ds-noscrollbar", className)}>
      <ol className={cx("flex w-max items-center gap-1", well && "rounded-full bg-paper-2 p-1")}>
        {steps.map((s, i) => {
          const current = s.status === "current";
          const done = s.status === "done";
          const locked = s.disabled || !onSelect || (reachable === "reached" && s.status === "upcoming");
          return (
            <li key={s.id} className="flex items-center gap-1">
              {i > 0 && (
                <span
                  aria-hidden
                  className={cx("h-px", well ? "w-3" : "w-5 sm:w-8", done || current ? "bg-fg/60" : "ds-stitch")}
                />
              )}
              <button
                type="button"
                disabled={locked}
                onClick={() => onSelect?.(s.id)}
                aria-current={current ? "step" : undefined}
                className={cx(
                  "flex items-center gap-2 rounded-full text-small whitespace-nowrap transition-colors duration-200",
                  well ? "h-10 pr-4 pl-1.5" : "h-9 px-3.5",
                  current && "bg-inverse text-on-inverse",
                  !current && (s.disabled || (reachable === "reached" && s.status === "upcoming") ? "text-fg-faint" : "text-fg"),
                  !current && !locked && (well ? "hover:bg-surface" : "hover:bg-paper-2"),
                )}
              >
                <span
                  className={cx(
                    "grid place-items-center rounded-full font-medium",
                    well ? "size-7 text-micro" : "size-5 text-[0.62rem]",
                    current
                      ? "bg-on-inverse/15"
                      : done
                        ? well
                          ? "bg-surface text-ok"
                          : "bg-paper-2"
                        : cx("border border-line-strong", well && "bg-surface"),
                  )}
                >
                  {done && !current ? <IconCheck size={well ? 12 : 11} strokeWidth={2.6} /> : (s.numeral ?? i + 1)}
                </span>
                {s.label}
                {s.marker}
                {s.srStatus && <span className="sr-only">{s.srStatus}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
