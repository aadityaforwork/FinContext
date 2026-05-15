"use client";

/**
 * Icons — minimal inline-SVG line-icon set.
 *
 * Why hand-built instead of a library: zero dependency, zero bundle cost,
 * one consistent stroke language (1.75 width, round caps/joins, 24-grid).
 * Every icon inherits `currentColor` so it picks up text colour automatically
 * and is sized via the `size` prop.
 *
 * Replaces the emoji icons (📊🧭📡⚙️🎯…) that were the biggest "AI-generated"
 * tell in the old UI.
 */

const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

function Svg({ size = 16, children, ...props }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...base}
      {...props}
    >
      {children}
    </svg>
  );
}

/* ---- Navigation ---------------------------------------------------------- */

export const DashboardIcon = (p) => (
  <Svg {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Svg>
);

export const SettingsIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Svg>
);

export const TargetIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1.5" />
  </Svg>
);

/* ---- Feature glyphs ------------------------------------------------------ */

export const CompassIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M16 8l-2.5 5.5L8 16l2.5-5.5L16 8z" />
  </Svg>
);

export const SignalIcon = (p) => (
  <Svg {...p}>
    <path d="M5 12a7 7 0 0 1 7-7" />
    <path d="M5 16a11 11 0 0 1 11-11" />
    <circle cx="6" cy="18" r="1.5" />
  </Svg>
);

export const PulseIcon = (p) => (
  <Svg {...p}>
    <path d="M3 12h4l3 8 4-16 3 8h4" />
  </Svg>
);

export const LayersIcon = (p) => (
  <Svg {...p}>
    <path d="M12 3 3 8l9 5 9-5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </Svg>
);

export const RiskIcon = (p) => (
  <Svg {...p}>
    <path d="M12 3l9 16H3l9-16z" />
    <path d="M12 10v4" />
    <path d="M12 17.5v.01" />
  </Svg>
);

export const SparkIcon = (p) => (
  <Svg {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
  </Svg>
);

/* ---- Controls ----------------------------------------------------------- */

export const SearchIcon = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </Svg>
);

export const RefreshIcon = (p) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
    <path d="M21 4v5h-5" />
  </Svg>
);

export const CloseIcon = (p) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

export const ChevronRight = (p) => (
  <Svg {...p}>
    <path d="M9 6l6 6-6 6" />
  </Svg>
);

export const ChevronDown = (p) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);

export const ChevronLeft = (p) => (
  <Svg {...p}>
    <path d="M15 6l-6 6 6 6" />
  </Svg>
);

export const LogoutIcon = (p) => (
  <Svg {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="M16 17l5-5-5-5" />
    <path d="M21 12H9" />
  </Svg>
);

export const ExternalIcon = (p) => (
  <Svg {...p}>
    <path d="M14 4h6v6" />
    <path d="M20 4l-9 9" />
    <path d="M19 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6" />
  </Svg>
);

export const BellIcon = (p) => (
  <Svg {...p}>
    <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.7 21a2 2 0 0 1-3.4 0" />
  </Svg>
);

/* ---- Direction / movement ----------------------------------------------- */

export const ArrowUpRight = (p) => (
  <Svg {...p}>
    <path d="M7 17L17 7" />
    <path d="M8 7h9v9" />
  </Svg>
);

export const TrendUp = (p) => (
  <Svg {...p}>
    <path d="M3 17l6-6 4 4 8-8" />
    <path d="M14 7h7v7" />
  </Svg>
);

export const TrendDown = (p) => (
  <Svg {...p}>
    <path d="M3 7l6 6 4-4 8 8" />
    <path d="M14 17h7v-7" />
  </Svg>
);

/* ---- News category glyphs ----------------------------------------------- */

export const CompanyIcon = (p) => (
  <Svg {...p}>
    <rect x="4" y="3" width="10" height="18" rx="1.5" />
    <path d="M14 8h4a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-4" />
    <path d="M7.5 7h3M7.5 11h3M7.5 15h3" />
  </Svg>
);

export const SectorIcon = (p) => (
  <Svg {...p}>
    <path d="M3 21V9l6-4v4l6-4v16" />
    <path d="M15 21V11l6 4v6" />
    <path d="M6.5 12v.01M6.5 16v.01M18 17v.01" />
  </Svg>
);

export const MacroIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z" />
  </Svg>
);

export const GlobalIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3.5 9h17M3.5 15h17" />
    <path d="M12 3a13 13 0 0 1 0 18M12 3a13 13 0 0 0 0 18" />
  </Svg>
);

/* Map a news `category` string to its glyph — used by NewsImpactFeed. */
export const CATEGORY_ICON = {
  stock_specific: CompanyIcon,
  sector: SectorIcon,
  macro: MacroIcon,
  global: GlobalIcon,
};
