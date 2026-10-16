"use client";

import { motion } from "framer-motion";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx, DUR, EASE } from "./tokens";

type Option<T extends string> = { value: T; label: ReactNode; disabled?: boolean; title?: string };

function arrowNav<T extends string>(e: KeyboardEvent, options: Option<T>[], value: T, onChange: (v: T) => void, refs: (HTMLButtonElement | null)[]) {
  const enabled = options.filter((o) => !o.disabled);
  const i = enabled.findIndex((o) => o.value === value);
  let next: number | undefined;
  if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % enabled.length;
  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + enabled.length) % enabled.length;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = enabled.length - 1;
  if (next === undefined) return;
  e.preventDefault();
  const v = enabled[next].value;
  onChange(v);
  refs[options.findIndex((o) => o.value === v)]?.focus();
}

/**
 * Segmented control: 2–4 mutually exclusive options in a grey well; the active one is an ink pill that slides.
 * Use for view switches (Concepts / Collection, Light / Dark, units). Keyboard: arrows, Home, End.
 */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  label,
  className,
}: {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  /** Accessible name for the group. */
  label: string;
  className?: string;
}) {
  const id = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cx("inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-paper-2 p-1 ds-noscrollbar", className)}
    >
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => arrowNav(e, options, value, onChange, refs.current)}
            className={cx(
              "relative isolate shrink-0 rounded-full font-medium whitespace-nowrap transition-colors duration-200 disabled:opacity-40",
              size === "sm" ? "h-7 px-3 text-micro" : "h-9 px-4 text-small",
              on ? "text-on-inverse" : "text-fg-muted hover:text-fg",
            )}
          >
            {on && (
              <motion.span
                layoutId={`seg-${id}`}
                aria-hidden
                className="absolute inset-0 -z-10 rounded-full bg-inverse"
                transition={{ duration: DUR.ui, ease: EASE }}
              />
            )}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export type TabItem<T extends string> = Option<T> & { count?: number; content?: ReactNode };

/**
 * Underline tabs for switching panels inside a card (Tech pack: BOM / Measurements / Construction).
 * Renders the tab list and, when items carry `content`, the active panel. Keyboard: arrows, Home, End.
 * The list scrolls horizontally on mobile rather than wrapping.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className,
  panelClassName,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
  panelClassName?: string;
}) {
  const id = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const active = items.find((t) => t.value === value);
  return (
    <div className={className}>
      <div role="tablist" aria-label={label} className="flex gap-6 overflow-x-auto border-b border-line ds-noscrollbar">
        {items.map((t, i) => {
          const on = t.value === value;
          return (
            <button
              key={t.value}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${id}-tab-${t.value}`}
              aria-selected={on}
              aria-controls={t.content !== undefined ? `${id}-panel-${t.value}` : undefined}
              tabIndex={on ? 0 : -1}
              disabled={t.disabled}
              onClick={() => onChange(t.value)}
              onKeyDown={(e) => arrowNav(e, items, value, onChange, refs.current)}
              className={cx(
                "relative flex min-h-11 shrink-0 items-center gap-2 text-small whitespace-nowrap transition-colors disabled:opacity-40",
                on ? "font-medium text-fg" : "text-fg-muted hover:text-fg",
              )}
            >
              {t.label}
              {t.count != null && (
                <span className={cx("tabular rounded-full px-1.5 text-micro", on ? "bg-inverse text-on-inverse" : "bg-paper-2 text-fg-muted")}>
                  {t.count}
                </span>
              )}
              {on && (
                <motion.span
                  layoutId={`tab-${id}`}
                  aria-hidden
                  className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-fg"
                  transition={{ duration: DUR.ui, ease: EASE }}
                />
              )}
            </button>
          );
        })}
      </div>
      {active?.content !== undefined && (
        <div role="tabpanel" id={`${id}-panel-${active.value}`} aria-labelledby={`${id}-tab-${active.value}`} className={cx("pt-6", panelClassName)}>
          {active.content}
        </div>
      )}
    </div>
  );
}
