"use client";

// Small client hooks the landing's motion is built on: the reduced-motion preference without a hydration mismatch,
// pausing CSS loops that nobody can see, and the one heartbeat that is allowed to move on its own (a real
// GET /api/health response, never a timer of its own).

import { useEffect, useRef, useSyncExternalStore, type RefObject } from "react";
import type { HealthResponse } from "@/lib/api";
import { useHealth } from "@/lib/health";

const RM_QUERY = "(prefers-reduced-motion: reduce)";
const subscribeRM = (cb: () => void) => {
  const mq = window.matchMedia(RM_QUERY);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};

/**
 * Reduced-motion preference that is `false` during SSR and hydration (no mismatch), then follows the OS live.
 * Use it to pick a transition (INSTANT vs EASE / DUR), never to change rendered markup.
 */
export function useReducedMotionSafe(): boolean {
  return useSyncExternalStore(
    subscribeRM,
    () => window.matchMedia(RM_QUERY).matches,
    () => false,
  );
}

/**
 * Sets `data-paused` on the element while it is off-screen or the tab is hidden, and removes it otherwise. CSS
 * animations inside a paused element hold still (globals.css: `[data-paused] *`); style anything else from the
 * attribute, e.g. `in-data-paused:[animation-play-state:paused]`. Writes the DOM directly: no re-renders.
 */
export function useInViewPause(ref: RefObject<Element | null>, opts?: { rootMargin?: string }): void {
  const rootMargin = opts?.rootMargin ?? "0px";

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    let onScreen = true;
    const apply = () => {
      const paused = !onScreen || document.visibilityState === "hidden";
      if (paused) node.setAttribute("data-paused", "");
      else node.removeAttribute("data-paused");
    };
    const io =
      typeof IntersectionObserver === "undefined"
        ? undefined
        : new IntersectionObserver(
            (entries) => {
              onScreen = entries[entries.length - 1].isIntersecting;
              apply();
            },
            { rootMargin },
          );
    io?.observe(node);
    document.addEventListener("visibilitychange", apply);
    apply();
    return () => {
      io?.disconnect();
      document.removeEventListener("visibilitychange", apply);
      node.removeAttribute("data-paused");
    };
  }, [ref, rootMargin]);
}

/**
 * Calls `cb` each time a real GET /api/health response replaces the previous one and reports `ok`, while the tab is
 * visible: the landing's one honest heartbeat. No timers of its own; it follows the header's shared poll (about
 * every 10 s). It fires under reduced motion too, so keep whatever it triggers static there.
 */
export function useHealthBeat(cb: (data: HealthResponse) => void): void {
  const cbRef = useRef(cb);
  useEffect(() => {
    cbRef.current = cb;
  });

  useEffect(
    () =>
      useHealth.subscribe((state, prev) => {
        if (state.health === prev.health || state.health.kind !== "ok") return;
        if (document.visibilityState !== "visible") return;
        cbRef.current(state.health.data);
      }),
    [],
  );
}
