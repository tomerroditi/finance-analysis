/**
 * Format a number as Israeli Shekel currency (₪).
 * @param value - The numeric value to format
 * @param maximumFractionDigits - Decimal places (default: 0)
 * @returns Formatted currency string (e.g., "₪1,234")
 */
export function formatCurrency(value: number, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits,
  }).format(value || 0);
}

/**
 * Format currency in compact form for small UI spaces (KPI cards, badges).
 * Canonical layout: sign-currency-magnitude with no spaces (e.g., "₪12K", "-₪1.5M").
 * Uses K/M suffixes for large values; small values render in full but with the same
 * sign-then-currency layout (e.g., "-₪132") so deltas across cards look identical.
 * @param value - The numeric value to format
 * @returns Compact currency string
 */
export function formatCompactCurrency(value: number): string {
  const v = value || 0;
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}₪${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}₪${(abs / 1_000).toFixed(0)}K`;
  if (abs >= 1_000) return `${sign}₪${(abs / 1_000).toFixed(1)}K`;
  return `${sign}₪${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/**
 * Format a delta/change value with explicit sign for KPI deltas and trend cards.
 * Canonical layout: sign-currency-magnitude (e.g., "+₪35K", "-₪20K", "+₪150").
 * Always includes a leading "+" or "-" so positive/negative changes look consistent.
 * @param value - The change amount
 * @param options.compact - Use K/M suffixes (default: true)
 * @returns Signed compact currency string
 */
export function formatChange(value: number, options: { compact?: boolean } = {}): string {
  const { compact = true } = options;
  const v = value || 0;
  const sign = v >= 0 ? "+" : "-";
  const abs = Math.abs(v);
  if (compact) {
    if (abs >= 1_000_000) return `${sign}₪${(abs / 1_000_000).toFixed(1)}M`;
    if (abs >= 10_000) return `${sign}₪${(abs / 1_000).toFixed(0)}K`;
    if (abs >= 1_000) return `${sign}₪${(abs / 1_000).toFixed(1)}K`;
  }
  return `${sign}₪${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/**
 * Format a percent change with explicit sign (e.g., "+1.6%", "-2.5%").
 * @param value - The percent value (e.g., 1.6 for 1.6%)
 * @param fractionDigits - Decimal places (default: 1)
 * @returns Signed percent string
 */
export function formatPercentChange(value: number, fractionDigits = 1): string {
  const v = value || 0;
  const sign = v >= 0 ? "+" : "-";
  return `${sign}${Math.abs(v).toFixed(fractionDigits)}%`;
}
