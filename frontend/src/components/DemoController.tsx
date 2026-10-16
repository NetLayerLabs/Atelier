"use client";

// Overlay for the guided tour: keyboard controls, ?demo=1 auto-start, a small progress indicator, the prompt when
// the tour waits on a human (a quote, a pre-order) or shows a service error, optional captions and a spotlight
// ring. The beat script itself lives in lib/demo.ts.

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { DEMO_BEATS, reducedMotion, useDemo } from "@/lib/demo";
import { IconButton, IconPlay, IconStop } from "./ds";
import { cx, ease } from "./ui";

function typingInField(target: EventTarget | null) {
  const t = target as HTMLElement | null;
  if (!t) return false;
  return t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
}

const INTERACTIVE = 'button, a[href], input, select, textarea, [role="button"]';
const CAPTION_BOTTOM = 80; // px above the viewport bottom (clear of the tour status box)
const CAPTION_GAP = 12; // px below the sticky header

type Slot = "bottom" | "top" | "hidden";

function overlapsControl(top: number, height: number, width: number): boolean {
  const left = (window.innerWidth - width) / 2;
  const right = left + width;
  const bottom = top + height;
  for (const el of document.querySelectorAll<HTMLElement>(INTERACTIVE)) {
    if (el.closest("[data-demo-caption]")) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > left && r.left < right && r.bottom > top && r.top < bottom) return true;
  }
  return false;
}

function headerBottom(): number {
  return Math.max(0, document.querySelector("header")?.getBoundingClientRect().bottom ?? 0);
}

/**
 * Presenter caption that never sits on top of a control: it takes the bottom band, moves to a band under the header
 * when a button / link / field is there, and hides while both bands are over controls (e.g. the hand-off panel's
 * Approve button). Re-checked on scroll, resize and as the page changes under the tour.
 */
function Caption({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ slot: Slot; top: number }>({ slot: "bottom", top: 0 });
  useEffect(() => {
    let raf = 0;
    const check = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const box = ref.current?.firstElementChild?.getBoundingClientRect();
        if (!box) return;
        const top = headerBottom() + CAPTION_GAP;
        const slot: Slot = !overlapsControl(window.innerHeight - CAPTION_BOTTOM - box.height, box.height, box.width)
          ? "bottom"
          : !overlapsControl(top, box.height, box.width)
            ? "top"
            : "hidden";
        setPlace((cur) => (cur.slot === slot && cur.top === top ? cur : { slot, top }));
      });
    };
    check();
    const id = setInterval(check, 400);
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(id);
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, []);
  return (
    <motion.div
      ref={ref}
      data-demo-caption
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: place.slot === "hidden" ? 0 : 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease }}
      className="pointer-events-none fixed inset-x-0 z-50 flex justify-center px-4"
      style={place.slot === "top" ? { top: place.top } : { bottom: CAPTION_BOTTOM }}
      aria-live="polite"
      aria-hidden={place.slot === "hidden" || undefined}
    >
      <p className="max-w-3xl rounded-card border border-line bg-surface/90 px-6 py-3.5 text-center text-lg leading-snug font-light tracking-[-0.02em] text-fg shadow-e3 backdrop-blur-md sm:text-xl">
        {text}
      </p>
    </motion.div>
  );
}

