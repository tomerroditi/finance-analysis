import { describe, it, expect } from "vitest";
import { resolveRangePreset } from "./dateRanges";

describe("resolveRangePreset", () => {
  const now = new Date(2026, 8, 21); // 2026-09-21, local time

  it("leaves both bounds off for all-time", () => {
    expect(resolveRangePreset("all", now)).toEqual({});
  });

  it("ends every bounded window on today", () => {
    for (const preset of ["last1m", "last3m", "year", "last12m"] as const) {
      expect(resolveRangePreset(preset, now).end).toBe("2026-09-21");
    }
  });

  it("walks back whole months for the trailing windows", () => {
    expect(resolveRangePreset("last1m", now).start).toBe("2026-08-21");
    expect(resolveRangePreset("last3m", now).start).toBe("2026-06-21");
    expect(resolveRangePreset("last12m", now).start).toBe("2025-09-21");
  });

  it("starts the year window on January 1st", () => {
    expect(resolveRangePreset("year", now).start).toBe("2026-01-01");
  });

  it("clamps a month-end start into the shorter month", () => {
    // Naive `setMonth(getMonth() - 1)` on 31 March yields 3 March, which would
    // hand the backend a window overlapping the month the user asked to leave.
    const march31 = new Date(2026, 2, 31);
    expect(resolveRangePreset("last1m", march31).start).toBe("2026-02-28");
  });

  it("formats from the local calendar, not the UTC instant", () => {
    // Just after local midnight: `toISOString()` would report the previous
    // day in any positive-offset zone (the app's home zone is UTC+2/+3).
    const justAfterMidnight = new Date(2026, 8, 21, 0, 30);
    expect(resolveRangePreset("last1m", justAfterMidnight).end).toBe("2026-09-21");
  });
});
