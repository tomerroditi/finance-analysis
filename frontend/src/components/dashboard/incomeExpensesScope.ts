import { formatMonthShort } from "../../utils/dateFormatting";

/**
 * Period folding behind the Income & Expenses card's monthly/yearly scope
 * toggle.
 *
 * Every analytics series the card reads is keyed by month ("YYYY-MM"), so the
 * yearly scope is a pure client-side fold: no endpoint, no extra request, and
 * the two scopes can never disagree about what a year cost. A period key
 * doubles as its own scope marker — "2026" is a year, "2026-06" a month — so
 * a row only has to carry its key to know how to label itself.
 */

/** Which period the card aggregates by. */
export type Scope = "monthly" | "yearly";

/** One totals row: a period with its income and expense sums. */
export type LedgerRow = { month: string; income: number; expenses: number };

/** One breakdown row: a period with an amount per series (category / source). */
export type CompositionRow = { month: string; values: Record<string, number> };

/** True when a period key names a whole year ("2026") rather than a month ("2026-06"). */
export function isYearKey(period: string): boolean {
  return !period.includes("-");
}

/** Row label for either kind of period key: the bare year, or "Jun '26". */
export function formatPeriodLabel(period: string): string {
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
