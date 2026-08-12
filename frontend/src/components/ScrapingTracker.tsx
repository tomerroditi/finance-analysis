import { useScrapingPoller } from "../hooks/useScraping";

/**
 * Renderless host for the app-wide scraper poller.
 *
 * Mounted once by `Layout`, above the router, so scraping state survives
 * navigation: a scrape started on Data Sources keeps advancing (and a 2FA
 * prompt keeps being answerable) while the user reads their dashboard, and
 * coming back to the page shows the live state rather than idle cards.
 *
 * Must stay a single mount point — see `useScrapingPoller`.
 */
export function ScrapingTracker() {
  useScrapingPoller();
  return null;
}
