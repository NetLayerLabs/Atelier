"use client";

import Link from "next/link";
import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cx, TONE, type Tone } from "./tokens";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "accent" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const BASE =
  "group/btn relative inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap select-none " +
  "transition-[background-color,border-color,color,opacity,transform,box-shadow] duration-200 ease-thread " +
  "active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45";

const VARIANT: Record<ButtonVariant, string> = {
  /** Black pill (white in dark): the main action of a screen. Inside .ds-inverse it becomes the white pill. */
  primary: "bg-inverse text-on-inverse hover:-translate-y-px hover:bg-inverse-hover",
  /** Outlined pill: the alternative next to a primary. */
  secondary: "border border-line-bold bg-transparent text-fg hover:border-fg hover:bg-paper-2",
  /** Text-weight action: tertiary links, "Cancel", "Show more". */
  ghost: "text-fg-muted hover:bg-paper-2 hover:text-fg",
  /** The human's decisive step (Approve, Send to mill). Monochrome: the same ink pill as primary, kept as a role. */
  accent: "bg-accent text-on-accent hover:-translate-y-px hover:opacity-90",
  /** Destructive or "stop" (Reject, Exit tour). */
  danger: "border border-bad/45 text-bad hover:bg-bad-soft",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-9 px-4 text-[0.76rem]",
  md: "min-h-11 px-5.5 text-[0.8rem]",
  lg: "min-h-12 px-6.5 text-[0.86rem]",
};

/** Class string for a design-system button, e.g. to style a <Link>. */
export function buttonClass({
  variant = "primary",
  size = "md",
  className,
}: { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {}) {
  return cx(BASE, VARIANT[variant], SIZE[size], className);
}

type CommonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Icon before the label (16px). */
  icon?: ReactNode;
  /** Icon after the label. With `trailingBadge`, it sits in a round chip at the right end (the "Launch ↗" look). */
  trailing?: ReactNode;
  trailingBadge?: boolean;
  loading?: boolean;
};

function Inner({
  icon,
  trailing,
  trailingBadge,
  loading,
  size = "md",
  variant = "primary",
  children,
}: CommonProps & { children?: ReactNode }) {
  const badge =
    variant === "primary"
      ? "bg-on-inverse text-inverse"
      : variant === "accent"
        ? "bg-on-accent text-accent"
        : "bg-inverse text-on-inverse";
  return (
    <>
      {loading ? <Spinner /> : icon}
      {children}
      {trailing &&
        (trailingBadge ? (
          <span
            aria-hidden
            className={cx(
              "-mr-3.5 ml-1.5 grid place-items-center rounded-full transition-transform duration-500 ease-thread group-hover/btn:rotate-45",
              size === "sm" ? "size-7" : size === "lg" ? "size-9" : "size-8",
              badge,
            )}
          >
            {trailing}
          </span>
        ) : (
          <span aria-hidden className="transition-transform duration-300 ease-thread group-hover/btn:translate-x-0.5">
            {trailing}
          </span>
        ))}
    </>
  );
}

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & CommonProps;

/**
 * Pill button. `primary` (ink) for the main action, `secondary` (outline) beside it, `ghost` for quiet actions,
 * `accent` (same ink, as a role) for the creative director's decisive step, `danger` for stop/reject.
 * Sizes: sm 36px, md 44px (default, touch-safe), lg 52px (hero CTAs).
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", icon, trailing, trailingBadge, loading, className, children, disabled, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClass({ variant, size, className: cx(trailingBadge && "pr-1.5", className) })}
      {...rest}
    >
      <Inner {...{ icon, trailing, trailingBadge, loading, size, variant }}>{children}</Inner>
    </button>
  );
});

export type LinkButtonProps = AnchorHTMLAttributes<HTMLAnchorElement> & CommonProps & { href: string };

/** A next/link styled as a Button. Use for navigation; use Button for actions. */
export function LinkButton({
  variant = "primary",
  size = "md",
  icon,
  trailing,
  trailingBadge,
  className,
  children,
  href,
  ...rest
}: LinkButtonProps) {
  return (
    <Link href={href} className={buttonClass({ variant, size, className: cx(trailingBadge && "pr-1.5", className) })} {...rest}>
      <Inner {...{ icon, trailing, trailingBadge, size, variant }}>{children}</Inner>
    </Link>
  );
}

export type IconButtonVariant = "solid" | "soft" | "outline" | "ghost";

export type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Accessible name; also shown as the native tooltip. Required: icon buttons have no visible text. */
  label: string;
  variant?: IconButtonVariant;
  size?: "sm" | "md" | "lg";
  /** A status dot on the top-right rim (e.g. system health). */
  dot?: Tone | false;
  /** Pulse the dot (live / working). */
  dotLive?: boolean;
  children: ReactNode;
};

/**
 * Round icon button (Scenar-style header controls). 32 / 40 / 48px; the hit area is always at least 40px.
 * `solid` = ink circle, `soft` = paper-2 well, `outline` = hairline ring, `ghost` = no chrome.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = "soft", size = "md", dot, dotLive, className, children, type, title, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      aria-label={label}
      title={title ?? label}
      className={cx(
        "relative inline-grid shrink-0 place-items-center rounded-full transition-[background-color,border-color,color,transform] duration-200 ease-thread active:scale-95 disabled:pointer-events-none disabled:opacity-45",
        size === "sm" && "size-8",
        size === "md" && "size-10",
        size === "lg" && "size-12",
        variant === "solid" && "bg-inverse text-on-inverse hover:bg-inverse-hover",
        variant === "soft" && "bg-paper-2 text-fg hover:bg-line-strong",
        variant === "outline" && "border border-line-bold text-fg hover:border-fg",
        variant === "ghost" && "text-fg-muted hover:bg-paper-2 hover:text-fg",
        className,
      )}
      {...rest}
    >
      {children}
      {dot && (
        <span
          aria-hidden
          className={cx(
            "absolute -top-0.5 -right-0.5 size-3 rounded-full border-2 border-paper",
            TONE[dot].dot,
            dot === "neutral" && "bg-fg-faint",
            dotLive && "ds-live",
          )}
        />
      )}
    </button>
  );
});

/** 14px ring spinner in currentColor. */
export function Spinner({ className, size = 14 }: { className?: string; size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cx("inline-block shrink-0 animate-spin rounded-full border-[1.5px] border-current border-t-transparent", className)}
    />
  );
}
