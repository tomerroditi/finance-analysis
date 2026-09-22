import { formatMonthShort } from "../../utils/dateFormatting";

/**
 * Period folding behind the Income & Expenses card's monthly/yearly/all scope
 * toggle.
 *
 * Every analytics series the card reads is keyed by month ("YYYY-MM"), so the
 * yearly and all-time scopes are pure client-side folds: no endpoint, no extra
 * request, and no two scopes can disagree about what a year cost. A period key
 * doubles as its own scope marker — "2026" is a year, "2026-06" a month,
 * {@link ALL_PERIOD} the whole window — so a row only has to carry its key to
 * know how to label itself.
 */

/** Which period the card aggregates by. */
export type Scope = "monthly" | "yearly" | "all";

/**
 * The period key every row folds onto in the "all" scope. It is deliberately
 * not a date: "2026" already means a year and "2026-06" a month, so the third
 * scope needs a key no calendar can produce.
 */
export const ALL_PERIOD = "all";

/**
 * How much history the "all" scope folds. The monthly/yearly scopes show
 * every period they have and let the pager walk back, but a single all-time
 * figure has no rows to page through — the window is the only way to ask it
 * about a shorter span.
 */
export type RangeWindow = "all" | "year" | "last12m";

/** One totals row: a period with its income and expense sums. */
export type LedgerRow = { month: string; income: number; expenses: number };

/** One breakdown row: a period with an amount per series (category / source). */
export type CompositionRow = { month: string; values: Record<string, number> };

/** True when a period key is the all-scope fold rather than a real period. */
export function isAllKey(period: string): boolean {
  return period === ALL_PERIOD;
}

/** True when a period key names a whole year ("2026") rather than a month ("2026-06"). */
export function isYearKey(period: string): boolean {
  return !isAllKey(period) && !period.includes("-");
}

/**
 * Row label for any period key: the all-scope label, the bare year, or
 * "Jun '26". The all-scope label is passed in because it is the one label
 * that is a translated phrase rather than a formatted date.
 */
export function formatPeriodLabel(period: string, allLabel = "All time"): string {
  if (isAllKey(period)) return allLabel;
  return isYearKey(period) ? period : formatMonthShort(period);
}

/** Chronological order over "YYYY" and "YYYY-MM" keys alike (both sort lexically). */
function byPeriod<T extends { month: string }>(a: T, b: T): number {
  return a.month.localeCompare(b.month);
}

/** Sum monthly totals rows into one row per calendar year. */
export function toYearlyLedger(rows: LedgerRow[]): LedgerRow[] {
  const years = new Map<string, LedgerRow>();
  for (const row of rows) {
    const year = row.month.slice(0, 4);
    const acc = years.get(year) ?? { month: year, income: 0, expenses: 0 };
    acc.income += row.income;
    acc.expenses += row.expenses;
    years.set(year, acc);
  }
  return [...years.values()].sort(byPeriod);
}

/** Sum monthly breakdown rows into one row per calendar year, series by series. */
export function toYearlyComposition(rows: CompositionRow[]): CompositionRow[] {
  const years = new Map<string, CompositionRow>();
  for (const row of rows) {
    const year = row.month.slice(0, 4);
    const acc = years.get(year) ?? { month: year, values: {} };
    for (const [name, value] of Object.entries(row.values)) {
      acc.values[name] = (acc.values[name] ?? 0) + value;
    }
    years.set(year, acc);
  }
  return [...years.values()].sort(byPeriod);
}

/** A calendar year's total, with how many months of it the series actually covers. */
export type YearTotal = { year: string; value: number; months: number };

/**
 * KPI figures for the yearly scope: the running year, the two before it, and
 * the baseline its trend chip compares against.
 */
export type YearlyKpi = {
  /** The most recent year in the series. */
  latest: YearTotal;
  /** The two years before it, newest first (fewer when history is short). */
  earlier: YearTotal[];
  /** What the previous year had made by this point — see {@link yearlyKpi}. */
  baseline: number;
  /** Whether `latest` is still running (fewer than 12 months of data). */
  partial: boolean;
};

/** Fold a monthly series into per-year totals, oldest year first. */
export function totalsByYear(rows: { month: string; value: number }[]): YearTotal[] {
  const years = new Map<string, YearTotal>();
  for (const row of rows) {
    const year = row.month.slice(0, 4);
    const acc = years.get(year) ?? { year, value: 0, months: 0 };
    acc.value += row.value;
    acc.months += 1;
    years.set(year, acc);
  }
  return [...years.values()].sort((a, b) => a.year.localeCompare(b.year));
}

