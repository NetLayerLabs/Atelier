"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useId, useState, type HTMLAttributes, type ReactNode } from "react";
import { IconChevronDown } from "./icons";
import { cx, DUR, EASE } from "./tokens";

/**
 * Disclosure: a row that expands to show detail (an RFQ email, a quote's evidence, "Why this number?").
 * Structure is fixed so the guided tour can drive it: the root element carries your `data-demo`, and its
 * FIRST CHILD is the toggle <button aria-expanded>. Controlled (`open` + `onOpenChange`) or uncontrolled.
 */
export function Disclosure({
  title,
  meta,
  leading,
  children,
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  variant = "card",
  className,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title: ReactNode;
  /** Right-aligned summary (a badge, a price, a count). */
  meta?: ReactNode;
  /** Left element (an icon, a flag, a swatch). */
  leading?: ReactNode;
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** card: bordered surface (default). row: hairline-separated list row. */
  variant?: "card" | "row";
  "data-demo"?: string;
}) {
  const [inner, setInner] = useState(defaultOpen);
  const open = openProp ?? inner;
  const id = useId();
  const set = (v: boolean) => {
    setInner(v);
    onOpenChange?.(v);
  };
  return (
    <div
      {...rest}
      className={cx(
        variant === "card" ? "rounded-panel border border-line bg-surface" : "border-b border-line",
        className,
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => set(!open)}
        className={cx(
          "flex min-h-14 w-full items-center gap-3 text-left transition-colors",
          variant === "card" ? "rounded-panel px-4 py-3 hover:bg-surface-muted sm:px-5" : "py-3 hover:text-fg",
        )}
      >
        {leading && <span className="shrink-0">{leading}</span>}
        <span className="min-w-0 flex-1 text-body font-medium text-fg">{title}</span>
        {meta && <span className="hidden shrink-0 items-center gap-2 sm:flex">{meta}</span>}
        <span
          aria-hidden
          className={cx(
            "grid size-8 shrink-0 place-items-center rounded-full bg-paper-2 text-fg transition-transform duration-300 ease-thread",
            open && "rotate-180",
          )}
        >
          <IconChevronDown size={16} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={id}
            key="panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: DUR.ui, ease: EASE }}
            className="overflow-hidden"
          >
            <div className={cx(variant === "card" ? "border-t border-line px-4 py-4 sm:px-5" : "pb-4")}>
              {meta && <div className="mb-3 flex flex-wrap gap-2 sm:hidden">{meta}</div>}
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
