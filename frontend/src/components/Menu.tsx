"use client";

// The Menu: a black pill in the header ("+ Menu", the plus turns into a cross) that opens a card with every
// place and tool in the app: the studio chapters, the landing sections, the Brand workspace, the guided tour,
// inference stats, system status, sign-in, the theme and "Start over".

import { AnimatePresence, motion } from "framer-motion";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AUTH_REQUIRED_EVENT, getAuthStatus } from "@/lib/api";
import { useDemo } from "@/lib/demo";
import { useHealth } from "@/lib/health";
import { useUi } from "@/lib/ui";
import {
  Badge,
  IconArrowUpRight,
  IconKey,
  IconPlay,
  IconPlus,
  IconPulse,
  IconRefresh,
  IconSignal,
  IconStop,
  Label,
  StatusDot,
  ThemeSegmented,
} from "./ds";
import { cx, DUR, EASE } from "./ds/tokens";
import { healthSummary, PoweredBy } from "./Header";
import { lastRealCall, useTelemetry } from "./Inference";
import { CHAPTERS } from "./landing/data";
import { LANDING_CONTENTS } from "./landing/Hero";
import { scrollToId } from "./ui";
import { useWorkspaceStatus } from "./workspace/WorkspaceGate";

const CHAPTER_IDS = ["chapter-trend", "chapter-ideation", "chapter-vibe", "chapter-production"] as const;

