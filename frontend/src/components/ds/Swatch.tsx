import { cx } from "./tokens";

/**
 * Fabric swatch: a colour chip cut with pinking shears (zig-zag bottom edge) and a faint twill weave.
 * `color` is a real colour from the data (a trend palette, a BOM colourway) - this is the one place where a
 * non-token colour is allowed. With `name`/`code` it becomes a labelled card (name + mono hex beneath).
 */
export function Swatch({
  color,
  name,
  code,
  size = "md",
  weave = true,
  className,
}: {
  color: string;
  name?: string;
  /** e.g. the hex, a Pantone-style reference or a share ("32%"). */
  code?: string;
  size?: "xs" | "sm" | "md" | "lg";
  /** Show the twill texture (off for tiny inline chips). */
  weave?: boolean;
  className?: string;
}) {
  const dims =
    size === "xs" ? "h-4 w-4 rounded-[3px]" : size === "sm" ? "h-9 w-9 rounded-md" : size === "md" ? "h-16 w-full rounded-lg" : "h-28 w-full rounded-xl";
  const chip = (
    <span
      aria-hidden={!name || undefined}
      role={name ? undefined : "img"}
      aria-label={name ? undefined : `Colour ${code ?? color}`}
      className={cx("relative block shrink-0 overflow-hidden ring-1 ring-line ring-inset", size !== "xs" && "ds-pinked", dims, !name && className)}
      style={{ background: color }}
    >
      {weave && size !== "xs" && (
        <span
          aria-hidden
          className="absolute inset-0 opacity-[0.16] mix-blend-overlay"
          style={{
            backgroundImage:
              "repeating-linear-gradient(45deg, rgba(255,255,255,.9) 0 1px, transparent 1px 4px), repeating-linear-gradient(-45deg, rgba(0,0,0,.6) 0 1px, transparent 1px 5px)",
          }}
        />
      )}
    </span>
  );
  if (!name && !code) return chip;
  return (
    <figure className={cx("flex min-w-0 flex-col gap-2", size === "sm" && "flex-row items-center gap-2.5", className)}>
      {chip}
      <figcaption className="min-w-0 leading-tight">
        {name && <span className="block truncate text-small text-fg">{name}</span>}
        {code && <span className="block truncate font-mono text-micro text-fg-faint uppercase">{code}</span>}
      </figcaption>
    </figure>
  );
}

/** A row of swatches as one strip (palette at a glance). Each entry may carry a weight (share of the palette). */
export function SwatchStrip({
  colors,
  className,
  height = 40,
}: {
  colors: { color: string; name?: string; weight?: number }[];
  className?: string;
  height?: number;
}) {
  return (
    <div
      role="img"
      aria-label={`Palette: ${colors.map((c) => c.name ?? c.color).join(", ")}`}
      className={cx("ds-pinked flex w-full overflow-hidden rounded-lg ring-1 ring-line ring-inset", className)}
      style={{ height }}
    >
      {colors.map((c, i) => (
        <span key={`${c.color}-${i}`} title={c.name ?? c.color} style={{ background: c.color, flex: c.weight ?? 1 }} />
      ))}
    </div>
  );
}
