/**
 * Bidi-stable LTR wrapping. Every currency string we emit is wrapped in
 * U+2066 (LRI, Left-to-Right Isolate) ... U+2069 (PDI, Pop Directional
 * Isolate) so the digits + currency render left-to-right regardless of
 * the surrounding paragraph direction, and a U+00A0 (NBSP) glues the
 * digits to ₪ so they never line-wrap apart. This means consumers under
 * RTL no longer have to remember `dir="ltr"` on every span — the string
 * itself is bidi-stable.
 */
const LRI = "⁦";
const PDI = "⁩";
const NBSP = " ";

function wrapCurrency(sign: string, body: string): string {
  return `${LRI}${sign}${body}${NBSP}₪${PDI}`;
}

/**
 * Format a number as Israeli Shekel currency (₪).
 * Canonical layout: sign-magnitude-currency with NBSP before ₪
 * (e.g., "1,234 ₪", "-132 ₪"). The result is wrapped in LRI/PDI so the
 * digits-then-shekel order is preserved under both LTR and RTL.
 * Matches `formatCompactCurrency` / `formatChange` so the main KPI
 * value and its delta below render with the shekel sign on the same
 * side (Israeli convention: ₪ after digits).
 * @param value - The numeric value to format
 * @param maximumFractionDigits - Decimal places (default: 0)
 * @returns Formatted currency string (e.g., "1,234 ₪")
 */
export function formatCurrency(value: number, maximumFractionDigits = 0): string {
  const v = value || 0;
  const sign = v < 0 ? "-" : "";
  const magnitude = Math.abs(v).toLocaleString("en-US", { maximumFractionDigits });
  return wrapCurrency(sign, magnitude);
}

/**
 * Format currency in compact form for small UI spaces (KPI cards, badges).
 * Canonical layout: sign-magnitude-currency (e.g., "12K ₪", "-1.5M ₪").
 * Uses K/M suffixes for large values; small values render in full but with the
 * same sign-magnitude-currency layout (e.g., "-132 ₪") so deltas across cards
 * look identical.
 * @param value - The numeric value to format
 * @returns Compact currency string
 */
export function formatCompactCurrency(value: number): string {
  const v = value || 0;
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1_000_000) return wrapCurrency(sign, `${(abs / 1_000_000).toFixed(1)}M`);
  if (abs >= 10_000) return wrapCurrency(sign, `${(abs / 1_000).toFixed(0)}K`);
  if (abs >= 1_000) return wrapCurrency(sign, `${(abs / 1_000).toFixed(1)}K`);
  return wrapCurrency(sign, abs.toLocaleString("en-US", { maximumFractionDigits: 0 }));
}

/**
 * Format a delta/change value with explicit sign for KPI deltas and trend cards.
 * Canonical layout: sign-magnitude-currency (e.g., "+35K ₪", "-20K ₪", "+150 ₪").
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
    if (abs >= 1_000_000) return wrapCurrency(sign, `${(abs / 1_000_000).toFixed(1)}M`);
    if (abs >= 10_000) return wrapCurrency(sign, `${(abs / 1_000).toFixed(0)}K`);
    if (abs >= 1_000) return wrapCurrency(sign, `${(abs / 1_000).toFixed(1)}K`);
  }
  return wrapCurrency(sign, abs.toLocaleString("en-US", { maximumFractionDigits: 0 }));
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
