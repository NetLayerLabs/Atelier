import { cx } from "./tokens";

/**
 * Loading placeholder with a slow sweep. Match the shape of what will arrive (an image tile, three text lines).
 * Pair long waits with a sentence saying what is happening ("Gemma is reading the mood board…").
 */
export function Skeleton({ className, rounded = "md" }: { className?: string; rounded?: "sm" | "md" | "lg" | "full" }) {
  return (
    <span
      aria-hidden
      className={cx(
        "ds-skeleton block",
        rounded === "sm" && "rounded-md",
        rounded === "md" && "rounded-field",
        rounded === "lg" && "rounded-card",
        rounded === "full" && "rounded-full",
        className,
      )}
    />
  );
}

/** N lines of text placeholder; the last line is shorter. */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <span aria-hidden className={cx("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} rounded="sm" className={cx("h-3", i === lines - 1 ? "w-3/5" : "w-full")} />
      ))}
    </span>
  );
}
