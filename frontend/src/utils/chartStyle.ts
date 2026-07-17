/**
 * Shared styling constants for the Recharts-based chart system — the "soft
 * gradient" dark look. Charts deliberately strip chrome (no gridlines, no axis
 * lines, no tick marks) so they read as product UI rather than technical
 * plots; tick labels stay for readability.
 */

export const isTouchDevice =
  typeof window !== "undefined" &&
  (navigator.maxTouchPoints > 0 || "ontouchstart" in window);

/**
 * Soft, modern categorical palette (fintech aesthetic). Use this everywhere a
 * chart needs to cycle colours instead of rolling a per-file rainbow array, so
 * the whole dashboard stays visually consistent.
 */
export const CHART_COLORS = [
  "#3b82f6", // blue (primary)
  "#10b981", // emerald
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
  "#84cc16", // lime
];

/** Surface colour used to separate donut/pie segments (matches --surface). */
export const CHART_SURFACE_COLOR = "#1e293b";

/** Muted tick-label colour (slate-500). */
export const CHART_TICK_COLOR = "#64748b";

/** Default axis text colour for titles/labels (slate-400). */
export const CHART_TEXT_COLOR = "#94a3b8";

/** Corner radius (px) for vertical bars — the soft rounded-bar look. */
export const BAR_RADIUS: [number, number, number, number] = [6, 6, 0, 0];

/**
 * Spread into every `<XAxis>` / `<YAxis>`: hides the axis/tick lines and
 * styles tick labels, matching the chrome-free theme.
 */
export const AXIS_DEFAULTS = {
  axisLine: false,
  tickLine: false,
  tick: { fill: CHART_TICK_COLOR, fontSize: 11 },
} as const;

/** Convert a `#rrggbb` hex string to an `rgba(...)` string at the given alpha. */
export function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Compact axis-tick number: 1500000 → "1.5M", 25000 → "25K", -1200 → "-1.2K".
 * Plain numbers only (no currency symbol) — keeps y-axis margins tight.
 */
export function formatAxisNumber(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000) {
    return `${sign}${trimZero((abs / 1_000_000).toFixed(1))}M`;
  }
  if (abs >= 1_000) {
    return `${sign}${trimZero((abs / 1_000).toFixed(1))}K`;
  }
  return `${sign}${Math.round(abs)}`;
}

function trimZero(s: string): string {
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}
