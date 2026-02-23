import { describe, it, expect } from "vitest";
import { formatDate, formatShortDate, DATE_FORMAT } from "./dateFormatting";

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

describe("DATE_FORMAT", () => {
  it("is dd/MM/yyyy", () => {
    expect(DATE_FORMAT).toBe("dd/MM/yyyy");
  });
});
