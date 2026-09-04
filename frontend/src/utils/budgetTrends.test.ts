import { describe, it, expect } from "vitest";
import {
  bucketByMonth,
  cumulative,
  lastActivePeriod,
  monthKeysEndingAt,
  monthKeysOfYear,
} from "./budgetTrends";

describe("budgetTrends", () => {
  describe("monthKeysEndingAt", () => {
    it("returns the trailing months oldest-first, inclusive of the anchor", () => {
      expect(monthKeysEndingAt(2026, 7, 3)).toEqual(["2026-05", "2026-06", "2026-07"]);
    });

    it("walks back across a year boundary", () => {
      expect(monthKeysEndingAt(2026, 2, 3)).toEqual(["2025-12", "2026-01", "2026-02"]);
    });
  });

  describe("monthKeysOfYear", () => {
    it("returns twelve zero-padded keys", () => {
      const keys = monthKeysOfYear(2026);
      expect(keys).toHaveLength(12);
      expect(keys[0]).toBe("2026-01");
      expect(keys[11]).toBe("2026-12");
    });
  });

  describe("bucketByMonth", () => {
    const months = ["2026-01", "2026-02", "2026-03"];

    it("sums expenses into their month as positive spend", () => {
      const series = bucketByMonth(
        [
          { date: "2026-01-14", amount: -100 },
          { date: "2026-01-28", amount: -50 },
          { date: "2026-03-02", amount: -70 },
        ],
        months,
        220,
      );
      expect(series).toEqual([150, 0, 70]);
    });

    it("ignores transactions outside the requested window", () => {
      const series = bucketByMonth(
        [
          { date: "2025-12-31", amount: -999 },
          { date: "2026-02-01", amount: -40 },
        ],
        months,
        40,
      );
      expect(series).toEqual([0, 40, 0]);
    });

    it("flips the series when the caller's total uses the opposite sign", () => {
      // Every budget view reports `current_amount` spend-positive, so this
      // guard is defensive: a caller that ever passes the opposite sign gets a
      // series matching its own total instead of a chart mirrored below the axis.
      const series = bucketByMonth(
        [{ date: "2026-02-10", amount: 300 }],
        months,
        -300,
      );
      expect(series).toEqual([0, -300, 0]);
    });

    it("tolerates missing dates, amounts and an undefined list", () => {
      expect(bucketByMonth(undefined, months)).toEqual([0, 0, 0]);
      expect(
        bucketByMonth([{ date: null, amount: -10 }, { date: "2026-01-05" }], months),
      ).toEqual([0, 0, 0]);
    });
  });

  describe("cumulative", () => {
    it("returns a running total", () => {
      expect(cumulative([10, 0, 5, 5])).toEqual([10, 10, 15, 20]);
    });
  });

  describe("lastActivePeriod", () => {
    it("finds the last non-zero period so the burn line stops at 'now'", () => {
      expect(lastActivePeriod([5, 3, 0, 0])).toBe(1);
    });

    it("falls back to the final period when nothing happened", () => {
      expect(lastActivePeriod([0, 0, 0])).toBe(2);
    });
  });
});
