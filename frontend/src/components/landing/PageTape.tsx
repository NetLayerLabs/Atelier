"use client";

import { motion, useMotionValueEvent, useScroll, useSpring, useTransform } from "framer-motion";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";
import { cx, NEEDLE_SPRING } from "@/components/ds";
import { useDemo } from "@/lib/demo";
import { LANDING_CONTENTS } from "./Hero";
import { useReducedMotionSafe } from "./motion";

/*
 * The page tape: from xl up, a tailor's tape in the right-hand gutter that reads your progress through the landing.
 * Sections 01-06 are marked where they really start (in proportion to their length), an ink pointer rides it with
 * the scroll, smoothed like a needle, and the track above the pointer inks in. It fades in once the hero has gone
 * and out as the closing CTA arrives. Decorative and client-only: nothing in the server HTML, hidden from assistive
 * tech (the "On this page" list and the Menu are the navigation), no pointer events.
 */

/** Where the tape reads the page: a section counts as reached once its top passes this fraction of the viewport. */
const READ = 0.33;

/** Tailwind's xl breakpoint: below it the gutter is too narrow for the tape. */
const XL = "(min-width: 80rem)";
const subscribeXL = (cb: () => void) => {
  const mq = window.matchMedia(XL);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};

/** Measured from the page on mount and on resize, never per frame. */
type Geometry = {
  /** The tape's box: 52vh tall and centred, on whole pixels so the ticks and the pointer stay crisp. */
  top: number;
  height: number;
  /** Where the closing CTA starts, as a fraction of the landing: the end of the tape. */
  end: number;
  /** Where each section starts on the tape (0-1). */
  marks: number[];
  /** Landing progress where the tape fades in (the hero leaving) and out (the closing CTA arriving). */
  fade: [number, number, number, number];
};

function measure(root: HTMLElement): Geometry | null {
  const box = root.getBoundingClientRect();
  const vh = document.documentElement.clientHeight;
  if (box.height <= vh) return null;
  const at = (el: Element | null | undefined, edge: "top" | "bottom") =>
    el ? (el.getBoundingClientRect()[edge] - box.top) / box.height : undefined;

  const end = at(document.getElementById("landing-cta-title")?.closest("section"), "top") ?? 1;
  const marks = LANDING_CONTENTS.map(({ id }) => (at(document.getElementById(id), "top") ?? NaN) / end);
  const heroEnd = at(document.getElementById("landing-hero"), "bottom") ?? 0;
  // Progress is the reading line's place in the landing, so an edge sits at fraction f of the viewport when
  // progress = edge + (READ - f) * one viewport. In: the hero's foot rises from 36% to 14% (clear of the tape's top
  // at 24%). Out: the CTA's top rises from 95% to 70%.
  const v = vh / box.height;
  const fade: Geometry["fade"] = [
    heroEnd + (READ - 0.36) * v,
    heroEnd + (READ - 0.14) * v,
    end + (READ - 0.95) * v,
    end + (READ - 0.7) * v,
  ];
  if (!(fade[1] < fade[2])) return null; // a landing shorter than a few screens: nothing to measure

  const height = Math.round(vh * 0.52);
  return { top: Math.round((vh - height) / 2), height, end, marks, fade };
}

const same = (a: Geometry | null, b: Geometry) =>
  !!a &&
  a.top === b.top &&
  a.height === b.height &&
  Math.abs(a.end - b.end) < 1e-4 &&
  a.marks.every((m, i) => Math.abs(m - b.marks[i]) < 1e-4) &&
  a.fade.every((f, i) => Math.abs(f - b.fade[i]) < 1e-4);

/** The section the tape is in: the last mark at or above `t` (-1 before 01). */
function sectionAt(t: number, marks: number[]) {
  let i = -1;
  marks.forEach((m, k) => {
    if (t >= m) i = k;
  });
  return i;
}

/**
 * Rendered once by Landing, at the end of its root: `rootRef` is the landing's root element. Nothing below xl, nothing
 * on the server or during hydration, and it steps aside while the guided tour runs.
 */
export function PageTape({ rootRef }: { rootRef: RefObject<HTMLDivElement | null> }) {
  const wide = useSyncExternalStore(subscribeXL, () => window.matchMedia(XL).matches, () => false);
  const touring = useDemo((s) => s.status !== "idle");
  return wide ? <Tape rootRef={rootRef} touring={touring} /> : null;
}

