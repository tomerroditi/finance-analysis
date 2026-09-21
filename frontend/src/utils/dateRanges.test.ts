import { describe, it, expect } from "vitest";
import { resolveRangePreset } from "./dateRanges";

describe("resolveRangePreset", () => {
  const now = new Date(2026, 8, 21); // 2026-09-21, local time

  it("leaves both bounds off for all-time", () => {
    expect(resolveRangePreset("all", now)).toEqual({});
  });

  it("ends every bounded window on today", () => {
    for (const preset of ["year", "last12m"] as const) {
      expect(resolveRangePreset(preset, now).end).toBe("2026-09-21");
    }
  });

  it("walks back twelve whole months for the trailing window", () => {
    expect(resolveRangePreset("last12m", now).start).toBe("2025-09-21");
  });

  it("starts the year window on January 1st", () => {
    expect(resolveRangePreset("year", now).start).toBe("2026-01-01");
  });

  it("clamps a month-end start into the shorter month", () => {
    // Naive `setMonth(getMonth() - 12)` on 29 February yields 1 March, which
    // would hand the backend a window a day inside the one the user asked for.
    const leapDay = new Date(2028, 1, 29);
    expect(resolveRangePreset("last12m", leapDay).start).toBe("2027-02-28");
  });

  it("formats from the local calendar, not the UTC instant", () => {
    // Just after local midnight: `toISOString()` would report the previous
    // day in any positive-offset zone (the app's home zone is UTC+2/+3).
    const justAfterMidnight = new Date(2026, 8, 21, 0, 30);
    expect(resolveRangePreset("last12m", justAfterMidnight).end).toBe("2026-09-21");
  });
});
