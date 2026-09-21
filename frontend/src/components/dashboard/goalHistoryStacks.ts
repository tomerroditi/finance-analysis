/**
 * Stack geometry for the savings-goals history chart.
 *
 * A month's column is one stack of per-goal segments, and Recharts stacks
 * positives upward and negatives downward in series order. Rounding every
 * segment would render a column as a string of beads, so only the segment at
 * each outer end is rounded — which is what these two helpers decide.
 *
 * They live apart from the component because the negative end is the clawback
 * case (a deficit month taking money back out of a goal), and a chart cannot
 * be asserted on in jsdom.
 */

/** A month's outer segments: the top of its positive run and the foot of its negative one. */
export interface StackEnd {
  top?: string;
  bottom?: string;
}

export type StackEnds = Map<string, StackEnd>;

/** The corner radii of a rectangle, clockwise from the top-left. */
export type CornerRadii = [number, number, number, number];

/** How much the outer end of a column is rounded, in px. */
export const STACK_CORNER_RADIUS = 4;

/**
 * Find the outer segment at each end of every month's stack.
 *
 * The last positive key present is the top of the column and the last negative
 * one is its foot, since Recharts lays segments out in series order. A key the
 * month is missing, or holds at zero, draws nothing and so can never be an end.
 *
 * @param rows - One row per month, keyed by month plus one key per goal.
 * @param keys - The series keys, in the order the chart stacks them.
 */
export function stackEnds(
  rows: Record<string, number | string>[],
  keys: string[],
): StackEnds {
  const ends: StackEnds = new Map();
  for (const row of rows) {
    const entry: StackEnd = {};
    for (const key of keys) {
      const value = row[key];
      if (typeof value !== "number" || value === 0) continue;
      if (value > 0) entry.top = key;
      else entry.bottom = key;
    }
    ends.set(String(row.month), entry);
  }
  return ends;
}

/**
 * Corner radii for one stack segment: rounded only on the column's outer end.
 *
 * A month that both funded one goal and clawed money back out of another has
 * two ends — the top of the positive run and the bottom of the negative one —
 * and both are rounded, away from the zero line.
 */
export function segmentRadius(
  ends: StackEnds,
  row: Record<string, number | string> | undefined,
  key: string,
): CornerRadii {
  const entry = row ? ends.get(String(row.month)) : undefined;
  const r = STACK_CORNER_RADIUS;
  if (entry?.top === key) return [r, r, 0, 0];
  if (entry?.bottom === key) return [0, 0, r, r];
  return [0, 0, 0, 0];
}
