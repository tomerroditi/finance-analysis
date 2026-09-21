import { describe, it, expect } from "vitest";
import {
  stackEnds,
  segmentRadius,
  STACK_CORNER_RADIUS as R,
} from "./goalHistoryStacks";

/**
 * A month's column is one stack, and only the segment at each outer end is
 * rounded — rounding every segment renders the column as a string of beads.
 *
 * The negative end is the clawback case (a deficit month taking money back out
 * of a goal), which is exactly the case a chart in jsdom cannot be asserted on.
 */
describe("goal history stack geometry", () => {
  const keys = ["g1", "g2", "g3"];

  describe("stackEnds", () => {
    it("names the last funded goal as the top of the column", () => {
      const ends = stackEnds([{ month: "2026-03", g1: 2500, g2: 2000 }], keys);
      expect(ends.get("2026-03")).toEqual({ top: "g2" });
    });

    it("skips goals the month left at zero or never touched", () => {
      // A segment of zero height draws nothing, so it can never be the end
      // the rounding belongs to.
      const ends = stackEnds([{ month: "2026-03", g1: 2500, g2: 0 }], keys);
      expect(ends.get("2026-03")).toEqual({ top: "g1" });
    });

    it("marks both ends when a month funded one goal and clawed back another", () => {
      const ends = stackEnds(
        [{ month: "2026-04", g1: 1200, g3: -800 }],
        keys,
      );
      expect(ends.get("2026-04")).toEqual({ top: "g1", bottom: "g3" });
    });

    it("gives a month with no movement no ends at all", () => {
      const ends = stackEnds([{ month: "2026-05" }], keys);
      expect(ends.get("2026-05")).toEqual({});
    });
  });

  describe("segmentRadius", () => {
    const rows = [
      { month: "2026-04", g1: 1200, g2: 500, g3: -800 },
    ];
    const ends = stackEnds(rows, keys);

    it("rounds the top of the positive run upward", () => {
      expect(segmentRadius(ends, rows[0], "g2")).toEqual([R, R, 0, 0]);
    });

    it("rounds the foot of the negative run downward", () => {
      expect(segmentRadius(ends, rows[0], "g3")).toEqual([0, 0, R, R]);
    });

    it("leaves an inner segment square on both ends", () => {
      expect(segmentRadius(ends, rows[0], "g1")).toEqual([0, 0, 0, 0]);
    });

    it("is square when the row is missing", () => {
      // Recharts hands a shape no payload while the chart is initialising.
      expect(segmentRadius(ends, undefined, "g1")).toEqual([0, 0, 0, 0]);
    });
  });
});
