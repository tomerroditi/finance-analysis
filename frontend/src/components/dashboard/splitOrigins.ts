import type { SplitFrom } from "../../services/api";
import type { CompositionRow } from "./incomeExpensesScope";

/**
 * The "By original tag" reading of the Income & Expenses breakdowns.
 *
 * A split moves part of a transaction onto another tag, and the breakdowns
 * count each part under the tag it now carries. That is the right default, but
 * it hides where the money came from: a ₪3,000 Bit transfer split into ₪1,000
 * of bonus reads as a bonus and nothing else. The backend therefore reports,
 * per series, how much of it a split carried over from a parent tagged
 * otherwise (`split_from`), and this module turns that into two things the card
 * can draw:
 *
 * - **origin rows**, one per period, holding each carried amount under an
 *   {@link originKey}. They fold through the same scope helpers as the
 *   breakdown rows, so a year or the whole window reports its origins the same
 *   way it reports its totals.
 * - **{@link byOriginalTag}**, which moves those amounts back under the parent
 *   as a pseudo-series. The card draws a pseudo-series hatched in the colour of
 *   the tag the money carries now, so the reading keeps both tags in view.
 *
 * Only one level is tracked: a part of a part points at its direct parent.
 */

/**
 * Separator inside an origin key. No category or tag name can contain it, so a
 * key is never mistaken for a real series.
 */
const ORIGIN_SEP = "\u0000";

/** The pseudo-series for money a split moved from `parent` to `child`. */
export function originKey(parent: string, child: string): string {
  return `${parent}${ORIGIN_SEP}${child}`;
}

/** The two tags behind an origin key, or null for a real series name. */
export function parseOriginKey(key: string): { parent: string; child: string } | null {
  const at = key.indexOf(ORIGIN_SEP);
  if (at < 0) return null;
  return { parent: key.slice(0, at), child: key.slice(at + 1) };
}

/** What a series is called on screen: a pseudo-series is named after its parent. */
export function seriesLabel(key: string): string {
  return parseOriginKey(key)?.parent ?? key;
}

/**
 * Diagonal stripes in `color` over the bar's own background — the mark for
 * "this money carries another tag now".
 */
export function hatchFill(color: string): string {
  return `repeating-linear-gradient(135deg, ${color} 0 3px, transparent 3px 6px)`;
}

/** The CSS background a series is drawn with: solid, or hatched for a pseudo-series. */
export function seriesFill(key: string, colorOf: (name: string) => string): string {
  return parseOriginKey(key) ? hatchFill(colorOf(key)) : colorOf(key);
}

/**
 * A colour lookup that also answers for pseudo-series, with the colour of the
 * tag the money carries now (the split's own tag).
 */
export function withOriginColors(colorOf: (name: string) => string): (name: string) => string {
  return (name: string) => colorOf(parseOriginKey(name)?.child ?? name);
}

/** One origin row per period, keyed by {@link originKey}. */
export function toOriginRows(
  rows: { month: string; split_from?: SplitFrom }[],
): CompositionRow[] {
  return rows.map((row) => {
    const values: Record<string, number> = {};
    for (const [child, parents] of Object.entries(row.split_from ?? {})) {
      for (const [parent, amount] of Object.entries(parents)) {
        values[originKey(parent, child)] = amount;
      }
    }
    return { month: row.month, values };
  });
}

/** Whether any period carries split money, i.e. whether the toggle has anything to show. */
export function hasOrigins(originRows: CompositionRow[]): boolean {
  return originRows.some((row) => Object.values(row.values).some((v) => v > 0));
}

/**
 * The parents a series' money was split from in one period, largest first —
 * the tooltip's "split from" lines.
 */
export function originsOf(
  originRow: CompositionRow | undefined,
  child: string,
): { parent: string; amount: number }[] {
  if (!originRow) return [];
  return Object.entries(originRow.values)
    .map(([key, amount]) => ({ origin: parseOriginKey(key), amount }))
    .filter(
      (e): e is { origin: { parent: string; child: string }; amount: number } =>
        e.origin?.child === child && e.amount > 0,
    )
    .map((e) => ({ parent: e.origin.parent, amount: e.amount }))
    .sort((a, b) => b.amount - a.amount);
}

/** Drop the float residue a subtraction leaves, so a fully split series disappears. */
function settle(value: number): number {
  return Math.abs(value) < 0.005 ? 0 : value;
}

/**
 * Move every split-carried amount from the tag it carries now back under its
 * parent, as a pseudo-series. Each period's total is unchanged — the money
 * only changes which bar segment it is drawn in.
 */
export function byOriginalTag(rows: CompositionRow[], originRows: CompositionRow[]): CompositionRow[] {
  const origins = new Map(originRows.map((row) => [row.month, row.values]));
  return rows.map((row) => {
    const carried = origins.get(row.month);
    if (!carried) return row;
    const values = { ...row.values };
    for (const [key, amount] of Object.entries(carried)) {
      const origin = parseOriginKey(key);
      if (!origin || !(amount > 0)) continue;
      const left = settle((values[origin.child] ?? 0) - amount);
      if (left === 0) delete values[origin.child];
      else values[origin.child] = left;
      values[key] = (values[key] ?? 0) + amount;
    }
    return { month: row.month, values };
  });
}

/**
 * Fold every pseudo-series back into its parent, so a single-series view (the
 * focused one) counts all the money that started under that tag.
 */
export function mergeOrigins(rows: CompositionRow[]): CompositionRow[] {
  return rows.map((row) => {
    const values: Record<string, number> = {};
    for (const [key, value] of Object.entries(row.values)) {
      const name = seriesLabel(key);
      values[name] = (values[name] ?? 0) + value;
    }
    return { month: row.month, values };
  });
}

/**
 * Series order with each pseudo-series right after its parent, so a parent's
 * own money and the money split away from it sit side by side in a bar.
 */
export function withOriginSeries(series: string[], originRows: CompositionRow[]): string[] {
  const keys = Array.from(new Set(originRows.flatMap((row) => Object.keys(row.values))));
  const order = [...series];
  for (const key of keys) {
    const parent = seriesLabel(key);
    const at = order.lastIndexOf(parent);
    let insert = order.length;
    if (at >= 0) {
      insert = at + 1;
      while (insert < order.length && seriesLabel(order[insert]) === parent) insert += 1;
    }
    order.splice(insert, 0, key);
  }
  return order;
}