export function MenuButton({
  onStartOver,
  hasProgress,
  onRefreshHealth,
}: {
  onStartOver: () => void;
  hasProgress: boolean;
  onRefreshHealth: () => void;
}) {
  const open = useUi((s) => s.menuOpen);
  const setOpen = useUi((s) => s.setMenuOpen);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();

  // Close on outside click, Esc (focus back to the pill) and navigation.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setOpen]);
  useEffect(() => setOpen(false), [pathname, setOpen]);

  return (
    <div className="relative" ref={wrap}>
      <button
        ref={button}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="atelier-menu"
        className="flex h-9 items-center gap-2 rounded-full bg-inverse py-1 pr-3.5 pl-1 text-on-inverse transition-[background-color,transform] duration-200 hover:bg-inverse-hover active:scale-[0.97] md:h-10 md:pr-4"
      >
        <span
          aria-hidden
          className={cx(
            "grid size-7 place-items-center rounded-full bg-on-inverse text-inverse transition-transform duration-500 ease-thread md:size-8",
            open && "rotate-45",
          )}
        >
          <IconPlus size={14} strokeWidth={2.4} />
        </span>
        <span className="text-[0.66rem] font-medium tracking-[0.01em]">Menu</span>
      </button>
      <AnimatePresence>
        {open && (
          <MenuPanel
            onClose={() => setOpen(false)}
            onStartOver={onStartOver}
            hasProgress={hasProgress}
            onRefreshHealth={onRefreshHealth}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function MenuPanel({
  onClose,
  onStartOver,
  hasProgress,
  onRefreshHealth,
}: {
  onClose: () => void;
  onStartOver: () => void;
  hasProgress: boolean;
  onRefreshHealth: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const onHome = pathname === "/";
  const health = useHealth((s) => s.health);
  const sum = healthSummary(health);
  const ws = useWorkspaceStatus();
  const demoActive = useDemo((s) => s.status !== "idle");
  const telemetry = useTelemetry((s) => s.data);
  const last = lastRealCall(telemetry);
  const realCalls = telemetry?.calls.filter((c) => !c.fake).length ?? 0;
  const [auth, setAuth] = useState<{ required: boolean; signedIn: boolean } | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  // Which chapters exist on the page right now (a chapter mounts once it is reached).
  const [reached] = useState<boolean[]>(() =>
    CHAPTER_IDS.map((id, i) => (typeof document !== "undefined" && onHome ? !!document.getElementById(id) : i === 0)),
  );

  useEffect(() => {
    let live = true;
    getAuthStatus()
      .then((s) => live && setAuth({ required: s.adminTokenRequired, signedIn: s.authenticated }))
      .catch(() => undefined);
    panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => {
      live = false;
    };
  }, []);

  const go = (id: string) => {
    onClose();
    if (onHome) scrollToId(id);
    else router.push(`/#${id}`);
  };

  return (
    <motion.div
      ref={panel}
      id="atelier-menu"
      role="dialog"
      aria-label="Menu"
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      transition={{ duration: DUR.ui, ease: EASE }}
      style={{ transformOrigin: "top left" }}
      className="fixed inset-x-3 top-[4.5rem] max-h-[calc(100dvh-5rem)] overflow-y-auto overscroll-contain rounded-card border border-line bg-surface p-2 shadow-e3 sm:absolute sm:inset-x-auto sm:top-[calc(100%+0.5rem)] sm:left-0 sm:w-[25rem]"
    >
      <Section label="Studio · chapters">
        {CHAPTERS.map((c, i) => (
          <MenuRow
            key={c.numeral}
            onClick={() => go(CHAPTER_IDS[i])}
            disabled={!reached[i]}
            lead={<span className="text-micro leading-none font-medium tabular">{c.numeral}</span>}
            label={c.title}
            hint={reached[i] ? c.kicker : `${c.kicker} · not reached yet`}
          />
        ))}
      </Section>

      <Section label="Overview">
        <ul className="grid grid-cols-2 gap-0.5">
          {LANDING_CONTENTS.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => go(c.id)}
                className="flex min-h-10 w-full items-baseline gap-2 rounded-[14px] px-3 py-2 text-left text-small text-fg-muted transition-colors hover:bg-paper-2 hover:text-fg"
              >
                <span className="font-mono text-micro text-fg-faint">{String(i + 1).padStart(2, "0")}</span>
                {c.label}
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section label="Brand">
        <MenuRow
          href="/workspace"
          onClick={() => {
            onClose();
            router.push("/workspace");
          }}
          lead={<StatusDot tone={ws ? (ws.ready ? "ok" : "warn") : "faint"} />}
          label="Brand workspace"
          hint={ws ? (ws.ready ? "Ready: profile, suppliers, prices, guardrails" : `Still needed: ${ws.missing.join("; ")}`) : "Profile, brand book, suppliers, prices, guardrails"}
          arrow
        />
      </Section>

      <Section label="Tools">
        <MenuRow
          onClick={() => {
            onClose();
            const d = useDemo.getState();
            if (demoActive) d.stop();
            else d.start();
          }}
          lead={demoActive ? <IconStop size={13} /> : <IconPlay size={13} />}
          label={demoActive ? "Exit the guided tour" : "Guided tour"}
          hint="Drives the real app against the real services"
          kbd="Shift D"
        />
        <MenuRow
          onClick={() => {
            onClose();
            useUi.getState().setInferenceOpen(true);
          }}
          lead={<IconPulse size={15} />}
          label="Inference stats"
          hint={
            realCalls
              ? `${realCalls} measured call${realCalls === 1 ? "" : "s"}${last?.tokensPerSec != null ? ` · last ${Math.round(last.tokensPerSec)} tok/s` : ""}`
              : "No measured calls yet"
          }
        />
        <MenuRow
          onClick={() => {
            onClose();
            onRefreshHealth();
            useUi.getState().setHealthOpen(true);
          }}
          lead={<IconSignal size={15} />}
          label="System status"
          hint="Every service, from /api/health"
          trailing={<Badge tone={sum.tone}>{sum.label}</Badge>}
        />
        {auth?.required && (
          <MenuRow
            onClick={() => {
              onClose();
              if (!auth.signedIn) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
            }}
            disabled={auth.signedIn}
            lead={<IconKey size={15} />}
            label={auth.signedIn ? "Signed in" : "Sign in"}
            hint="Approve needs the admin token; every step before it is open to try"
          />
        )}
        {hasProgress && (
          <MenuRow
            onClick={() => {
              onClose();
              onStartOver();
            }}
            lead={<IconRefresh size={15} />}
            label="Start over"
            hint="Clears this session and returns to the top"
          />
        )}
      </Section>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-3 rounded-[18px] bg-paper-2 px-3 py-3">
        <ThemeSegmented />
        <PoweredBy health={health} className="text-micro text-fg-faint" />
      </div>
    </motion.div>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="border-b border-line px-1 pt-2 pb-2 last-of-type:border-b-0">
      <Label as="p" className="px-2 pt-1 pb-1.5">
        {label}
      </Label>
      {children}
    </section>
  );
}

function MenuRow({
  onClick,
  href,
  lead,
  label,
  hint,
  trailing,
  arrow,
  kbd,
  disabled,
}: {
  onClick: () => void;
  href?: string;
  lead: ReactNode;
  label: ReactNode;
  hint?: ReactNode;
  trailing?: ReactNode;
  arrow?: boolean;
  kbd?: string;
  disabled?: boolean;
}) {
  const cls = cx(
    "group/row flex w-full items-center gap-3 rounded-[14px] px-2 py-2 text-left transition-colors",
    disabled ? "cursor-default opacity-50" : "hover:bg-paper-2 focus-visible:bg-paper-2",
  );
  const body = (
    <>
      <span
        aria-hidden
        className="grid size-9 shrink-0 place-items-center rounded-full bg-paper-2 text-fg transition-colors group-hover/row:bg-inverse group-hover/row:text-on-inverse"
      >
        {lead}
      </span>
      <span className="min-w-0 flex-1 leading-snug">
        <span className="block text-small font-medium text-fg">{label}</span>
        {hint && <span className="block truncate text-micro text-fg-muted">{hint}</span>}
      </span>
      {trailing}
      {kbd && <kbd className="hidden rounded-md border border-line-strong px-1.5 py-0.5 font-mono text-[0.62rem] text-fg-faint sm:inline">{kbd}</kbd>}
      {arrow && (
        <span aria-hidden className="text-fg-faint transition-transform duration-300 ease-thread group-hover/row:rotate-45 group-hover/row:text-fg">
          <IconArrowUpRight size={16} />
        </span>
      )}
    </>
  );
  if (href) {
    return (
      <a
        href={href}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey) return;
          e.preventDefault();
          onClick();
        }}
        className={cls}
      >
        {body}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={cls}>
      {body}
    </button>
  );
}
