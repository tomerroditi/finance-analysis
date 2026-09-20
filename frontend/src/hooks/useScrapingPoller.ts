import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";
import { qkPrefix } from "../services/queryKeys";
import { useScrapingStore, isLive } from "../stores/scrapingStore";
import { INITIAL_2FA_COOLDOWN_SECONDS } from "./useScraping";

/** How often the backend is asked for each live scrape's status. */
export const POLL_INTERVAL_MS = 2000;

/**
 * Query-key prefixes a finished scrape invalidates.
 *
 * A successful scrape writes new transactions (and, for insurance
 * providers, new policy balances) straight into the DB. Completion is
 * detected by POLLING, not by a mutation, so the shared
 * `MutationCache.onSuccess` sweep in `queryClient.ts` never fires for it —
 * whatever isn't listed here stays stale for the full 5-minute
 * `staleTime`, i.e. freshly scraped transactions were invisible on the
 * Transactions / Dashboard / Budget pages for up to five minutes.
 *
 * Deliberately a narrow list rather than a bare `invalidateQueries()`:
 * `.claude/rules/frontend_components.md` → "Don't fan out invalidation in
 * mutation hot paths". Everything here is genuinely downstream of new
 * transaction rows.
 */
export const SCRAPE_COMPLETION_PREFIXES = [
  qkPrefix.transactions,
  qkPrefix.analytics,
  qkPrefix.budget,
  qkPrefix.pendingRefunds,
  qkPrefix.insuranceAccounts,
  qkPrefix.bankBalances,
  qkPrefix.lastScrapes,
] as const;

/**
 * Poll every live scrape once and fold the results into the store.
 *
 * Exported for the tests: the interval is otherwise the only way to reach
 * this, and driving it through fake timers makes the assertions about *what*
 * a tick does harder to read than they need to be.
 */
export async function pollOnce(queryClient: QueryClient): Promise<void> {
  // Read the store at tick time rather than closing over a render-time
  // snapshot. The old effect listed `runningScrapers` as a dependency, so
  // every status change tore the interval down and started a fresh one —
  // which also meant a scrape that started mid-interval waited a full extra
  // period before its first poll.
  const store = useScrapingStore.getState();
  const live = Object.values(store.runningScrapers).filter(isLive);
  if (live.length === 0) return;

  // Concurrently, not serially: with several accounts scraping at once a
  // sequential loop made each tick as slow as the sum of its requests, so
  // the last card in the list updated visibly later than the first.
  await Promise.all(
    live.map(async (scraper) => {
      try {
        const res = await scrapingApi.getStatus(scraper.process_id);
        const newStatus = res.data.status;

        if (newStatus === "waiting_for_2fa") {
          // Seed the resend cooldown from the moment the button appears.
          store.seedInitialCooldown(
            scraper.process_id,
            Date.now() + INITIAL_2FA_COOLDOWN_SECONDS * 1000,
          );
        }

        if (
          newStatus !== scraper.status ||
          Date.now() - scraper.last_updated > 5000
        ) {
          if (newStatus === "success" && scraper.status !== "success") {
            for (const queryKey of SCRAPE_COMPLETION_PREFIXES) {
              queryClient.invalidateQueries({ queryKey });
            }
          }
          store.updateStatus(scraper.process_id, {
            status: newStatus,
            error_message: res.data.error_message,
            error_type: res.data.error_type,
          });
        }
      } catch (e) {
        console.error("Failed to check status for", scraper.process_id, e);
      }
    }),
  );
}

/**
 * Drive scrape polling and cold-load hydration for the whole app.
 *
 * Mount exactly once, above the router — see `ScrapingTracker`. Polling used
 * to live inside `useScraping`, so it stopped the moment the Data Sources
 * page unmounted: a scrape that finished while the user was on another page
 * never fired its completion invalidations, and coming back showed stale
 * numbers until the 5-minute `staleTime` lapsed. Worse, a 2FA prompt could
 * not be answered off-page at all, because the `process_id` it needed had
 * gone with the component.
 *
 * @param isDemoMode - the client's current Demo Mode. A change swaps the
 *   database underneath us without a page reload, and `process_id` is a
 *   per-database autoincrement, so the store is cleared rather than carried
 *   across.
 */
export function useScrapingPoller(isDemoMode: boolean): void {
  const queryClient = useQueryClient();
  const setDemo = useScrapingStore((s) => s.setDemo);

  useEffect(() => {
    setDemo(isDemoMode);
  }, [isDemoMode, setDemo]);

  // Re-adopt whatever is still live on a cold load. The backend's
  // `_active_scrapers` registry is the source of truth for what is running;
  // without this, a reload (or a first paint on another page) shows idle
  // cards for scrapes the server is still working on.
  useEffect(() => {
    let cancelled = false;
    scrapingApi
      .getActive()
      .then((res) => {
        if (cancelled || res.data.length === 0) return;
        useScrapingStore.getState().hydrate(res.data);
      })
      .catch((e) => {
        // Non-fatal: the user simply sees idle cards until they act, which
        // is exactly the pre-hydration behaviour.
        console.error("Failed to load active scrapers:", e);
      });
    return () => {
      cancelled = true;
    };
  }, [isDemoMode]);

  const inFlight = useRef(false);

  useEffect(() => {
    // One interval for the app's whole lifetime, with no dependency on the
    // scraper map: ticks are cheap and return immediately when nothing is
    // live, which is far less machinery than tearing the timer down and
    // rebuilding it on every status change.
    const interval = setInterval(async () => {
      // A slow round trip must not stack ticks — with several accounts
      // scraping, overlapping ticks would re-fire the same completion
      // invalidations and hammer the backend.
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        await pollOnce(queryClient);
      } finally {
        inFlight.current = false;
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [queryClient]);
}
