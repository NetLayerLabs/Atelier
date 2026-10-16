"use client";

import type { ReactNode } from "react";
import { IconAlert, IconCheck, IconInfo } from "./icons";
import { cx, TONE } from "./tokens";

export type AlertTone = "info" | "ok" | "warn" | "bad";

const MAP = { info: "accent", ok: "ok", warn: "warn", bad: "bad" } as const;

export function alertIcon(tone: AlertTone, size = 16) {
  return tone === "ok" ? <IconCheck size={size} strokeWidth={2.2} /> : tone === "info" ? <IconInfo size={size} /> : <IconAlert size={size} />;
}

/**
 * Inline alert: a tinted panel with a round icon, a title, a message and an optional action (Retry).
 * Use for service errors (with the backend's setup `hint`), guardrail breaches, and confirmations that must
 * stay on screen. For transient confirmations use toast(). `role="alert"` for bad/warn, status otherwise.
 */
export function InlineAlert({
  tone = "info",
  title,
  children,
  hint,
  action,
  className,
  "data-demo": dataDemo,
}: {
  tone?: AlertTone;
  title: ReactNode;
  children?: ReactNode;
  /** A setup / fix hint from the backend ("Set AMD_VISION_ENDPOINT …"), shown in mono. */
  hint?: ReactNode;
  /** Usually a <Button size="sm" variant="secondary">Retry</Button>. */
  action?: ReactNode;
  className?: string;
  "data-demo"?: string;
}) {
  const t = TONE[MAP[tone]];
  return (
    <div
      role={tone === "bad" || tone === "warn" ? "alert" : "status"}
      data-demo={dataDemo}
      className={cx("flex flex-col gap-4 rounded-panel border p-4 sm:flex-row sm:items-start sm:p-5", t.soft, t.border, className)}
    >
      <span aria-hidden className={cx("grid size-8 shrink-0 place-items-center rounded-full bg-surface", t.text)}>
        {alertIcon(tone)}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cx("text-body font-medium", t.text)}>{title}</p>
        {children && <div className="mt-1 text-small break-words text-fg-muted">{children}</div>}
        {hint && <SetupHint hint={hint} className="mt-2" />}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** The backend's setup hint, in mono, prefixed "Setup". */
export function SetupHint({ hint, className }: { hint: ReactNode; className?: string }) {
  return (
    <p className={cx("font-mono text-micro leading-relaxed break-words text-fg-muted", className)}>
      <span className="mr-1.5 rounded-sm bg-surface px-1.5 py-0.5 text-label tracking-[0.12em] text-fg uppercase">Setup</span>
      {hint}
    </p>
  );
}