export function DemoController() {
  const status = useDemo((s) => s.status);
  const beat = useDemo((s) => s.beat);
  const label = useDemo((s) => s.label);
  const caption = useDemo((s) => s.caption);
  const captions = useDemo((s) => s.captions);
  const message = useDemo((s) => s.message);
  const active = status !== "idle";

  // ?demo=1 auto-starts (after the first paint, so the dashboard is mounted); &captions=1 shows captions.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("captions") === "1") useDemo.setState({ captions: true });
    if (q.get("demo") !== "1") return;
    const t = setTimeout(() => useDemo.getState().start(), 600);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.isTrusted || e.metaKey || e.ctrlKey || e.altKey) return; // ignore the demo's own synthetic keys
      const d = useDemo.getState();
      const on = d.status !== "idle";
      if (e.shiftKey && (e.key === "D" || e.key === "d") && !typingInField(e.target)) {
        e.preventDefault();
        if (on) d.stop();
        else d.start();
        return;
      }
      if (!on || typingInField(e.target)) return;
      if (e.key === "Escape") {
        // Esc closes the inference panel first if it's open; a second Esc exits the demo.
        if (document.querySelector('[aria-label="Inference statistics"]')) return;
        e.preventDefault();
        d.stop();
      } else if (e.key === " " || e.code === "Space") {
        e.preventDefault();
        d.togglePause();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        d.next();
      } else if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        d.toggleCaptions();
      } else if ((e.key === "r" || e.key === "R") && d.status === "blocked") {
        e.preventDefault();
        d.retry();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <Spotlight />
      <AnimatePresence>{active && captions && caption && <Caption key={caption} text={caption} />}</AnimatePresence>
      <AnimatePresence>
        {(active || message) && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.35, ease }}
            className="fixed bottom-4 left-4 z-50 max-w-[calc(100vw-2rem)]"
          >
            <div
              role="status"
              className="group rounded-[22px] border border-line bg-surface px-4 py-2.5 text-[0.7rem] font-medium text-fg-faint shadow-e3"
            >
              {active && (
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden
                    className={cx(
                      "size-1.5 rounded-full",
                      status === "running" && "pulse-dot bg-accent",
                      status === "paused" && "bg-fg-faint",
                      status === "blocked" && "bg-bad",
                      status === "waiting" && "pulse-dot bg-ok",
                      status === "done" && "bg-ok",
                    )}
                  />
                  <span className="tabular whitespace-nowrap">
                    Tour{" "}
                    <span className="text-fg-muted">
                      {String(Math.min(beat + 1, DEMO_BEATS.length)).padStart(2, "0")}/{DEMO_BEATS.length}
                    </span>
                  </span>
                  <span className="max-w-[14rem] truncate text-fg-muted">
                    {status === "paused"
                      ? "Paused"
                      : status === "done"
                        ? "Finished"
                        : status === "waiting"
                          ? `Waiting · ${label}`
                          : label}
                  </span>
                  <span className="flex gap-0.5" aria-hidden>
                    {DEMO_BEATS.map((b, i) => (
                      <span
                        key={b.id}
                        className={cx(
                          "h-1 w-1.5 rounded-full",
                          i < beat || status === "done" ? "bg-accent/70" : i === beat ? "bg-accent" : "bg-line-strong",
                        )}
                      />
                    ))}
                  </span>
                </div>
              )}
              {message && (
                <p
                  className={cx(
                    "max-w-md font-sans text-xs leading-snug break-words",
                    status === "blocked" ? "text-bad" : status === "waiting" ? "text-fg" : "text-fg-muted",
                    active && "mt-2",
                  )}
                >
                  {message}
                </p>
              )}
              {active && (
                <p
                  className={cx(
                    "mt-1.5 tracking-[0.08em] text-fg-faint/80 transition-opacity duration-300",
                    status === "paused" || status === "blocked" || status === "waiting" || status === "done"
                      ? "opacity-100"
                      : "hidden opacity-0 group-hover:block group-hover:opacity-100",
                  )}
                >
                  {status === "blocked" ? "R retry · → skip · Esc exit" : "Space pause · → next · C captions · Esc exit"}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/** Header control: starts the guided tour, or exits it while it runs (round; Shift+D also toggles). */
export function DemoButton({ className }: { className?: string }) {
  const active = useDemo((s) => s.status !== "idle");
  const start = useDemo((s) => s.start);
  const stop = useDemo((s) => s.stop);
  return (
    <IconButton
      onClick={() => (active ? stop() : start())}
      label={active ? "Exit the tour (Esc)" : "Guided tour through the real app (Shift+D)"}
      aria-pressed={active}
      variant={active ? "solid" : "outline"}
      dot={active ? "accent" : false}
      dotLive={active}
      className={className}
    >
      {active ? <IconStop size={14} /> : <IconPlay size={14} />}
    </IconButton>
  );
}

/** An ink ring that follows the element the tour is pointing at. */

function Spotlight() {
  const selector = useDemo((s) => s.spotlight);
  const [rect, setRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null);

  useEffect(() => {
    if (!selector) return;
    let raf = 0;
    const tick = () => {
      const node = document.querySelector(selector);
      const r = node?.getBoundingClientRect();
      setRect((prev) => {
        if (!r || r.width === 0) return null;
        const next = { top: r.top - 8, left: r.left - 8, width: r.width + 16, height: r.height + 16 };
        return prev &&
          Math.abs(prev.top - next.top) < 0.5 &&
          Math.abs(prev.left - next.left) < 0.5 &&
          Math.abs(prev.width - next.width) < 0.5 &&
          Math.abs(prev.height - next.height) < 0.5
          ? prev
          : next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      setRect(null);
    };
  }, [selector]);

  const still = reducedMotion();
  return (
    <AnimatePresence>
      {selector && rect && (
        <motion.div
          aria-hidden
          initial={{ opacity: 0, scale: still ? 1 : 1.03 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4, ease }}
          className="pointer-events-none fixed z-50 rounded-panel border-2 border-accent shadow-[0_0_0_6px_var(--accent-soft),0_18px_48px_-12px_var(--accent-soft)]"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
        />
      )}
    </AnimatePresence>
  );
}
