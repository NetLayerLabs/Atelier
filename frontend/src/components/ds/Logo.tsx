import { cx } from "./tokens";

/**
 * The Atelier logo: a serif "A" under a tailor's-gauge arc with one tick at the top (the needle of the hero gauge).
 * The artwork is a transparent PNG in public/brand/ used as a CSS mask, so it is painted in currentColor and
 * follows the theme (ink on white, white on the dark projector theme).
 */
function Masked({ src, width, height, className, title }: {
  src: string;
  width: number;
  height: number;
  className?: string;
  title?: string;
}) {
  const mask = `url(${src}) center / contain no-repeat`;
  return (
    <span
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className={cx("inline-block shrink-0 bg-current", className)}
      style={{ width, height, mask, WebkitMask: mask }}
    />
  );
}

/** The mark alone (square). Minimum size 20px. */
export function AtelierMark({ size = 28, className, title }: { size?: number; className?: string; title?: string }) {
  return <Masked src="/brand/atelier-mark.png" width={size} height={size} className={className} title={title} />;
}

/** The full lockup: mark + "ATELIER" in spaced serif capitals. `height` is the lockup's height in px. */
export function AtelierLockup({ height = 24, className, title }: { height?: number; className?: string; title?: string }) {
  return (
    <Masked
      src="/brand/atelier-header.png"
      width={Math.round(height * LOCKUP_RATIO)}
      height={height}
      className={className}
      title={title}
    />
  );
}

/** Width / height of public/brand/atelier-header.png (1200 x 251). */
const LOCKUP_RATIO = 1200 / 251;

/** Text wordmark, kept for places that need live text; the lockup is the logo. */
export function Wordmark({ className }: { className?: string }) {
  return <span className={cx("text-[0.9rem] leading-none font-semibold tracking-[-0.02em]", className)}>Atelier</span>;
}
