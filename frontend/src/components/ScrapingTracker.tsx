import { useScrapingPoller } from "../hooks/useScrapingPoller";
import { useDemoMode } from "../context/DemoModeContext";

/**
 * Keeps scrapes advancing wherever the user is in the app.
 *
 * Renders nothing — it exists to own the app-wide scrape poller at a mount
 * point above the router, so a scrape survives in-app navigation: its status
 * keeps updating, its completion still invalidates the caches that show its
 * new transactions, and a 2FA prompt stays answerable because the
 * `process_id` it needs is no longer tied to the Data Sources page's
 * lifetime.
 */
export function ScrapingTracker() {
  const { isDemoMode } = useDemoMode();
  useScrapingPoller(isDemoMode);
  return null;
}
