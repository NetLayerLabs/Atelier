// Atelier design system - import everything from "@/components/ds". Spec: docs/DESIGN.md. Showcase: /design.

export { cx, EASE, DUR, NEEDLE_SPRING, INSTANT, RISE, C, TONE, tensionColor, type Tone } from "./tokens";
export * from "./icons";
export {
  GlyphCheck,
  GlyphCross,
  GlyphPin,
  GlyphHand,
  GlyphRetry,
  GlyphStar,
  GlyphRating,
  GlyphText,
  GLYPH_CHARS,
  type GlyphProps,
  type GlyphTone,
  type GlyphName,
} from "./glyphs";
export { AtelierLockup, AtelierMark, Wordmark } from "./Logo";
export {
  Button,
  LinkButton,
  IconButton,
  Spinner,
  buttonClass,
  type ButtonProps,
  type ButtonVariant,
  type ButtonSize,
  type IconButtonProps,
} from "./Button";
export { Card, CardHeader, type CardProps, type CardVariant } from "./Card";
export { Eyebrow, StatusDot, Label, SectionHeading, Em } from "./Eyebrow";
export { Chip, ChipButton, GarmentTag, Badge, type BadgeStatus, type ChipVariant } from "./Chip";
export { Swatch, SwatchStrip } from "./Swatch";
export { Stat, StatGroup, CountUp } from "./Stat";
export { Field, Input, Textarea, Select, FileDrop, type InputProps } from "./Field";
export { Tabs, Segmented, type TabItem } from "./Tabs";
export { Disclosure } from "./Disclosure";
export { InlineAlert, SetupHint, type AlertTone } from "./Alert";
export { toast, ToastViewport } from "./Toast";
export { EmptyState, NotConnected } from "./EmptyState";
export { Skeleton, SkeletonText } from "./Skeleton";
export { Modal, Sheet } from "./Modal";
export { Table, THead, TBody, Tr, Th, Td } from "./Table";
export { Timeline, Stepper, StepNode, type TimelineItem, type StepStatus, type StepperStep } from "./Timeline";
export { Stitch } from "./Divider";
export { ThemeToggle, ThemeSegmented } from "./ThemeToggle";
export { useTheme, setThemePreference, type Theme, type ThemePreference } from "./theme";

// Instruments
export { TapeMeasure, type TapeMeasureProps, type TapeMarker } from "./instruments/TapeMeasure";
export { Dial, type DialProps, type DialZone } from "./instruments/Dial";
export { Ring } from "./instruments/Ring";
export { Radar, type RadarSeries } from "./instruments/Radar";
export { Sparkline, FanChart, type FanPoint } from "./instruments/Charts";
export { ProgressBar } from "./instruments/ProgressBar";
