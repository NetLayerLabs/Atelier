import type { ReactNode } from "react";
import { cx } from "./tokens";

/**
 * Stitch divider: a dashed seam between sections of a card or page. With `label`, the label sits in the middle
 * ("or", "Agent", "You"). Use a plain hairline (`border-line`) for table rows and lists; stitches mark a hand-off
 * or a change of author (AI ↔ human).
 */
export function Stitch({ label, className }: { label?: ReactNode; className?: string }) {
  if (!label) return <div role="separator" className={cx("ds-stitch w-full", className)} />;
  return (
    <div role="separator" className={cx("flex items-center gap-3", className)}>
      <span className="ds-stitch flex-1" />
      <span className="text-micro font-medium text-fg-faint">{label}</span>
      <span className="ds-stitch flex-1" />
    </div>
  );
}
