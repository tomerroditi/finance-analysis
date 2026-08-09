import { useEffect, useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";
import { qkPrefix } from "../services/queryKeys";
import {
  accountKey,
  isScraperActive,
  useScrapingStore,
} from "../stores/scrapingStore";
import type { Account, ResendError, ScraperState } from "../stores/scrapingStore";

// Re-exported so consumers keep importing scraping types from the hook they
// already use; the state itself lives in `stores/scrapingStore.ts`.
export type { Account, ResendError, ScraperState };
export { accountKey, isScraperActive };

/** Cooldown window enforced client-side after a resend attempt, win or lose. */
export const RESEND_COOLDOWN_SECONDS = 60;

/**
 * Cooldown seeded the first time a process is seen waiting for 2FA.
 *
 * Reaching `waiting_for_2fa` means the provider just sent an OTP — the scrape
 * the user started *is* the first send. Without this, Resend is live the
 * instant the code input appears, so "Scrape → Resend" fires a second OTP
 * seconds after the first, before the SMS has even arrived. Shorter than
 * ``RESEND_COOLDOWN_SECONDS`` because the user hasn't spent a click yet and a
 * genuinely undelivered first code shouldn't be a full minute of waiting.
 */
export const INITIAL_2FA_COOLDOWN_SECONDS = 30;

/** How often the poller asks the backend for each live scraper's status. */
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
const SCRAPE_COMPLETION_PREFIXES = [
  qkPrefix.transactions,
  qkPrefix.analytics,
  qkPrefix.budget,
  qkPrefix.pendingRefunds,
  qkPrefix.insuranceAccounts,
  qkPrefix.bankBalances,
  qkPrefix.lastScrapes,
] as const;

/**
 * Drives every live scraper's status polling, app-wide.
 *
 * Mounted EXACTLY ONCE (see `ScrapingTracker`, rendered by `Layout`) rather
 * than from `useScraping`: the state is global now, so a poller per consumer
 * would multiply both the request rate and the completion-invalidation
 * cascade. Living above the router also means a scrape keeps being tracked —
 * and a 2FA prompt keeps being answerable — while the user is on some other
 * page.
 */
export function useScrapingPoller() {
  const queryClient = useQueryClient();

  // Adopt whatever is already running on the backend. Process ids only exist
  // in memory on the client, so a reload (or a second tab) starts blind: an
  // account mid-scrape looks idle, and a scraper parked on a 2FA prompt can't
  // be answered at all because submitting a code needs its process id.
  useEffect(() => {
    let cancelled = false;
    scrapingApi
      .getActive()
      .then((res) => {
        if (cancelled) return;
        const { runningScrapers, upsertScraper } = useScrapingStore.getState();
        for (const active of res.data) {
          // Never clobber local state: an entry we already track may hold a
          // fresher status (an optimistic 2FA submit) than the DB row.
          if (runningScrapers[active.process_id]) continue;
          upsertScraper({
            process_id: active.process_id,
            account: {
              service: active.service,
              provider: active.provider,
              account_name: active.account_name,
            },
            status: active.status,
            last_updated: Date.now(),
          });
        }
      })
      .catch((e) => {
        console.error("Failed to load active scrapers:", e);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Guards against overlapping ticks: several accounts scraping at once
    // means several requests per tick, and a slow backend could otherwise
    // stack rounds on top of each other.
    let inFlight = false;

    const pollOne = async (scraper: ScraperState) => {
      const res = await scrapingApi.getStatus(scraper.process_id);
      const newStatus = res.data.status;
      const errorMessage = res.data.error_message;
      const errorType = res.data.error_type;
      const store = useScrapingStore.getState();

      if (newStatus === "waiting_for_2fa") {
        // Seed the resend cooldown from the moment the button appears.
        store.seedResendCooldown(
          scraper.process_id,
          Date.now() + INITIAL_2FA_COOLDOWN_SECONDS * 1000,
        );
      }

      if (
        newStatus === scraper.status &&
        Date.now() - scraper.last_updated <= 5000
      ) {
        return;
      }

      if (newStatus === "success" && scraper.status !== "success") {
        for (const queryKey of SCRAPE_COMPLETION_PREFIXES) {
          queryClient.invalidateQueries({ queryKey });
        }
      }
      store.patchScraper(scraper.process_id, {
        status: newStatus,
        error_message: errorMessage,
        error_type: errorType,
        last_updated: Date.now(),
      });
    };

    const checkStatus = async () => {
      if (inFlight) return;
      // Read fresh state every tick instead of closing over a snapshot, so
      // scrapers started (or finished) since the last tick are picked up
      // without tearing down and recreating the interval.
      const active = Object.values(
        useScrapingStore.getState().runningScrapers,
      ).filter(isScraperActive);
      if (active.length === 0) return;

      inFlight = true;
      try {
        // Concurrently, not serially: with several accounts scraping at once a
        // serial sweep would make each account's status lag the one before it.
        await Promise.all(
          active.map((scraper) =>
            pollOne(scraper).catch((e) => {
              console.error(
                "Failed to check status for",
                scraper.process_id,
                e,
              );
            }),
          ),
        );
      } finally {
        inFlight = false;
      }
    };

    const interval = setInterval(checkStatus, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [queryClient]);
}

/**
 * Just "is anything scraping right now?".
 *
 * For consumers that only need the flag (e.g. the budget freshness banner):
 * subscribes to one derived boolean instead of pulling in the whole action
 * surface and the cooldown ticker.
 */
export function useIsAnyScraping(): boolean {
  return useScrapingStore((s) =>
    Object.values(s.runningScrapers).some(isScraperActive),
  );
}

/**
 * Read + act on the global scraping state.
 *
 * Safe to call from any number of components: they all observe the same store
 * and the same single poller (`useScrapingPoller`).
 */
export function useScraping() {
  const runningScrapers = useScrapingStore((s) => s.runningScrapers);
  const resendCooldownEnd = useScrapingStore((s) => s.resendCooldownEnd);
  const resendErrors = useScrapingStore((s) => s.resendErrors);
  const tfaCodes = useScrapingStore((s) => s.tfaCodes);
  const pendingStarts = useScrapingStore((s) => s.pendingStarts);
  const setTfaCode = useScrapingStore((s) => s.setTfaCode);

  // Forces re-render every second while any cooldown is active so
  // `resendCooldownRemaining` recomputes and the countdown ticks down in
  // the UI without callers needing their own interval.
  const [, setCooldownTick] = useState(0);

  useEffect(() => {
    // Deadlines are absolute timestamps, so the closed-over map stays
    // authoritative for this effect's lifetime — no ref needed.
    const anyActive = () =>
      Object.values(resendCooldownEnd).some((end) => end > Date.now());
    if (!anyActive()) return;

    const interval = setInterval(() => {
      // One last tick so the UI renders the cooldown at 0, then stop. The
      // effect's dep (`resendCooldownEnd`) does NOT change when a deadline
      // merely passes, so nothing else would ever clear this timer — it
      // used to keep re-rendering the whole Data Sources page once a second
      // for the rest of the session after a single Resend.
      setCooldownTick((tick) => tick + 1);
      if (!anyActive()) clearInterval(interval);
    }, 1000);
    return () => clearInterval(interval);
  }, [resendCooldownEnd]);

  /** Seconds remaining in the resend cooldown for a process, or 0 if none. */
  const resendCooldownRemaining = useCallback(
    (processId: number): number => {
      const end = resendCooldownEnd[processId];
      if (!end) return 0;
      return Math.max(0, Math.ceil((end - Date.now()) / 1000));
    },
    [resendCooldownEnd],
  );

  // Start a single scraper. Accounts are independent — starting one does not
  // block another, so the user can fire several sources one after the other
  // and watch them run in parallel.
  const startScraper = useCallback(
    async (
      acc: Account,
      scrapingPeriodDays: number | null,
      opts?: { force2fa?: boolean },
    ) => {
      const key = accountKey(acc);
      const store = useScrapingStore.getState();
      // Only the round trip is guarded: until `start` answers we don't know
      // the process id, so the card has nothing to show and a second click
      // would fire a second request for the same account.
      if (store.pendingStarts[key]) return;
      store.setPendingStart(key, true);
      try {
        const res = await scrapingApi.start({
          service: acc.service,
          provider: acc.provider,
          account: acc.account_name,
          ...(scrapingPeriodDays !== null && {
            scraping_period_days: scrapingPeriodDays,
          }),
          ...(opts?.force2fa && { force_2fa: true }),
        });
        const processId = res.data;
        useScrapingStore.getState().upsertScraper({
          process_id: processId,
          account: acc,
          status: "in_progress",
          last_updated: Date.now(),
        });
      } catch (e) {
        console.error("Failed to start scraper:", e);
      } finally {
        useScrapingStore.getState().setPendingStart(key, false);
      }
    },
    [],
  );

  // Start all accounts, skipping any that already have an active scraper
  // (in_progress or waiting_for_2fa). Without this guard, clicking
  // "Scrape All" while one account is mid-2FA would fire a second
  // concurrent scrape for that same account — exactly the burst the
  // backend single-flight guard + OTP rate-limiter exist to stop, just
  // triggered from the UI instead of a double-click.
  const scrapeAll = useCallback(
    (accounts: Account[], scrapingPeriodDays: number | null) => {
      const activeScrapers = Object.values(runningScrapers).filter(
        isScraperActive,
      );
      accounts.forEach((acc) => {
        const isActive = activeScrapers.some(
          (s) =>
            s.account.service === acc.service &&
            s.account.provider === acc.provider &&
            s.account.account_name === acc.account_name,
        );
        if (isActive) return;
        startScraper(acc, scrapingPeriodDays);
      });
    },
    [startScraper, runningScrapers],
  );

  // 2FA mutation
  const tfaMutation = useMutation({
    mutationFn: ({
      service,
      provider,
      account,
      code,
    }: {
      service: string;
      provider: string;
      account: string;
      code: string;
    }) => scrapingApi.submit2fa(service, provider, account, code),
  });

  // Submit 2FA with optimistic update
  const submitTfa = useCallback(
    (scraper: ScraperState, code: string) => {
      useScrapingStore.getState().patchScraper(scraper.process_id, {
        status: "in_progress",
        last_updated: Date.now(),
      });
      tfaMutation.mutate({
        service: scraper.account.service,
        provider: scraper.account.provider,
        account: scraper.account.account_name,
        code,
      });
    },
    [tfaMutation],
  );

  // Resend 2FA in place: ask the backend to re-issue the OTP without
  // abandoning the waiting scraper. OneZero resends on the SAME process;
  // browser-based providers can't resend mid-flow, so the backend aborts
  // and relaunches, returning a NEW process_id we must swap in.
  const resendTfa = useCallback(async (scraper: ScraperState) => {
    const oldProcessId = scraper.process_id;
    const store = useScrapingStore.getState();
    store.setResendError(oldProcessId, undefined);
    try {
      const res = await scrapingApi.resend2fa(
        scraper.account.service,
        scraper.account.provider,
        scraper.account.account_name,
      );
      const { status, process_id: newProcessId } = res.data;

      if (status === "restarted" && newProcessId !== oldProcessId) {
        // Browser-provider fallback: the old process is gone, track the
        // new one under its own id.
        useScrapingStore.getState().replaceScraper(oldProcessId, {
          process_id: newProcessId,
          account: scraper.account,
          status: "waiting_for_2fa",
          last_updated: Date.now(),
        });
      } else {
        // Resent in place: same process stays alive, just bump the
        // freshness timestamp so the polling effect doesn't treat it as
        // stale.
        useScrapingStore
          .getState()
          .patchScraper(oldProcessId, { last_updated: Date.now() });
      }

      // Same condition as the runningScrapers branch above, so the
      // cooldown always keys off whichever process_id that branch just
      // decided is "the current one" for this account — today the
      // backend always mints a fresh id on "restarted", so
      // newProcessId !== oldProcessId is always true in that branch and
      // this is equivalent to `status === "restarted" ? newProcessId :
      // oldProcessId`, but keeping the two conditions textually
      // identical avoids the two ever silently diverging.
      const cooldownProcessId =
        status === "restarted" && newProcessId !== oldProcessId
          ? newProcessId
          : oldProcessId;
      useScrapingStore
        .getState()
        .setResendCooldown(
          cooldownProcessId,
          Date.now() + RESEND_COOLDOWN_SECONDS * 1000,
        );
    } catch (e) {
      const axiosErr = e as {
        response?: { status?: number; data?: { detail?: string } };
      };
      const httpStatus = axiosErr.response?.status;
      const detail = axiosErr.response?.data?.detail;
      // 400 = rate-limited: the backend's detail is a specific,
      // actionable wait-and-retry hint worth showing verbatim (it's
      // English-only, same as every other `response.data.detail`
      // surfaced elsewhere in this app, e.g. DataSources's own
      // setBalanceMutation.onError). 404 = the waiting scraper is gone
      // (aborted/timed out elsewhere) — "Scraping process not found" is
      // confusing to an end user, so show a translated "expired" message
      // instead. Anything else falls back to a generic translated error.
      const resendError: ResendError =
        httpStatus === 400
          ? { kind: "rate_limited", detail }
          : httpStatus === 404
            ? { kind: "expired" }
            : { kind: "unknown" };
      const failStore = useScrapingStore.getState();
      failStore.setResendError(oldProcessId, resendError);
      // Even a failed attempt (e.g. rate-limited) should still start the
      // cooldown so the user isn't tempted to hammer the button.
      failStore.setResendCooldown(
        oldProcessId,
        Date.now() + RESEND_COOLDOWN_SECONDS * 1000,
      );
      console.error("Failed to resend code:", e);
    }
  }, []);

  // Abort a scraper
  const abortScraper = useCallback(async (scraper: ScraperState) => {
    try {
      await scrapingApi.abort(scraper.process_id);
      useScrapingStore.getState().patchScraper(scraper.process_id, {
        status: "failed",
        error_message: "Aborted by user",
        last_updated: Date.now(),
      });
    } catch (e) {
      console.error("Failed to abort:", e);
    }
  }, []);

  // Get scraper state for a specific account
  const getScraperForAccount = useCallback(
    (acc: Account): ScraperState | undefined => {
      return Object.values(runningScrapers)
        .filter(
          (s) =>
            s.account.service === acc.service &&
            s.account.provider === acc.provider &&
            s.account.account_name === acc.account_name,
        )
        .sort((a, b) => b.process_id - a.process_id)[0];
    },
    [runningScrapers],
  );

  /** True while this account has a `/scraping/start` request in flight. */
  const isStartPending = useCallback(
    (acc: Account): boolean => !!pendingStarts[accountKey(acc)],
    [pendingStarts],
  );

  // Scoped to the account the in-flight submit belongs to. Two accounts can be
  // waiting for a 2FA code at the same time now, and a bare
  // `tfaMutation.isPending` would grey out the other card's Verify/Resend
  // buttons while an unrelated account's code is being verified.
  const pendingTfaAccount = tfaMutation.isPending
    ? tfaMutation.variables
    : undefined;
  const isTfaPending = useCallback(
    (acc: Account): boolean =>
      !!pendingTfaAccount &&
      pendingTfaAccount.service === acc.service &&
      pendingTfaAccount.provider === acc.provider &&
      pendingTfaAccount.account === acc.account_name,
    [pendingTfaAccount],
  );

  const activeScraperCount = useMemo(
    () => Object.values(runningScrapers).filter(isScraperActive).length,
    [runningScrapers],
  );

  return {
    startScraper,
    scrapeAll,
    submitTfa,
    resendTfa,
    abortScraper,
    getScraperForAccount,
    isStartPending,
    isTfaPending,
    /** Number of scrapers currently running or waiting for a 2FA code. */
    activeScraperCount,
    isAnyScraping: activeScraperCount > 0,
    resendCooldownRemaining,
    resendErrors,
    tfaCodes,
    setTfaCode,
  };
}
