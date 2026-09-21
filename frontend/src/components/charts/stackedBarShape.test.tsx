import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { BarChart, Bar, Rectangle, XAxis, YAxis } from "recharts";
import {
  stackEnds,
  stackSegmentRadius,
  roundedStackShape,
  STACK_CORNER_RADIUS as R,
} from "./stackedBarShape";

/**
 * A stacked column is several segments drawn end to end, so only the segment
 * at each outer end is rounded — rounding every one renders the column as a
 * string of beads.
 *
 * The negative end is the interesting case (a clawback bar hanging under the
 * axis), and a rendered chart cannot be measured in jsdom, so the geometry is
 * asserted here instead.
 */
describe("stacked bar shape", () => {
  const keys = ["g1", "g2", "g3"];

  describe("stackEnds", () => {
    it("names the last funded series as the top of the column", () => {
      const ends = stackEnds([{ month: "2026-03", g1: 2500, g2: 2000 }], keys, "month");
      expect(ends.get("2026-03")).toEqual({ top: "g2" });
    });

    it("skips series the row left at zero or never carried", () => {
      // A segment of zero height draws nothing, so it can never be the end
      // the rounding belongs to.
      const ends = stackEnds([{ month: "2026-03", g1: 2500, g2: 0 }], keys, "month");
      expect(ends.get("2026-03")).toEqual({ top: "g1" });
    });

    it("marks both ends when a column runs above and below the axis", () => {
      const ends = stackEnds([{ month: "2026-04", g1: 1200, g3: -800 }], keys, "month");
      expect(ends.get("2026-04")).toEqual({ top: "g1", bottom: "g3" });
    });

    it("keys rows by whatever the chart's x axis is", () => {
      const ends = stackEnds([{ age: 67, pension: 9000 }], ["pension"], "age");
      expect(ends.get("67")).toEqual({ top: "pension" });
    });

    it("gives a column with no movement no ends at all", () => {
      expect(stackEnds([{ month: "2026-05" }], keys, "month").get("2026-05")).toEqual({});
    });
  });

  describe("stackSegmentRadius", () => {
    const rows = [{ month: "2026-04", g1: 1200, g2: 500, g3: -800 }];
    const ends = stackEnds(rows, keys, "month");

    it("rounds the top of the positive run", () => {
      expect(stackSegmentRadius(ends, rows[0], "g2", "month")).toEqual([R, R, 0, 0]);
    });

    it("rounds the foot of the negative run with the same radii", () => {
      // Recharts flips them by the bar's sign — see the round-trip below.
      expect(stackSegmentRadius(ends, rows[0], "g3", "month")).toEqual([R, R, 0, 0]);
    });

    it("leaves an inner segment square at both ends", () => {
      expect(stackSegmentRadius(ends, rows[0], "g1", "month")).toEqual([0, 0, 0, 0]);
    });

    it("is square when Recharts hands the shape no row", () => {
      expect(stackSegmentRadius(ends, undefined, "g1", "month")).toEqual([0, 0, 0, 0]);
    });
  });

  /**
   * The whole path, end to end: Recharts has to hand the shape the row it is
   * drawing and a height signed away from the axis, or the radii above are
   * decided on the wrong information.
   */
  describe("rendered into a chart", () => {
    /** Every bar path a two-series stacked chart draws for these rows. */
    function pathsFor(rows: { month: string; a: number; b: number }[]) {
      const ends = stackEnds(rows, ["a", "b"], "month");
      const { container } = render(
        <BarChart width={300} height={200} data={rows}>
          <XAxis dataKey="month" />
          <YAxis />
          <Bar
            dataKey="a"
            stackId="s"
            fill="#f00"
            shape={roundedStackShape(ends, "a", "month")}
            isAnimationActive={false}
          />
          <Bar
            dataKey="b"
            stackId="s"
            fill="#0f0"
            shape={roundedStackShape(ends, "b", "month")}
            isAnimationActive={false}
          />
        </BarChart>,
      );
      return [...container.querySelectorAll("path")]
        .map((p) => p.getAttribute("d") ?? "")
        .filter((d) => d.startsWith("M"));
    }

    /**
     * Where a segment's rounding sits, as SVG y coordinates: the corner the
     * path opens on, and the flat edge it closes on. Larger y is further down
     * the chart, so comparing the two says which end got rounded without
     * pinning any pixel.
     */
    function roundedEnd(d: string): { corner: number; flat: number } {
      return {
        corner: Number(d.match(/^M[\d.]+,([\d.]+)A/)?.[1]),
        flat: Number(d.match(/L\s?[\d.]+,([\d.]+)Z$/)?.[1]),
      };
    }

    it("rounds the top of a column and leaves the segment under it square", () => {
      const [inner, top] = pathsFor([{ month: "2026-01", a: 1000, b: 500 }]);
      expect(inner).not.toContain("A ");

      const { corner, flat } = roundedEnd(top);
      // The rounded corner is above where the segment meets the one below it.
      expect(corner).toBeLessThan(flat);
    });

    it("rounds a clawback column at its foot, below the axis", () => {
      // One month funds nothing and gives 800 back. Its rounding must sit at
      // the bottom tip, not where the bar leaves the axis — which is the end
      // `[0, 0, r, r]` would have rounded.
      const paths = pathsFor([
        { month: "2026-01", a: 1000, b: 500 },
        { month: "2026-02", a: 0, b: -800 },
      ]);

      const { corner, flat } = roundedEnd(paths.at(-1)!);
      expect(corner).toBeGreaterThan(flat);
    });
  });

  /**
   * Pins the Recharts behaviour the radii above rely on: `radius[0]`/`[1]` are
   * applied at the rectangle's `y`, which a bar puts at its *value* end for
   * either sign. Were this to change, `[r, r, 0, 0]` would start rounding a
   * clawback bar where it meets the axis instead of at its tip.
   */
  describe("the Recharts rectangle semantics this relies on", () => {
    /** The `d` of a rectangle path, as rendered by the installed Recharts. */
    function pathOf(y: number, height: number, radius: [number, number, number, number]) {
      const { container } = render(
        <svg>
          <Rectangle x={10} y={y} width={30} height={height} radius={radius} fill="#fff" />
        </svg>,
      );
      return container.querySelector("path")?.getAttribute("d") ?? "";
    }

    it("rounds a positive bar at its top, which is its `y`", () => {
      // Spans y 20..60 with y at the top; the arc must sit near y=20.
      expect(pathOf(20, 40, [4, 4, 0, 0])).toContain("M10,24A");
    });

    it("rounds a negative bar at its bottom tip, which is also its `y`", () => {
      // Same span, but drawn from the tip at y=60 upward (negative height).
      expect(pathOf(60, -40, [4, 4, 0, 0])).toContain("M10,56A");
    });

    it("would round a negative bar at the axis if the radii were flipped", () => {
      // The bug this module exists to avoid: the arc lands at the y=20 end,
      // where the bar meets the axis, and the tip renders square.
      const d = pathOf(60, -40, [0, 0, 4, 4]);
      expect(d).toContain("M10,60L");
      expect(d).toContain("24A");
    });
  });
});
