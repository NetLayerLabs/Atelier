"use client";

// The app bar (every page), laid out like Scenar's: the mark + wordmark and the black "+ Menu" pill on the left;
// on the right a small Studio | ● Workspace toggle (desktop), the black "Launch studio ↗" pill, the System pill
// (opens the services popover), and small round tour / theme buttons (both also live in the Menu).
// It also polls GET /api/health and publishes it (lib/health) for the landing's status strip.

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";
import { getHealth, isNetworkError, type HealthResponse } from "@/lib/api";
import { useHealth, type HealthState } from "@/lib/health";
import { useAtelier } from "@/lib/store";
import { useUi } from "@/lib/ui";
import { DemoButton } from "./DemoController";
import { AtelierLockup, AtelierMark, Badge, Button, Chip, Eyebrow, IconArrowUpRight, IconGrid, IconRefresh, SetupHint, StatusDot, ThemeToggle, type BadgeStatus, type Tone } from "./ds";
import { cx, DUR, EASE } from "./ds/tokens";
import { InferenceButton } from "./Inference";
import { MenuButton } from "./Menu";
import { scrollToId } from "./ui";
import { useWorkspaceStatus } from "./workspace/WorkspaceGate";

export function Header({ onStartOver }: { onStartOver: () => void }) {
  const setHealth = useHealth((s) => s.setHealth);
  const health = useHealth((s) => s.health);
  const setBackendDown = useAtelier((s) => s.setBackendDown);
  const hasProgress = useAtelier((s) => s.analyze.status !== "idle");

  const check = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealth({ kind: "ok", data });
      setBackendDown(false);
    } catch (err) {
      const down = isNetworkError(err);
      setHealth({ kind: down ? "down" : "error" });
      setBackendDown(down);
    }
  }, [setBackendDown, setHealth]);

  useEffect(() => {
    let alive = true;
    const run = () => alive && void check();
    run();
    const id = setInterval(run, 10_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [check]);

  // Re-check promptly when an API call reports the backend is down.
  const backendDown = useAtelier((s) => s.backendDown);
  useEffect(() => {
    if (!backendDown) return;
    const id = setInterval(() => void check(), 3_000);
    return () => clearInterval(id);
  }, [backendDown, check]);

  return (
    <header className="sticky top-0 z-40 h-[4.5rem]">
      {/* Veil: blurs what scrolls underneath and fades out downward (no hard band), as on Scenar. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -bottom-3 bg-[var(--veil)] backdrop-blur-[14px] [mask-image:linear-gradient(to_bottom,#000_45%,transparent)]"
      />
      <div className="relative flex h-full items-center justify-between gap-2 px-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
          <button
            type="button"
            onClick={onStartOver}
            className="group/brand flex h-10 items-center gap-2 rounded-full pr-1 text-fg"
            aria-label="Atelier - back to start"
          >
            {/* The wrappers own the breakpoint display: the logo's own `inline-block` beat `hidden` on phones. */}
            <span className="inline-flex md:hidden">
              <AtelierMark size={30} />
            </span>
            <span className="hidden md:inline-flex">
              <AtelierLockup height={26} />
            </span>
          </button>
          <MenuButton onStartOver={onStartOver} hasProgress={hasProgress} onRefreshHealth={check} />
        </div>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <PoweredBy health={health} className="mr-2 hidden text-micro text-fg-faint 2xl:inline" />
          <AnimatePresence>
            {hasProgress && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="hidden xl:block">
                <Button variant="ghost" size="sm" onClick={onStartOver}>
                  Start over
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
          <PlacesToggle />
          <LaunchStudio />
          <InferenceButton />
          <HealthIndicator health={health} onRefresh={check} />
          <DemoButton className="max-sm:hidden" />
          <ThemeToggle className="max-sm:hidden" />
        </div>
      </div>
    </header>
  );
}

/** Scenar's "Launch app ↗": a black pill with a round white arrow badge; icon-only below 768px. */
function LaunchStudio() {
  const pathname = usePathname();
  return (
    <Link
      href="/#chapter-trend"
      onClick={(e) => {
        if (pathname !== "/") return;
        e.preventDefault();
        scrollToId("chapter-trend");
      }}
      aria-label="Launch studio"
      title="Go to the studio (chapter I)"
      className="group/launch inline-flex h-9 items-center gap-2 rounded-full bg-inverse p-1 text-on-inverse transition-[transform,background-color] duration-300 ease-thread hover:-translate-y-px hover:bg-inverse-hover active:scale-[0.97] md:h-10 md:pl-4"
    >
      <span aria-hidden className="hidden text-[0.7rem] font-medium whitespace-nowrap md:inline">
        Launch studio
      </span>
      <span
        aria-hidden
        className="grid size-7 place-items-center rounded-full bg-on-inverse text-inverse transition-transform duration-500 ease-thread group-hover/launch:rotate-45 md:size-8"
      >
        <IconArrowUpRight size={14} strokeWidth={2.4} />
      </span>
    </Link>
  );
}

/**
 * Desktop: the two places as Scenar's small segmented switch - "Studio | ● Workspace". The ink thumb marks where
 * you are; the dot on Workspace shows its setup state (amber: still needs something, green: ready).
 */
function PlacesToggle() {
  const pathname = usePathname();
  const st = useWorkspaceStatus(30_000);
  const onWorkspace = pathname?.startsWith("/workspace");
  const item = "relative inline-flex h-full items-center gap-1.5 rounded-full px-3.5 text-[0.68rem] font-medium whitespace-nowrap transition-colors";
  return (
    <nav aria-label="Places" className="mr-1 hidden h-[2.1rem] items-stretch rounded-full bg-paper-2 p-[3px] lg:flex">
      {/* On the dashboard it scrolls to chapter I; elsewhere it goes back to the studio. */}
      <Link
        href="/#chapter-trend"
        onClick={(e) => {
          if (pathname !== "/") return;
          e.preventDefault();
          scrollToId("chapter-trend");
        }}
        title="Go to the studio (chapter I)"
        aria-current={!onWorkspace ? "page" : undefined}
        className={cx(item, !onWorkspace ? "bg-inverse text-on-inverse shadow-[0_6px_16px_-10px_rgba(0,0,0,0.6)]" : "text-fg-muted hover:text-fg")}
      >
        Studio
      </Link>
      <Link
        href="/workspace"
        title={st && !st.ready ? `Brand workspace - still needed: ${st.missing.join("; ")}` : "Brand workspace"}
        aria-current={onWorkspace ? "page" : undefined}
        className={cx(item, onWorkspace ? "bg-inverse text-on-inverse shadow-[0_6px_16px_-10px_rgba(0,0,0,0.6)]" : "text-fg-muted hover:text-fg")}
      >
        <StatusDot tone={!st ? "faint" : st.ready ? "ok" : "warn"} size={6} />
        Workspace
        {st && !st.ready && <span className="sr-only"> (setup incomplete)</span>}
      </Link>
    </nav>
  );
}

/**
 * v5: the credit line. Each part only when /api/health says a REAL (not fake) service of that kind is connected;
 * with neither, nothing (the wordmark already says "Atelier").
 */
export function PoweredBy({ health, className }: { health: HealthState; className?: string }) {
  const p = health.kind === "ok" ? health.data.poweredBy : undefined;
  // "AMD" only when the hardware is verified (AMD_GPU_LABEL or the diffusion server naming an AMD device), and
  // "AMD Instinct" only when that label names an Instinct GPU (AMD Token Factory doesn't say which GPUs it runs on).
  const unverified = !!p && !p.amd && !!p.modelConnected;
  if (!p || (!p.amd && !p.evolus && !unverified)) return null;
  return (
    <span className={className}>
      {p.amd && (
        <>
          Powered by{" "}
          <span className="text-fg-muted" title={p.hardware}>
            {/instinct|\bmi\d{3}/i.test(p.hardware ?? "") ? "AMD Instinct" : "AMD GPUs"}
          </span>
        </>
      )}
      {unverified && (
        <span title="A model endpoint answers, but its hardware is not verified - set AMD_GPU_LABEL to the GPU it runs on">
          Model connected - hardware not verified
        </span>
      )}
      {(p.amd || unverified) && p.evolus && <span className="mx-2 text-fg-faint">·</span>}
      {p.evolus && (
        <>
          Orchestrated by <span className="text-fg-muted">Evolus</span>
        </>
      )}
    </span>
  );
}

const SERVICE_LABELS: Record<string, string> = {
  vision: "Vision model",
  diffusion: "Diffusion model",
  llm: "LLM orchestrator",
  evolus_outreach: "Evolus · supplier outreach",
  evolus_shopify: "Evolus · Shopify workflow",
  shopify: "Shopify dev store",
  evolus_agent: "Evolus agent · the brain",
  evolus_extractor: "Evolus · quote extractor",
  evolus_po: "Evolus · purchase orders",
};

export function serviceLabel(name: string) {
  return SERVICE_LABELS[name] ?? name.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function summariseHealth(data: HealthResponse) {
  const counted = data.services.filter((s) => !s.optional || s.status === "connected");
  const total = counted.length;
  const connected = counted.filter((s) => s.status === "connected" && !s.fake).length;
  const unreachable = data.services.filter((s) => s.status === "unreachable").length;
  const fake = data.services.filter((s) => s.fake).length;
  let label: string;
  if (fake > 0) label = "Fake upstream";
  else if (total === 0) label = "No services";
  else if (connected === total) label = "All connected";
  else label = `${connected}/${total} connected`;
  return { label, connected, total, unreachable, fake };
}

/** The status summary for any health state: label + dot tone (shared by the header pill and the Menu). */
export function healthSummary(health: HealthState): { label: string; tone: Tone | "faint"; live: boolean } {
  if (health.kind === "ok") {
    const s = summariseHealth(health.data);
    const tone: Tone | "faint" = s.fake > 0 ? "bad" : s.unreachable > 0 ? "warn" : s.connected > 0 ? "ok" : "faint";
    return { label: s.label, tone, live: tone === "ok" };
  }
  if (health.kind === "down") return { label: "Offline", tone: "bad", live: false };
  if (health.kind === "error") return { label: "Degraded", tone: "bad", live: false };
  return { label: "Checking…", tone: "faint", live: true };
}

function serviceBadge(status: string, fake?: boolean): BadgeStatus {
  if (fake) return "fake";
  return status === "connected" ? "connected" : status === "unreachable" ? "unreachable" : "not-connected";
}

/** "System" pill: a dark circle with the signal icon and a status dot, the summary as label (sm+). Opens the services popover. */
function HealthIndicator({ health, onRefresh }: { health: HealthState; onRefresh: () => void }) {
  const open = useUi((s) => s.healthOpen);
  const setOpen = useUi((s) => s.setHealthOpen);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setOpen]);

  const sum = healthSummary(health);
  // Compact label for the pill ("System · 7/9"); the popover and aria-label keep the full summary.
  const short =
    health.kind === "ok" && health.data.services.length > 0 && !health.data.services.some((x) => x.fake)
      ? `${summariseHealth(health.data).connected}/${summariseHealth(health.data).total}`
      : sum.label;
  const dot = sum.tone === "faint" ? "bg-fg-faint" : sum.tone === "ok" ? "bg-ok" : sum.tone === "warn" ? "bg-warn" : "bg-bad";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`System status: ${sum.label}`}
        title="System · services from /api/health"
        data-demo="system-pill"
        className="group/sys flex h-9 items-center gap-2 rounded-full bg-paper-2 p-1 text-[0.72rem] font-medium text-fg transition-[background-color,transform] duration-200 hover:bg-line-strong active:scale-[0.97] md:h-10 md:pr-3.5"
      >
        <span className="relative grid size-7 place-items-center rounded-full bg-inverse text-on-inverse md:size-8">
          <IconGrid size={13} className="transition-transform duration-500 ease-thread group-hover/sys:rotate-90" />
          <span aria-hidden className={cx("absolute -top-px -right-px size-[9px] rounded-full ring-2 ring-paper-2", dot, sum.live && "ds-live")} />
        </span>
        <span className="hidden whitespace-nowrap tabular md:inline">
          <span className="text-fg-muted">System · </span>
          {short}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Service status"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: DUR.ui, ease: EASE }}
            style={{ transformOrigin: "top right" }}
            className="fixed inset-x-3 top-[4.5rem] max-h-[80vh] overflow-y-auto rounded-card border border-line bg-surface p-5 shadow-e3 sm:absolute sm:inset-x-auto sm:top-[calc(100%+0.5rem)] sm:right-0 sm:w-[26rem]"
          >
            <div className="flex items-center justify-between gap-3">
              <Eyebrow tone={sum.tone} live={sum.live}>
                Services · {sum.label}
              </Eyebrow>
              <Button variant="ghost" size="sm" onClick={onRefresh} icon={<IconRefresh size={14} />}>
                Refresh
              </Button>
            </div>
            {health.kind === "ok" ? (
              <>
                <ul className="mt-3 divide-y divide-line">
                  {health.data.services.filter((s) => !s.optional || s.status === "connected").map((s) => (
                    <li key={s.name} className="flex items-start justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="text-small font-medium text-fg">{serviceLabel(s.name)}</p>
                        {s.detail && (
                          <p className={cx("mt-0.5 text-micro break-words", s.fake ? "text-bad" : "text-fg-muted")}>
                            {s.detail}
                            {s.latencyMs != null && <span className="font-mono"> · probe {Math.round(s.latencyMs)}ms</span>}
                          </p>
                        )}
                        {s.status !== "connected" && !s.optional && s.hint && <SetupHint hint={s.hint} className="mt-1.5" />}
                      </div>
                      {s.optional && s.status !== "connected" ? (
                        <Chip>Optional</Chip>
                      ) : (
                        <Badge status={serviceBadge(s.status, s.fake)} />
                      )}
                    </li>
                  ))}
                  {health.data.services.length === 0 && <li className="py-3 text-small text-fg-muted">No services reported.</li>}
                </ul>
                <p className="mt-2 rounded-panel bg-paper-2 p-3 text-micro leading-relaxed text-fg-muted">
                  Every screen calls these services for real. A step whose service is not connected shows an error with
                  its setup hint - never made-up output.
                </p>
              </>
            ) : (
              <p className="mt-4 text-small text-fg-muted">
                {health.kind === "checking"
                  ? "Checking backend…"
                  : health.kind === "down"
                    ? "The backend is unreachable."
                    : "The health endpoint returned an error."}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
