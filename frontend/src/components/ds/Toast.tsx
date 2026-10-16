"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { create } from "zustand";
import { alertIcon, type AlertTone } from "./Alert";
import { IconClose } from "./icons";
import { cx, DUR, EASE, TONE } from "./tokens";

type ToastItem = { id: number; title: ReactNode; description?: ReactNode; tone: AlertTone; duration: number };

const useToasts = create<{ items: ToastItem[]; dismiss: (id: number) => void }>((set) => ({
  items: [],
  dismiss: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

let nextId = 1;

/**
 * Show a transient confirmation ("Tech pack saved", "RFQ sent to 3 mills"). Not for errors that need action -
 * use <InlineAlert> where the problem is. Returns the id; `duration: 0` keeps it until dismissed.
 */
export function toast(
  title: ReactNode,
  opts: { description?: ReactNode; tone?: AlertTone; duration?: number } = {},
): number {
  const id = nextId++;
  const item: ToastItem = { id, title, description: opts.description, tone: opts.tone ?? "ok", duration: opts.duration ?? 5000 };
  useToasts.setState((s) => ({ items: [...s.items.slice(-3), item] }));
  return id;
}

function ToastCard({ t }: { t: ToastItem }) {
  const dismiss = useToasts((s) => s.dismiss);
  useEffect(() => {
    if (!t.duration) return;
    const h = setTimeout(() => dismiss(t.id), t.duration);
    return () => clearTimeout(h);
  }, [t, dismiss]);
  const tone = TONE[t.tone === "info" ? "accent" : t.tone];
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 6, transition: { duration: DUR.micro } }}
      transition={{ duration: DUR.ui, ease: EASE }}
      className="pointer-events-auto flex w-full items-start gap-3 rounded-panel border border-line bg-surface p-3.5 pr-2.5 shadow-e3 sm:w-96"
    >
      <span aria-hidden className={cx("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", tone.soft, tone.text)}>
        {alertIcon(t.tone, 14)}
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className="text-small font-medium text-fg">{t.title}</p>
        {t.description && <p className="mt-0.5 text-micro text-fg-muted">{t.description}</p>}
      </div>
      <button
        type="button"
        onClick={() => dismiss(t.id)}
        aria-label="Dismiss"
        className="grid size-8 shrink-0 place-items-center rounded-full text-fg-faint hover:bg-paper-2 hover:text-fg"
      >
        <IconClose size={14} />
      </button>
    </motion.li>
  );
}

/** Mount once (app/layout.tsx does). Bottom-right on desktop, bottom-centre on mobile; clear of the tour box. */
export function ToastViewport() {
  const items = useToasts((s) => s.items);
  return (
    <ol
      aria-live="polite"
      aria-label="Notifications"
      className="pointer-events-none fixed inset-x-4 bottom-4 z-[90] flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6 sm:bottom-6"
    >
      <AnimatePresence initial={false}>
        {items.map((t) => (
          <ToastCard key={t.id} t={t} />
        ))}
      </AnimatePresence>
    </ol>
  );
}
