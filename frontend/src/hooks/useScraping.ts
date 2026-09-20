import { useState, useEffect, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";
import { useScrapingStore, isLive } from "../stores/scrapingStore";
import type { Account, ResendError, ScraperState } from "../stores/scrapingStore";

export type { Account, ResendError, ScraperState };
export { useIsAnyScraping } from "../stores/scrapingStore";

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

/**
 * Actions and read models over the app-wide scraping store.
 *
 * Holds no state of its own any more — see `stores/scrapingStore.ts` for why.
 * Polling and cold-load hydration live in `useScrapingPoller`, mounted once by
 * `ScrapingTracker`, so they keep running while this hook's callers are
 * unmounted.
 */
export function useScraping() {
  const runningScrapers = useScrapingStore((s) => s.runningScrapers);
  const resendCooldownEnd = useScrapingStore((s) => s.resendCooldownEnd);
  const resendErrors = useScrapingStore((s) => s.resendErrors);
  const trackStarted = useScrapingStore((s) => s.trackStarted);
  const updateStatus = useScrapingStore((s) => s.updateStatus);
  const replaceProcess = useScrapingStore((s) => s.replaceProcess);
  const touch = useScrapingStore((s) => s.touch);
  const setResendCooldown = useScrapingStore((s) => s.setResendCooldown);
  const setResendError = useScrapingStore((s) => s.setResendError);
  const clearResendError = useScrapingStore((s) => s.clearResendError);

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

  // Start a single scraper
  const startScraper = useCallback(
    async (
      acc: Account,
      scrapingPeriodDays: number | null,
      opts?: { force2fa?: boolean },
    ) => {
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
        trackStarted(res.data, acc);
      } catch (e) {
        console.error("Failed to start scraper:", e);
      }
    },
    [trackStarted],
  );

  // Start all accounts, skipping any that already have an active scraper
  // (in_progress or waiting_for_2fa). Without this guard, clicking
  // "Scrape All" while one account is mid-2FA would fire a second
  // concurrent scrape for that same account — exactly the burst the
  // backend single-flight guard + OTP rate-limiter exist to stop, just
  // triggered from the UI instead of a double-click.
  const scrapeAll = useCallback(
    (accounts: Account[], scrapingPeriodDays: number | null) => {
      // Read through the store rather than the render-time snapshot: a
      // Scrape All fired moments after a card's own Play button would
      // otherwise still see that account as idle.
      const activeScrapers = Object.values(
        useScrapingStore.getState().runningScrapers,
      ).filter(isLive);
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
    [startScraper],
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
      updateStatus(scraper.process_id, { status: "in_progress" });
      tfaMutation.mutate({
        service: scraper.account.service,
        provider: scraper.account.provider,
        account: scraper.account.account_name,
        code,
      });
    },
    [tfaMutation, updateStatus],
  );

  // Resend 2FA in place: ask the backend to re-issue the OTP without
  // abandoning the waiting scraper. OneZero resends on the SAME process;
  // browser-based providers can't resend mid-flow, so the backend aborts
  // and relaunches, returning a NEW process_id we must swap in.
  const resendTfa = useCallback(
    async (scraper: ScraperState) => {
      const oldProcessId = scraper.process_id;
      clearResendError(oldProcessId);
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
          replaceProcess(oldProcessId, newProcessId, scraper.account);
        } else {
          // Resent in place: same process stays alive, just bump the
          // freshness timestamp so the polling loop doesn't treat it as
          // stale.
          touch(oldProcessId);
        }

        // Same condition as the branch above, so the cooldown always keys
        // off whichever process_id that branch just decided is "the current
        // one" for this account — today the backend always mints a fresh id
        // on "restarted", so newProcessId !== oldProcessId is always true in
        // that branch and this is equivalent to `status === "restarted" ?
        // newProcessId : oldProcessId`, but keeping the two conditions
        // textually identical avoids the two ever silently diverging.
        const cooldownProcessId =
          status === "restarted" && newProcessId !== oldProcessId
            ? newProcessId
            : oldProcessId;
        setResendCooldown(
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
        setResendError(oldProcessId, resendError);
        // Even a failed attempt (e.g. rate-limited) should still start the
        // cooldown so the user isn't tempted to hammer the button.
        setResendCooldown(
          oldProcessId,
          Date.now() + RESEND_COOLDOWN_SECONDS * 1000,
        );
        console.error("Failed to resend code:", e);
      }
    },
    [clearResendError, replaceProcess, setResendCooldown, setResendError, touch],
  );

  // Abort a scraper
  const abortScraper = useCallback(
    async (scraper: ScraperState) => {
      try {
        await scrapingApi.abort(scraper.process_id);
        // Mirrors the CANCELED row the backend records — a user abort is not
        // a failure and must not read as one.
        updateStatus(scraper.process_id, {
          status: "canceled",
          error_message: undefined,
          error_type: undefined,
        });
      } catch (e) {
        console.error("Failed to abort:", e);
      }
    },
    [updateStatus],
  );

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

  // Check if any scraper is actively running
  const isAnyScraping = Object.values(runningScrapers).some(isLive);

  return {
    startScraper,
    scrapeAll,
    submitTfa,
    resendTfa,
    abortScraper,
    getScraperForAccount,
    isAnyScraping,
    tfaIsPending: tfaMutation.isPending,
    resendCooldownRemaining,
    resendErrors,
  };
}
