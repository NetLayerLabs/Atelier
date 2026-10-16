import type { ReactNode, SVGProps } from "react";

/**
 * Atelier icon set: 24px grid, 1.75 round stroke, `currentColor`. Drawn for this app (craft motifs: needle,
 * thread, ruler, scissors, tag, swatch). Use at 14–20px; inside a 28–32px round button use 14–16px.
 * Icons are decorative by default (aria-hidden); label the control that holds them instead.
 */
export type IconProps = Omit<SVGProps<SVGSVGElement>, "children"> & { size?: number; strokeWidth?: number };

function make(name: string, body: ReactNode) {
  function Icon({ size = 18, strokeWidth = 1.75, ...rest }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
        focusable="false"
        {...rest}
      >
        {body}
      </svg>
    );
  }
  Icon.displayName = `Icon${name}`;
  return Icon;
}

export const IconPlus = make("Plus", <path d="M12 5v14M5 12h14" />);
export const IconClose = make("Close", <path d="M6 6l12 12M18 6L6 18" />);
export const IconCheck = make("Check", <path d="M5 12.5l4.5 4.5L19 7.5" />);
export const IconArrowUpRight = make("ArrowUpRight", <path d="M7 17L17 7M9 7h8v8" />);
export const IconArrowRight = make("ArrowRight", <path d="M5 12h14M13 6l6 6-6 6" />);
export const IconArrowLeft = make("ArrowLeft", <path d="M19 12H5M11 6l-6 6 6 6" />);
export const IconArrowDown = make("ArrowDown", <path d="M12 5v14M6 13l6 6 6-6" />);
export const IconChevronDown = make("ChevronDown", <path d="M6 9l6 6 6-6" />);
export const IconChevronRight = make("ChevronRight", <path d="M9 6l6 6-6 6" />);
export const IconRefresh = make(
  "Refresh",
  <>
    <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8" />
    <path d="M4 4v4h4" />
    <path d="M4 13a8 8 0 0 0 14.3 4.9L20 16" />
    <path d="M20 20v-4h-4" />
  </>,
);
export const IconUpload = make(
  "Upload",
  <>
    <path d="M12 15V4M7.5 8.5L12 4l4.5 4.5" />
    <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </>,
);
export const IconExternal = make(
  "External",
  <>
    <path d="M14 4h6v6M20 4l-9 9" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </>,
);
export const IconSun = make(
  "Sun",
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4" />
  </>,
);
export const IconMoon = make("Moon", <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />);
export const IconPlay = make("Play", <path d="M8 5.5v13l10.5-6.5z" fill="currentColor" strokeWidth={1.2} />);
export const IconPause = make("Pause", <path d="M9 6v12M15 6v12" />);
export const IconStop = make("Stop", <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" strokeWidth={1.2} />);
/** Inference: a pulse trace (telemetry). */
export const IconPulse = make("Pulse", <path d="M3 12h4l2-5 4 10 2-5h6" />);
/** System status: a signal beacon. */
export const IconSignal = make(
  "Signal",
  <>
    <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    <path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8" />
  </>,
);
export const IconInfo = make(
  "Info",
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5.5M12 7.6v.01" />
  </>,
);
export const IconAlert = make(
  "Alert",
  <>
    <path d="M10.3 4.2L2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z" />
    <path d="M12 9.5v4.5M12 17v.01" />
  </>,
);
export const IconLock = make(
  "Lock",
  <>
    <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
    <path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" />
  </>,
);
export const IconUnplug = make(
  "Unplug",
  <>
    <path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0V7zM12 16v5" />
    <path d="M3 3l18 18" />
  </>,
);
export const IconMail = make(
  "Mail",
  <>
    <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
    <path d="M3.5 7l8.5 6 8.5-6" />
  </>,
);
export const IconStore = make(
  "Store",
  <>
    <path d="M4 9.5L5.5 4h13L20 9.5M4 9.5h16M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0" />
    <path d="M5.5 12.5V20h13v-7.5M10 20v-4.5h4V20" />
  </>,
);
export const IconImage = make(
  "Image",
  <>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <circle cx="9" cy="9.5" r="1.8" />
    <path d="M21 16l-5-5-9 9" />
  </>,
);
export const IconMessage = make("Message", <path d="M4 5.5h16v10H10l-4.5 4v-4H4z" />);
export const IconDocument = make(
  "Document",
  <>
    <path d="M6 3h8l4 4v14H6z" />
    <path d="M14 3v4h4M9 12h6M9 15.5h6M9 9h2" />
  </>,
);
export const IconChart = make(
  "Chart",
  <>
    <path d="M4 4v16h16" />
    <path d="M7 15l4-4 3 3 5-6" />
  </>,
);
export const IconLayers = make(
  "Layers",
  <>
    <path d="M12 3.5l9 5-9 5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </>,
);
export const IconEye = make(
  "Eye",
  <>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </>,
);
export const IconMenu = make("Menu", <path d="M4 8h16M4 16h16" />);
export const IconGrid = make(
  "Grid",
  <>
    <circle cx="8" cy="8" r="1.6" fill="currentColor" />
    <circle cx="16" cy="8" r="1.6" fill="currentColor" />
    <circle cx="8" cy="16" r="1.6" fill="currentColor" />
    <circle cx="16" cy="16" r="1.6" fill="currentColor" />
  </>,
);

// Craft motifs ------------------------------------------------------------------------------------------------

/** Needle with thread: Studio, creative direction. */
export const IconNeedle = make(
  "Needle",
  <>
    <path d="M19.5 4.5L6 18l-1.5 1.5" />
    <path d="M17 4.2a1.6 1.6 0 0 1 2.8 2.8" />
    <path d="M17.5 6.5c-4 1-9 2.5-8 6s6 1.5 4.5 5.5" />
  </>,
);
/** Tape measure / ruler: measurements, forecasts, the TapeMeasure instrument. */
export const IconRuler = make(
  "Ruler",
  <>
    <rect x="2.5" y="8" width="19" height="8" rx="1.5" />
    <path d="M6.5 8v3M10.5 8v4.5M14.5 8v3M18.5 8v4.5" />
  </>,
);
export const IconScissors = make(
  "Scissors",
  <>
    <circle cx="6" cy="6.5" r="2.5" />
    <circle cx="6" cy="17.5" r="2.5" />
    <path d="M8.2 7.8L20 17M8.2 16.2L20 7" />
  </>,
);
/** Garment tag: SKUs, labels, prices. */
export const IconTag = make(
  "Tag",
  <>
    <path d="M3.5 12.5V4.5a1 1 0 0 1 1-1h8L21 12l-8.5 8.5z" />
    <circle cx="8" cy="8" r="1.5" />
  </>,
);
/** Fabric swatch with a pinked edge: palettes, materials. */
export const IconSwatch = make(
  "Swatch",
  <path d="M5 4h14v12l-1.75 2-1.75-2-1.75 2-1.75-2-1.75 2-1.75-2-1.75 2L5 16z" />,
);
/** Spool of thread: the pipeline / production. */
export const IconSpool = make(
  "Spool",
  <>
    <path d="M6 4h12M6 20h12" />
    <path d="M8 4v16M16 4v16" />
    <path d="M8 8l8 2M8 12l8 2M8 16l8-1" />
  </>,
);
/** Hanger: collection / garments. */
export const IconHanger = make(
  "Hanger",
  <>
    <path d="M12 8.5a2 2 0 1 0-2-2" />
    <path d="M12 8.5v1.5L3.5 16.5a1 1 0 0 0 .6 1.8h15.8a1 1 0 0 0 .6-1.8L12 10" />
  </>,
);
/** Box / purchase order. */
export const IconBox = make(
  "Box",
  <>
    <path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z" />
    <path d="M3.5 7.5L12 12l8.5-4.5M12 12v9" />
  </>,
);
/** A spark: AI suggestion (use sparingly). */
export const IconSpark = make(
  "Spark",
  <path d="M12 3.5l1.8 5.2 5.2 1.8-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8z" />,
);
export const IconUser = make(
  "User",
  <>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 20a7 7 0 0 1 14 0" />
  </>,
);
export const IconKey = make(
  "Key",
  <>
    <circle cx="8" cy="15" r="4" />
    <path d="M11 12l9-9M16 7l3 3" />
  </>,
);