/** Sum the first `months` months of one year's rows. */
function sumFirstMonths(
  rows: { month: string; value: number }[],
  year: string,
  months: number,
): number {
  return rows
    .filter((r) => r.month.slice(0, 4) === year)
    .sort((a, b) => a.month.localeCompare(b.month))
    .slice(0, months)
    .reduce((s, r) => s + r.value, 0);
}

/**
 * Build the yearly KPI figures from a monthly series.
 *
 * The trend chip's baseline is like-for-like: while the latest year is still
 * running, it is the previous year summed over the *same number of elapsed
 * months*, not its full-year total. Comparing three months of one year to
 * twelve of another would show every January as a collapse in income and
 * every December as a boom, which says nothing about the household.
 */
export function yearlyKpi(rows: { month: string; value: number }[]): YearlyKpi | null {
  const totals = totalsByYear(rows);
  if (totals.length === 0) return null;

  const latest = totals[totals.length - 1];
  const previous = totals[totals.length - 2];
  const partial = latest.months < 12;
  return {
    latest,
    earlier: totals.slice(0, -1).reverse().slice(0, 2),
    baseline: previous
      ? partial
        ? sumFirstMonths(rows, previous.year, latest.months)
        : previous.value
      : 0,
    partial,
  };
}


/** Sum every monthly totals row into the single all-scope row. */
export function toAllLedger(rows: LedgerRow[]): LedgerRow[] {
  if (rows.length === 0) return [];
  const acc: LedgerRow = { month: ALL_PERIOD, income: 0, expenses: 0 };
  for (const row of rows) {
    acc.income += row.income;
    acc.expenses += row.expenses;
  }
  return [acc];
}

/** Sum every monthly breakdown row into the single all-scope row, series by series. */
export function toAllComposition(rows: CompositionRow[]): CompositionRow[] {
  if (rows.length === 0) return [];
  const acc: CompositionRow = { month: ALL_PERIOD, values: {} };
  for (const row of rows) {
    for (const [name, value] of Object.entries(row.values)) {
      acc.values[name] = (acc.values[name] ?? 0) + value;
    }
  }
  return [acc];
}

/** The "YYYY-MM" key `offset` months before `today` (0 = this month). */
function monthKeyBefore(today: Date, offset: number): string {
  const d = new Date(today.getFullYear(), today.getMonth() - offset, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Narrow a monthly series to one of the all-scope windows.
 *
 * The bounds are month keys compared as strings, not dates: every series the
 * card holds is already monthly, so a day-level bound could only ever be
 * rounded to a whole month anyway, and comparing the keys directly keeps the
 * window free of time zones (a `Date` built from "2026-06" is UTC midnight,
 * which is the previous month west of Greenwich).
 */
export function sliceWindow<T extends { month: string }>(
  rows: T[],
  window: RangeWindow,
  today: Date = new Date(),
): T[] {
  if (window === "all") return rows;
  if (window === "year") {
    const year = String(today.getFullYear());
    return rows.filter((r) => r.month.slice(0, 4) === year);
  }
  const from = monthKeyBefore(today, 11);
  return rows.filter((r) => r.month >= from);
}

/** All-time KPI figures: the windowed total and what it averages per month. */
export type AllKpi = { total: number; months: number; perMonth: number };

/**
 * Fold a monthly series into its all-scope KPI.
 *
 * `months` counts the rows the series actually carries, not the calendar span
 * of the window — a household that started tracking in March should see its
 * real monthly average, not one divided by a January and February it has no
 * data for.
 */
export function allTimeKpi(rows: { month: string; value: number }[]): AllKpi {
  const total = rows.reduce((s, r) => s + r.value, 0);
  const months = rows.length;
  return { total, months, perMonth: months ? total / months : 0 };
}

/**
 * Bar-scale cap = median(positive values) × `multiplier`. Anchoring to the
 * median (not the max or a high percentile) keeps typical periods in the
 * mid-range with headroom, even when the data clusters on one value (e.g. a
 * constant salary) where a percentile would collapse onto the cluster and max
 * out every bar. Values above the cap are drawn full-width and flagged as
 * outliers — their exact ₪ label still tells the true story.
 *
 * Feed this one series at a time. The ledger derives a cap per column rather
 * than one over income and expenses together — see `LedgerView`.
 */
export function barCap(values: number[], multiplier = 1.6): number {
  const positives = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (positives.length === 0) return 1;
  const median = positives[Math.floor(positives.length / 2)];
  return (median || positives[positives.length - 1] || 1) * multiplier;
}
