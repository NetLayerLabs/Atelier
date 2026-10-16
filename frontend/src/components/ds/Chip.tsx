import type { ButtonHTMLAttributes, ReactNode } from "react";
import { IconClose } from "./icons";
import { cx, TONE, type Tone } from "./tokens";

export type ChipVariant = "outline" | "soft" | "ink";

type ChipBase = {
  variant?: ChipVariant;
  size?: "sm" | "md";
  /** A small coloured dot before the label (category colour or status). */
  dot?: Tone | false;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
};

function chipClass({ variant = "outline", size = "md", selected, interactive }: { variant?: ChipVariant; size?: "sm" | "md"; selected?: boolean; interactive?: boolean }) {
  return cx(
    "inline-flex max-w-full items-center gap-1.5 rounded-full whitespace-nowrap transition-colors duration-200",
    size === "sm" ? "h-6 px-2.5 text-micro font-medium" : "h-8 px-3.5 text-[0.74rem] font-medium",
    selected
      ? "border border-inverse bg-inverse text-on-inverse"
      : variant === "outline"
        ? "border border-line-strong bg-surface text-fg"
        : variant === "soft"
          ? "bg-paper-2 text-fg-muted"
          : "bg-inverse font-medium text-on-inverse",
    interactive && !selected && "hover:border-line-bold hover:bg-surface-muted",
  );
}

/**
 * Pill chip for categories, filters and keywords (Scenar's tag pill). Static by default; pass `onClick` via
 * <ChipButton> for a toggle (aria-pressed). Keep labels to 1–3 words.
 */
export function Chip({ variant, size, dot, icon, className, children }: ChipBase) {
  return (
    <span className={cx(chipClass({ variant, size }), className)}>
      {dot && <span aria-hidden className={cx("size-1.5 shrink-0 rounded-full", TONE[dot].dot)} />}
      {icon}
      <span className="truncate">{children}</span>
    </span>
  );
}

/** A selectable chip (filter / multi-select). `selected` renders ink-filled and sets aria-pressed. */
export function ChipButton({
  variant,
  size,
  dot,
  icon,
  selected,
  onRemove,
  className,
  children,
  ...rest
}: ChipBase & ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean; onRemove?: () => void }) {
  return (
    <span className="inline-flex max-w-full items-center">
      <button
        type="button"
        aria-pressed={selected}
        className={cx(chipClass({ variant, size, selected, interactive: true }), onRemove && "pr-8", className)}
        {...rest}
      >
        {dot && <span aria-hidden className={cx("size-1.5 shrink-0 rounded-full", TONE[dot].dot)} />}
        {icon}
        <span className="truncate">{children}</span>
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${typeof children === "string" ? children : ""}`.trim()}
          className="-ml-7 grid size-6 place-items-center rounded-full text-fg-muted hover:bg-paper-2 hover:text-fg"
        >
          <IconClose size={12} strokeWidth={2.2} />
        </button>
      )}
    </span>
  );
}

/**
 * Garment tag: an angled label with a punched eyelet. Use for named things that get "tagged" onto a garment:
 * concept names (Look A), SKUs, sizes, price tags, the chosen supplier. Not for statuses (use <Badge>).
 * `code` adds a mono reference after the label (e.g. a SKU or "€38.00").
 */
export function GarmentTag({
  children,
  code,
  tone = "default",
  className,
}: {
  children: ReactNode;
  code?: ReactNode;
  tone?: "default" | "ink" | "accent";
  className?: string;
}) {
  return (
    <span className={cx("ds-tag max-w-full", className)} data-tone={tone === "default" ? undefined : tone}>
      <span className="h-7 min-w-0 pr-3 text-small font-medium whitespace-nowrap">
        <span className="truncate">{children}</span>
        {code && <span className="font-mono text-micro font-normal opacity-70">{code}</span>}
      </span>
    </span>
  );
}

export type BadgeStatus =
  | "connected"
  | "not-connected"
  | "unreachable"
  | "unverified"
  | "fake"
  | "measured"
  | "sent"
  | "received"
  | "draft"
  | "pending"
  | "running"
  | "approved"
  | "rejected"
  | "failed"
  | "unknown";

const STATUS: Record<BadgeStatus, { tone: Tone | "faint"; label: string; live?: boolean; strong?: boolean }> = {
  connected: { tone: "ok", label: "Connected", live: true },
  "not-connected": { tone: "faint", label: "Not connected" },
  unreachable: { tone: "warn", label: "Unreachable" },
  unverified: { tone: "warn", label: "Unverified" },
  fake: { tone: "bad", label: "FAKE upstream - not real", strong: true },
  measured: { tone: "ok", label: "Measured" },
  sent: { tone: "accent", label: "Sent" },
  received: { tone: "ok", label: "Received" },
  draft: { tone: "faint", label: "Draft" },
  pending: { tone: "neutral", label: "Pending" },
  running: { tone: "accent", label: "Running", live: true },
  approved: { tone: "ok", label: "Approved" },
  rejected: { tone: "bad", label: "Rejected" },
  failed: { tone: "bad", label: "Failed" },
  unknown: { tone: "warn", label: "Status unknown" },
};

/**
 * Status badge: coloured text on its soft tint, with a dot. One vocabulary for the whole app (see `BadgeStatus`);
 * pass `children` to override the label but keep the status colour. `fake` is always loud (bordered, bold).
 */
export function Badge({
  status,
  tone,
  children,
  title,
  className,
}: {
  status?: BadgeStatus;
  /** Free-form tone when no status fits. */
  tone?: Tone | "faint";
  children?: ReactNode;
  title?: string;
  className?: string;
}) {
  const s = status ? STATUS[status] : { tone: tone ?? "neutral", label: "" };
  const t = s.tone;
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-6 max-w-full shrink-0 items-center gap-1.5 rounded-full px-2.5 text-micro font-medium whitespace-nowrap",
        t === "faint" ? "bg-paper-2 text-fg-muted" : cx(TONE[t].soft, TONE[t].text),
        t === "neutral" && "text-fg",
        "strong" in s && s.strong && "border border-bad font-semibold",
        className,
      )}
    >
      <span
        aria-hidden
        className={cx("size-1.5 shrink-0 rounded-full", t === "faint" ? "bg-fg-faint" : TONE[t].dot, "live" in s && s.live && "ds-live")}
      />
      <span className="truncate">{children ?? s.label}</span>
    </span>
  );
}
