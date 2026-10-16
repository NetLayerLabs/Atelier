"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { IconButton } from "./Button";
import { IconClose } from "./icons";
import { cx, DUR, EASE } from "./tokens";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Esc to close, Tab trapped inside, body scroll locked, focus restored on close. */
function useDialogBehaviour(open: boolean, panel: RefObject<HTMLElement | null>, onClose: () => void, initialFocus?: RefObject<HTMLElement | null>) {
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const t = setTimeout(() => {
      const target = initialFocus?.current ?? panel.current?.querySelector<HTMLElement>(FOCUSABLE) ?? panel.current;
      target?.focus();
    }, 30);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
      } else if (e.key === "Tab" && panel.current) {
        const els = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null);
        if (els.length === 0) return;
        const first = els[0];
        const last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      before?.focus?.();
    };
  }, [open, panel, initialFocus]);
}

type DialogProps = {
  open: boolean;
  onClose: () => void;
  /** Visible title; also the dialog's accessible name unless `ariaLabel` is given. */
  title?: ReactNode;
  /** Eyebrow above the title. */
  eyebrow?: ReactNode;
  description?: ReactNode;
  /** Accessible name when there is no visible title (the tour looks some dialogs up by it). */
  ariaLabel?: string;
  children?: ReactNode;
  /** Sticky footer (actions). */
  footer?: ReactNode;
  /** Extra controls next to the close button (e.g. Refresh). */
  headerActions?: ReactNode;
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
  /** Hide the close button (e.g. a blocking sign-in that has its own "Not now"). */
  hideClose?: boolean;
};

function Head({ id, title, eyebrow, description, onClose, headerActions, hideClose }: DialogProps & { id: string }) {
  if (!title && !eyebrow && hideClose && !headerActions) return null;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow}
        {title && (
          <h2 id={id} className={cx("text-display-m text-fg", eyebrow ? "mt-3" : undefined)}>
            {title}
          </h2>
        )}
        {description && <p className="mt-2 text-small text-fg-muted">{description}</p>}
      </div>
      <div className="-mt-1 -mr-1 flex shrink-0 items-center gap-1">
        {headerActions}
        {!hideClose && (
          <IconButton label="Close" variant="soft" onClick={onClose}>
            <IconClose size={16} />
          </IconButton>
        )}
      </div>
    </div>
  );
}

/**
 * Centered modal dialog (sign-in, confirmations). Max 30rem wide; on mobile it sits near the bottom as a sheet.
 * Portaled to <body> (so sticky/blurred ancestors can't trap it).
 */
export function Modal(props: DialogProps & { size?: "sm" | "md" | "lg" }) {
  const { open, onClose, ariaLabel, children, footer, className, size = "sm", initialFocus } = props;
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const reduce = useReducedMotion();
  useDialogBehaviour(open, panel, onClose, initialFocus);
  if (typeof document === "undefined") return null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[100] flex items-end justify-center p-3 sm:items-center sm:p-6">
          <motion.div
            aria-hidden
            className="absolute inset-0 bg-[var(--scrim)] backdrop-blur-[6px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            aria-labelledby={ariaLabel ? undefined : props.title ? id : undefined}
            tabIndex={-1}
            initial={{ opacity: 0, y: reduce ? 0 : 16, scale: reduce ? 1 : 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: reduce ? 0 : 8 }}
            transition={{ duration: DUR.ui, ease: EASE }}
            className={cx(
              "relative flex max-h-[calc(100dvh-1.5rem)] w-full flex-col overflow-hidden rounded-sheet border border-line bg-surface shadow-e3 outline-none",
              size === "sm" && "max-w-[30rem]",
              size === "md" && "max-w-[40rem]",
              size === "lg" && "max-w-[56rem]",
              className,
            )}
          >
            <div className="overflow-y-auto p-6 sm:p-8">
              <Head {...props} id={id} />
              {children && <div className={cx(props.title || props.eyebrow ? "mt-6" : undefined)}>{children}</div>}
            </div>
            {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-6 py-4 sm:px-8">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

/**
 * Slide-over sheet. `side="right"`: a full-height panel up to 36rem (Inference stats, a quote's evidence).
 * `side="bottom"`: a mobile-style sheet with a grab bar. Portaled to <body>.
 */
export function Sheet(props: DialogProps & { side?: "right" | "bottom"; width?: string }) {
  const { open, onClose, ariaLabel, children, footer, className, side = "right", width = "36rem", initialFocus } = props;
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const reduce = useReducedMotion();
  useDialogBehaviour(open, panel, onClose, initialFocus);
  if (typeof document === "undefined") return null;
  const right = side === "right";
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[80]">
          <motion.div
            aria-hidden
            className="absolute inset-0 bg-[var(--scrim)] backdrop-blur-[4px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            aria-labelledby={ariaLabel ? undefined : props.title ? id : undefined}
            tabIndex={-1}
            initial={reduce ? { opacity: 0 } : right ? { x: "100%" } : { y: "100%" }}
            animate={reduce ? { opacity: 1 } : right ? { x: 0 } : { y: 0 }}
            exit={reduce ? { opacity: 0 } : right ? { x: "100%" } : { y: "100%" }}
            transition={{ duration: DUR.sheet, ease: EASE }}
            style={right ? { maxWidth: width } : undefined}
            className={cx(
              "absolute flex flex-col bg-surface shadow-e3 outline-none",
              right
                ? "top-0 right-0 h-full w-full border-l border-line sm:top-2 sm:right-2 sm:h-[calc(100%-1rem)] sm:rounded-sheet sm:border"
                : "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-sheet border-t border-line",
              className,
            )}
          >
            {!right && <span aria-hidden className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-line-strong" />}
            <div className="shrink-0 px-6 pt-6 pb-5 sm:px-7">
              <Head {...props} id={id} />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-8 sm:px-7">{children}</div>
            {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-6 py-4 sm:px-7">{footer}</div>}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
