import { format, startOfYear, subMonths } from "date-fns";

/**
 * Named windows a dashboard card can be read over. `all` means unbounded —
 * every transaction on record.
 */
export type RangePreset = "all" | "year" | "last12m";

/** An inclusive ISO (`YYYY-MM-DD`) window; an absent bound is unbounded. */
export interface DateRange {
  start?: string;
  end?: string;
}

/**
 * Resolve a named preset into inclusive ISO date bounds, relative to `now`.
 *
 * Deliberately formatted from the LOCAL calendar rather than
 * `toISOString()`: the latter serialises the UTC instant, so in any
 * positive-offset zone (Israel is UTC+2/+3) every moment between local
 * midnight and 02:00/03:00 resolves the window a day early. `subMonths` also
 * clamps month-ends properly — a trailing window measured from the 31st lands
 * on the 28th/30th rather than skidding forward into the current month the way
 * `setMonth(getMonth() - n)` does.
 *
 * @param preset - Which named window to resolve
 * @param now - Reference "today" (defaults to the current time)
 * @returns Inclusive `{start, end}` ISO bounds; `{}` for `all`
 */
export function resolveRangePreset(preset: RangePreset, now: Date = new Date()): DateRange {
  if (preset === "all") return {};
  const iso = (d: Date) => format(d, "yyyy-MM-dd");
  const end = iso(now);
  if (preset === "year") return { start: iso(startOfYear(now)), end };
  return { start: iso(subMonths(now, 12)), end };
}
