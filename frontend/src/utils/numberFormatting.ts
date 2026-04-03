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
 * Uses K/M suffixes for large values.
 * @param value - The numeric value to format
 * @returns Compact currency string (e.g., "₪12K", "₪1.5M")
 */
export function formatCompactCurrency(value: number): string {
  const abs = Math.abs(value || 0);
  if (abs >= 1_000_000) return `₪${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `₪${(value / 1_000).toFixed(0)}K`;
  if (abs >= 1_000) return `₪${(value / 1_000).toFixed(1)}K`;
  return formatCurrency(value);
}
