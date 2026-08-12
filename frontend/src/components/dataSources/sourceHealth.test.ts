import { describe, it, expect } from "vitest";
import {
  STALE_SOURCE_DAYS,
  countNeedingAttention,
  needsAttention,
  sourceHealth,
} from "./sourceHealth";

/** ISO timestamp `days` days before now. */
function daysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

describe("sourceHealth", () => {
  it("classifies a source that has never synced", () => {
    expect(sourceHealth(null)).toBe("never");
  });

  it("classifies a scrape from today as today", () => {
    expect(sourceHealth(new Date().toISOString())).toBe("today");
  });

  it("classifies a recent-but-not-today scrape as recent", () => {
    expect(sourceHealth(daysAgo(2))).toBe("recent");
  });

  it("classifies a scrape at the threshold as stale", () => {
    // Boundary: the badge and the page both flip exactly here, so an
    // off-by-one would make them disagree with the documented rule.
    expect(sourceHealth(daysAgo(STALE_SOURCE_DAYS))).toBe("stale");
    expect(sourceHealth(daysAgo(STALE_SOURCE_DAYS - 1))).toBe("recent");
  });
});

describe("needsAttention", () => {
  it("flags never-synced and stale sources only", () => {
    expect(needsAttention(null)).toBe(true);
    expect(needsAttention(daysAgo(STALE_SOURCE_DAYS + 1))).toBe(true);
    expect(needsAttention(daysAgo(1))).toBe(false);
    expect(needsAttention(new Date().toISOString())).toBe(false);
  });

  it("counts across a last-scrapes payload", () => {
    // Same shape the Sidebar badge and the page summary both count over —
    // one helper so a badge reading 2 can't land on a page reading 3.
    expect(
      countNeedingAttention([
        { last_scrape_date: null },
        { last_scrape_date: daysAgo(30) },
        { last_scrape_date: daysAgo(1) },
        { last_scrape_date: new Date().toISOString() },
      ]),
    ).toBe(2);
  });
});
