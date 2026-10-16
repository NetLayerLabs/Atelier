"use client";

import type { ReactNode } from "react";
import { SetupHint } from "./Alert";
import { Button } from "./Button";
import { Badge } from "./Chip";
import { IconRefresh, IconUnplug } from "./icons";
import { cx } from "./tokens";

/**
 * Empty state: nothing here yet, and what to do about it. A dashed ("chalk outline") panel
 * with a round icon, a title, one line of explanation and at most two actions.
 */
export function EmptyState({
  icon,
  title,
  children,
  actions,
  compact,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  /** Smaller padding for use inside cards. */
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center rounded-card border-[1.5px] border-dashed border-line-strong text-center",
        compact ? "gap-2.5 px-5 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {icon && (
        <span aria-hidden className="grid size-12 place-items-center rounded-full border border-line bg-surface text-fg-muted shadow-e1">
          {icon}
        </span>
      )}
      <p className="text-title text-fg">{title}</p>
      {children && <div className="max-w-md text-small text-pretty text-fg-muted">{children}</div>}
      {actions && <div className="mt-2 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}

/**
 * The honest "not connected" state for a step whose real service isn't configured or answering. Never fake
 * output here: name the service, show the backend's setup hint verbatim, offer Retry.
 */
export function NotConnected({
  service,
  status = "not-connected",
  children,
  hint,
  onRetry,
  retrying,
  compact,
  className,
}: {
  /** Human name, e.g. "Shopify dev store", "Vision model". */
  service: string;
  status?: "not-connected" | "unreachable";
  /** One sentence: what this step would show once connected. */
  children?: ReactNode;
  hint?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cx(
        "flex flex-col gap-4 rounded-card border-[1.5px] border-dashed border-line-strong bg-surface sm:flex-row sm:items-start",
        compact ? "p-4" : "p-5 sm:p-6",
        className,
      )}
    >
      <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-full bg-paper-2 text-fg-muted">
        <IconUnplug size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-body font-medium text-fg">{service}</p>
          <Badge status={status} />
        </div>
        {children && <div className="mt-1.5 text-small text-fg-muted">{children}</div>}
        {hint && <SetupHint hint={hint} className="mt-3" />}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} loading={retrying} icon={<IconRefresh size={14} />} className="self-start">
          Retry
        </Button>
      )}
    </div>
  );
}
