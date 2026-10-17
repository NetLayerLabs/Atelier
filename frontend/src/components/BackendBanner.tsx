"use client";

import { AnimatePresence, motion } from "framer-motion";
import { apiBaseLabel } from "@/lib/api";
import { useHealth } from "@/lib/health";
import { useAtelier } from "@/lib/store";
import { Badge, IconAlert, Spinner } from "./ds";
import { DUR, EASE } from "./ds/tokens";

/**
 * The band under the app bar: loud when an endpoint is the local test double (FAKE upstream), and when the
 * backend itself is unreachable (with the command to start it). Never shown otherwise.
 */
export function BackendBanner() {
  const down = useAtelier((s) => s.backendDown);
  const health = useHealth((s) => s.health);
  const fakes = health.kind === "ok" ? health.data.services.filter((s) => s.fake).map((s) => s.name) : [];
  const motionProps = {
    initial: { height: 0, opacity: 0 },
    animate: { height: "auto", opacity: 1 },
    exit: { height: 0, opacity: 0 },
    transition: { duration: DUR.ui, ease: EASE },
  } as const;
  return (
    <AnimatePresence>
      {!down && fakes.length > 0 && (
        <motion.div key="fake" role="alert" {...motionProps} className="overflow-hidden">
          <div className="mx-auto max-w-[1400px] px-4 pt-2 sm:px-8 lg:px-12">
            <p className="flex flex-col gap-2 rounded-panel border border-bad/40 bg-bad-soft px-4 py-3 text-small text-fg-muted sm:flex-row sm:items-center sm:gap-3">
              <Badge status="fake" className="self-start sm:self-auto" />
              <span>
                <span className="font-medium text-fg">{fakes.join(", ")}</span> {fakes.length === 1 ? "points" : "point"} at
                the local test double. Output from {fakes.length === 1 ? "it" : "them"} is not from a real service.
              </span>
            </p>
          </div>
        </motion.div>
      )}

      {down && (
        <motion.div key="down" role="alert" {...motionProps} className="overflow-hidden">
          <div className="mx-auto max-w-[1400px] px-4 pt-2 sm:px-8 lg:px-12">
            <div className="flex flex-col gap-3 rounded-panel border border-bad/40 bg-bad-soft px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-fg-muted">
                <span aria-hidden className="grid size-7 place-items-center rounded-full bg-surface text-bad">
                  <IconAlert size={14} />
                </span>
                <span className="font-medium text-bad">Backend unreachable</span>
                <span>at</span>
                <span className="font-mono text-micro break-all text-fg">{apiBaseLabel()}</span>
                <span className="inline-flex items-center gap-1.5">
                  <Spinner size={11} /> retrying automatically
                </span>
              </p>
              <p className="text-micro text-fg-muted">
                Start it with{" "}
                <code className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-micro break-all text-fg">
                  cd backend &amp;&amp; uv run uvicorn app.main:app --port 8787
                </code>
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
