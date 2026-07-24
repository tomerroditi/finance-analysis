import { afterEach, describe, it, expect, vi } from "vitest";
import {
  formatDate,
  formatShortDate,
  todayISO,
  DATE_FORMAT,
} from "./dateFormatting";

describe("formatDate", () => {
  it("formats a Date object to dd/MM/yyyy", () => {
    const date = new Date(2026, 0, 30); // Jan 30, 2026
    expect(formatDate(date)).toBe("30/01/2026");
  });

  it("formats an ISO date string", () => {
    expect(formatDate("2026-01-30T00:00:00.000Z")).toBe("30/01/2026");
  });

  it("formats a date-only string", () => {
    // Note: date-only strings are parsed as UTC
    expect(formatDate("2026-12-25")).toMatch(/25\/12\/2026/);
  });
});

describe("formatShortDate", () => {
  it("formats a Date object to short format", () => {
    const date = new Date(2026, 0, 30);
    expect(formatShortDate(date)).toBe("30 Jan");
  });

  it("formats an ISO string to short format", () => {
    expect(formatShortDate("2026-07-05T12:00:00.000Z")).toBe("5 Jul");
  });

  it("single-digit day has no leading zero", () => {
    const date = new Date(2026, 2, 3);
    expect(formatShortDate(date)).toBe("3 Mar");
  });
});

describe("todayISO", () => {
  // `process` isn't in the app tsconfig's lib (no @types/node), but the
  // vitest run is a Node process and re-reading TZ is the only way to make
  // this assertion timezone-independent.
  const nodeEnv = (
    globalThis as unknown as { process: { env: Record<string, string | undefined> } }
  ).process.env;
  const originalTz = nodeEnv.TZ;

  afterEach(() => {
    vi.useRealTimers();
    nodeEnv.TZ = originalTz;
  });

  // Israel (UTC+2/+3) is the app's home timezone and the one the bug bit:
  // `toISOString()` serialises the UTC instant, so every moment between
  // local midnight and 02:00/03:00 reported YESTERDAY. New York covers the
  // mirror-image case for negative offsets (late evening reported TOMORROW),
  // so this pair fails against the old implementation whatever CI's TZ is.
  it.each(["Asia/Jerusalem", "America/New_York"])(
    "returns the LOCAL calendar date at both ends of the day (%s)",
    (tz) => {
      nodeEnv.TZ = tz;
      vi.useFakeTimers();

      vi.setSystemTime(new Date(2026, 2, 15, 0, 30));
      expect(todayISO()).toBe("2026-03-15");

      vi.setSystemTime(new Date(2026, 2, 15, 23, 30));
      expect(todayISO()).toBe("2026-03-15");
    },
  );

  it("zero-pads single-digit months and days", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 3, 12, 0));
    expect(todayISO()).toBe("2026-01-03");
  });
});

describe("DATE_FORMAT", () => {
  it("is dd/MM/yyyy", () => {
    expect(DATE_FORMAT).toBe("dd/MM/yyyy");
  });
});
