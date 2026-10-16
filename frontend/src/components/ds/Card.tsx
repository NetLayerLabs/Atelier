import { createElement, type HTMLAttributes, type ReactNode } from "react";
import { cx } from "./tokens";

export type CardVariant = "surface" | "muted" | "inverse" | "outline";

export type CardProps = HTMLAttributes<HTMLElement> & {
  /**
   * surface: white card, very soft border + Scenar's soft shadow (default).
   * muted: a grey well inside a card or page (no border).
   * inverse: black card, the "decision" moment (one per screen).
   * outline: transparent with a hairline (secondary groupings).
   */
  variant?: CardVariant;
  /** Padding preset: none | sm (16) | md (24, default) | lg (32 → 40 on desktop). */
  pad?: "none" | "sm" | "md" | "lg";
  /** Lift on hover (for clickable cards). */
  interactive?: boolean;
  as?: "div" | "section" | "article" | "li" | "aside" | "figure";
};

/** The base container (Scenar's card): white, large radius (24px), rgba(0,0,0,.08) border, soft shadow. */
export function Card({ variant = "surface", pad = "md", interactive, as = "div", className, children, ...rest }: CardProps) {
  return createElement(
    as,
    {
      className: cx(
        "relative rounded-card",
        variant === "surface" && "border border-line bg-surface shadow-e2",
        variant === "muted" && "bg-paper-2",
        variant === "inverse" && "ds-inverse shadow-e2",
        variant === "outline" && "border border-line-strong",
        pad === "sm" && "p-4",
        pad === "md" && "p-5 sm:p-6",
        pad === "lg" && "p-6 sm:p-10",
        interactive &&
          "cursor-pointer transition-[transform,box-shadow,border-color] duration-500 ease-thread hover:-translate-y-0.5 hover:border-line-strong hover:shadow-e3",
        className,
      ),
      ...rest,
    },
    children,
  );
}

/** A card's header row: eyebrow/title on the left, actions on the right; wraps on mobile. */
export function CardHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("mb-5 flex flex-wrap items-start justify-between gap-x-4 gap-y-3", className)}>
      <div className="min-w-0">
        {eyebrow}
        {title && <h3 className={cx("text-title text-fg", eyebrow ? "mt-2" : undefined)}>{title}</h3>}
        {description && <p className="mt-1 max-w-prose text-small text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
