import { Rectangle } from "recharts";

/**
 * Rounded ends for stacked bar charts.
 *
 * A stacked column is several segments drawn end to end, so rounding each one
 * renders the column as a string of beads. Only the segment at each outer end
 * of a column should be rounded, which is what these helpers decide.
 *
 * ## Why both ends use the same radii
 *
 * Recharts gives a bar `y` at the *value* end and a `height` signed away from
 * the axis: a positive bar has `y` at its top with a positive height, and a
 * negative one has `y` at its bottom tip with a negative height. Its rectangle
 * path applies `radius[0]` and `radius[1]` at `y` either way, so
 * `[r, r, 0, 0]` rounds the tip of a bar in both directions — and
 * `[0, 0, r, r]` on a negative bar rounds where it *meets* the axis, leaving
 * the tip square. `stackedBarShape.test.tsx` pins that behaviour against the
 * installed Recharts.
 */

/** A month's outer segments: the end of its positive run and of its negative one. */
export interface StackEnd {
  top?: string;
  bottom?: string;
}

/** Outer segments per x value. */
export type StackEnds = Map<string, StackEnd>;

/** The corner radii of a rectangle, clockwise from the top-left. */
export type CornerRadii = [number, number, number, number];

/** How much the outer end of a column is rounded, in px. */
export const STACK_CORNER_RADIUS = 4;

/** A chart row: one x value plus a numeric column per series. */
export type StackRow = Record<string, number | string>;

/**
 * Find the outer segment at each end of every column's stack.
 *
 * The last positive key present is the top of the column and the last negative
 * one is its foot, since Recharts lays segments out in series order. A key the
 * row is missing, or holds at zero, draws nothing and so can never be an end.
 *
 * @param rows - Chart rows, one per x value.
 * @param keys - Series keys, in the order the chart stacks them.
 * @param xKey - The row field holding the x value (e.g. "month", "age").
 */
export function stackEnds(
  rows: StackRow[],
  keys: string[],
  xKey: string,
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
    ends.set(String(row[xKey]), entry);
  }
  return ends;
}

/**
 * Corner radii for one stack segment: rounded only at the column's outer end.
 *
 * A column that both funded one goal and clawed money back out of another has
 * two ends — the top of its positive run and the foot of its negative one —
 * and each is rounded away from the axis (see the note above on why the same
 * radii serve both).
 */
export function stackSegmentRadius(
  ends: StackEnds,
  row: StackRow | undefined,
  key: string,
  xKey: string,
): CornerRadii {
  const entry = row ? ends.get(String(row[xKey])) : undefined;
  const r = STACK_CORNER_RADIUS;
  return entry?.top === key || entry?.bottom === key ? [r, r, 0, 0] : [0, 0, 0, 0];
}

/** The geometry Recharts hands a bar's custom shape. */
export interface BarShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  payload?: StackRow;
}

/**
 * Build the `shape` for one series of a stacked bar chart.
 *
 * @param ends - Outer segments per x value, from {@link stackEnds}.
 * @param key - This series' data key.
 * @param xKey - The row field holding the x value.
 * @param fill - Overrides the series fill, for a gradient (`url(#…)`) the
 *   legend swatch cannot paint.
 */
export function roundedStackShape(
  ends: StackEnds,
  key: string,
  xKey: string,
  fill?: string,
) {
  return function StackSegment(props: BarShapeProps) {
    const { x = 0, y = 0, width = 0, height = 0, payload } = props;
    if (width <= 0 || height === 0) return null;
    const radius = stackSegmentRadius(ends, payload, key, xKey);
    // A segment can arrive shorter than its own corner radius (a small
    // allocation beside a large one). Recharts caps the radius at half the
    // rectangle anyway; clamping here keeps the intent local and explicit.
    const limit = Math.min(width / 2, Math.abs(height));
    const clamped = radius.map((r) => Math.min(r, limit)) as CornerRadii;
    return (
      <Rectangle
        x={x}
        y={y}
        width={width}
        height={height}
        fill={fill ?? props.fill}
        radius={clamped}
      />
    );
  };
}

/** The y-axis a stacked chart should draw: its extent and where to label it. */
export interface StackAxis {
  domain: [number, number];
  ticks: number[];
}

/** Round a raw tick spacing up to 1, 2, 2.5 or 5 times a power of ten. */
function niceStep(raw: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const step = [1, 2, 2.5, 5, 10].find((candidate) => normalized <= candidate) ?? 10;
  return step * magnitude;
}

/**
 * Size a stacked chart's y-axis to the stacks it actually draws.
 *
 * Left to itself, Recharts rounds a mixed-sign domain out to whole tick steps
 * on both sides, so one small negative segment (a withdrawal, a clawback)
 * reserved a whole empty step under the zero line — a third of the plot on a
 * household whose pool towers over its goals — and the labels between 0 and
 * the top were thinned away. Here each side extends only as far as the data
 * needs, plus a little headroom, and is labelled at round steps inside it —
 * a sliver below zero gets room to show, not a gridline of its own.
 *
 * @param rows - Chart rows, one per x value.
 * @param keys - The series currently drawn; hidden ones do not count.
 * @param targetTicks - Roughly how many labelled steps the taller side gets.
 */
export function stackAxis(
  rows: StackRow[],
  keys: string[],
  targetTicks = 3,
): StackAxis {
  let top = 0;
  let bottom = 0;
  for (const row of rows) {
    let up = 0;
    let down = 0;
    for (const key of keys) {
      const value = row[key];
      if (typeof value !== "number") continue;
      if (value > 0) up += value;
      else down += value;
    }
    top = Math.max(top, up);
    bottom = Math.min(bottom, down);
  }
  const span = Math.max(top, -bottom);
  if (span === 0) return { domain: [0, 1], ticks: [0] };
  const step = niceStep(span / targetTicks);
  const upper = top * 1.05;
  const lower = bottom * 1.15;
  const ticks: number[] = [];
  for (let tick = Math.ceil(lower / step) * step; tick <= upper; tick += step) {
    // Adding zero turns the -0 a tick just under the line rounds to into 0.
    ticks.push(Math.round(tick) + 0);
  }
  return { domain: [lower, upper || step], ticks };
}
