import { daysSince } from "../../utils/dateFormatting";

/**
 * A source is "needs attention" once its last successful scrape is this many
 * days old. Matches the Sidebar's Data Sources badge, so the badge count and
 * the page's own "needs attention" figure can never disagree — the user clicks
 * a badge showing 2 and lands on a page that says 2.
 */
export const STALE_SOURCE_DAYS = 7;

export type SourceHealth = "never" | "stale" | "today" | "recent";

/** Shape both `GET /scraping/last-scrapes` records and cards can satisfy. */
export interface LastScrapeLike {
  last_scrape_date: string | null;
}

/**
 * Classify one source by the age of its last **successful** scrape.
 *
 * - `never`  – never synced
 * - `stale`  – synced, but ≥ `STALE_SOURCE_DAYS` ago
 * - `today`  – synced today
 * - `recent` – synced within the window, but not today
 */
export function sourceHealth(lastScrapeDate: string | null): SourceHealth {
  if (!lastScrapeDate) return "never";
  const days = daysSince(lastScrapeDate);
  if (days >= STALE_SOURCE_DAYS) return "stale";
  const scraped = new Date(lastScrapeDate);
  const today = new Date();
  const isToday =
    scraped.getFullYear() === today.getFullYear() &&
    scraped.getMonth() === today.getMonth() &&
    scraped.getDate() === today.getDate();
  return isToday ? "today" : "recent";
}

/** True when a source has never synced or hasn't synced in over a week. */
export function needsAttention(lastScrapeDate: string | null): boolean {
  const health = sourceHealth(lastScrapeDate);
  return health === "never" || health === "stale";
}

/** Count of sources that have never synced or are over a week stale. */
export function countNeedingAttention(sources: LastScrapeLike[]): number {
  return sources.filter((s) => needsAttention(s.last_scrape_date)).length;
}
