/** Shared maths for the instruments. */

export function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

/** A "nice" step (1, 2, 2.5, 5 × 10^n) so that `range / step` is about `target`. */
export function niceStep(range: number, target = 6): number {
  if (!(range > 0)) return 1;
  const raw = range / target;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  const nice = f < 1.5 ? 1 : f < 2.25 ? 2 : f < 3.5 ? 2.5 : f < 7.5 ? 5 : 10;
  return nice * pow;
}

/** Fraction 0–1 of `v` between `min` and `max`, clamped. */
export function frac(v: number, min: number, max: number) {
  return max === min ? 0 : clamp((v - min) / (max - min), 0, 1);
}

/** Avoid "0.30000000000000004" in tick labels. */
export function tidy(n: number) {
  return Math.round(n * 1e6) / 1e6;
}

/**
 * Polar → cartesian, angle in degrees (0 = east, counter-clockwise positive, SVG y down). Rounded to 1/1000 px: the
 * server and the browser print trig results to different last digits, which React reports as a hydration mismatch.
 */
export function polar(cx: number, cy: number, r: number, deg: number) {
  const a = (deg * Math.PI) / 180;
  return { x: Math.round((cx + r * Math.cos(a)) * 1000) / 1000, y: Math.round((cy - r * Math.sin(a)) * 1000) / 1000 };
}

/** SVG arc path along a circle between two angles (degrees, as in `polar`), drawn clockwise from a0 to a1. */
export function arcPath(cx: number, cy: number, r: number, a0: number, a1: number) {
  const p0 = polar(cx, cy, r, a0);
  const p1 = polar(cx, cy, r, a1);
  const large = Math.abs(a0 - a1) > 180 ? 1 : 0;
  return `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`;
}