function Tape({ rootRef, touring }: { rootRef: RefObject<HTMLDivElement | null>; touring: boolean }) {
  const reduce = useReducedMotionSafe();
  const [geo, setGeo] = useState<Geometry | null>(null);
  const [active, setActive] = useState(-1);
  const geoRef = useRef<Geometry | null>(null);
  const activeRef = useRef(-1);

  // 0 when the reading line meets the top of the hero, 1 when it leaves the end of the closing CTA.
  const { scrollYProgress } = useScroll({ target: rootRef, offset: [[0, READ], [1, READ]] });
  // The pointer is a needle: it follows the scroll on the needle spring, or exactly under reduced motion.
  const spring = useSpring(scrollYProgress, NEEDLE_SPRING);
  const needle = reduce ? scrollYProgress : spring;

  const end = geo?.end ?? 1;
  const height = geo?.height ?? 0;
  const at = useTransform(needle, (p) => Math.min(1, Math.max(0, p / end)));
  const y = useTransform(at, (t) => Math.round(t * height));
  const opacity = useTransform(scrollYProgress, geo?.fade ?? [0, 1, 2, 3], [0, 1, 1, 0]);

  // The current section's numeral and tick go to ink when the pointer reaches them; state changes only on a new index.
  const sync = useCallback((p: number) => {
    const g = geoRef.current;
    if (!g) return;
    const i = sectionAt(p / g.end, g.marks);
    if (i === activeRef.current) return;
    activeRef.current = i;
    setActive(i);
  }, []);
  useMotionValueEvent(needle, "change", sync);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const update = () => {
      const g = measure(root);
      if (!g || same(geoRef.current, g)) return;
      geoRef.current = g;
      setGeo(g);
      sync(needle.get());
    };
    // The observer's first report is the initial measurement; after that, only real reflows and resizes.
    const ro = new ResizeObserver(update);
    ro.observe(root);
    for (const { id } of LANDING_CONTENTS) {
      const el = document.getElementById(id);
      if (el) ro.observe(el);
    }
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [rootRef, needle, sync]);

  if (!geo) return null;

  return (
    <div
      aria-hidden
      className={cx(
        "pointer-events-none fixed right-[12px] z-30 w-[30px] select-none print:hidden",
        "transition-opacity duration-500 ease-thread",
        touring && "opacity-0",
      )}
      style={{ top: geo.top, height: geo.height }}
    >
      <motion.div className="relative h-full" style={{ opacity }}>
        {/* the tape: a hairline track, a faint tick every 6px and a short cap at either end */}
        <span className="absolute inset-y-0 left-[23px] w-px bg-line-strong" />
        <span className="absolute inset-y-0 left-[20px] w-[3px] bg-[repeating-linear-gradient(to_bottom,var(--tick-faint)_0_1px,transparent_1px_6px)]" />
        <span className="absolute top-0 left-[18px] h-px w-[6px] bg-[var(--tick)]" />
        <span className="absolute bottom-0 left-[18px] h-px w-[6px] bg-[var(--tick)]" />

        {/* read so far: the track inks in down to the pointer */}
        <motion.span className="absolute inset-y-0 left-[23px] w-px origin-top bg-fg" style={{ scaleY: at }} />

        {/* the six sections, where they really start */}
        {geo.marks.map((m, i) =>
          Number.isFinite(m) ? (
            <span key={LANDING_CONTENTS[i].id} className="absolute inset-x-0 h-px" style={{ top: Math.round(m * geo.height) }}>
              <span
                className={cx(
                  "absolute right-[16px] -translate-y-1/2 font-mono text-micro leading-none tabular transition-colors duration-300 ease-thread",
                  i === active ? "text-fg" : "text-fg-dim",
                )}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <span
                className={cx(
                  "absolute top-0 left-[17px] h-px w-[6px] transition-colors duration-300 ease-thread",
                  i === active ? "bg-fg" : "bg-[var(--tick)]",
                )}
              />
            </span>
          ) : null,
        )}

        {/* the pointer: TapeMeasure's ink triangle and hairline, turned to read a vertical tape */}
        <motion.span className="absolute inset-x-0 top-0 h-px" style={{ y }}>
          <span className="absolute top-0 left-[15px] h-px w-[9px] bg-fg" />
          <span className="absolute -top-[4.5px] left-[24px] h-0 w-0 border-y-[5px] border-r-[6px] border-y-transparent border-r-current text-fg" />
        </motion.span>
      </motion.div>
    </div>
  );
}
