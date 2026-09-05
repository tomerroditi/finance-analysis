import { useState, useEffect, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";
import { qkPrefix } from "../services/queryKeys";

export interface Account {
  service: string;
  provider: string;
  account_name: string;
}

export interface ScraperState {
  process_id: number;
  account: Account;
  status: string; // 'in_progress', 'waiting_for_2fa', 'success', 'failed'
  last_updated: number;
  /**
   * Technical failure detail — the provider's own message, HTTP body or
   * exception text. Shown as secondary "technical details" copy, never as the
   * primary explanation.
   */
  error_message?: string;
  /**
   * Failure category (`INVALID_PASSWORD`, `TIMEOUT`, `GENERAL_ERROR`, …) that
   * selects the translated user-facing message. Undefined for scrapes recorded
   * before the backend tracked it, where `error_message` is all there is.
   */
  error_type?: string;
}

/**
 * Resend-2FA failure surfaced to the UI. `kind` lets the component decide
 * between showing the server's own actionable message verbatim (rate
 * limit) versus a translated, friendlier message (expired process) —
 * backend error strings are English-only and not meant to be shown
 * unfiltered for every failure mode.
 */
export interface ResendError {
  kind: "rate_limited" | "expired" | "unknown";
  detail?: string;
}

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

export function useScraping() {
  const queryClient = useQueryClient();
  const [runningScrapers, setRunningScrapers] = useState<
    Record<number, ScraperState>
  >({});

  // Resend-2FA cooldown bookkeeping. Keyed by the process_id the user was
  // looking at when they clicked Resend — if `resend2fa` swaps in a new
  // process_id ("restarted" case), the cooldown key follows it so the UI
  // (keyed off the current scraper's process_id) still finds it.
  const [resendCooldownEnd, setResendCooldownEnd] = useState<
    Record<number, number>
  >({});
  const [resendErrors, setResendErrors] = useState<
    Record<number, ResendError>
  >({});
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

  // Re-hydrate from the backend on mount.
  //
  // `runningScrapers` is component-local state, so it dies with whatever
  // component called this hook — leaving Data Sources and coming back used
  // to reset every card to idle even though the scraper was still running,
  // and the polling effect never restarted, so the finished scrape's
  // invalidations never fired either. The backend's `_active_scrapers`
  // registry is the real source of truth; ask it what is still live.
  //
  // Merged rather than assigned: a scrape started microseconds before this
  // request resolves is already in local state and must not be dropped, and
  // locally-known terminal states (a just-failed scrape the user is still
  // reading) must survive too. Existing entries win — their `last_updated`
  // and error fields are fresher than anything this endpoint returns.
  useEffect(() => {
    let cancelled = false;
    scrapingApi
      .getActive()
      .then((res) => {
        if (cancelled || res.data.length === 0) return;
        setRunningScrapers((prev) => {
          const next = { ...prev };
          for (const entry of res.data) {
            if (next[entry.process_id]) continue;
            next[entry.process_id] = {
              process_id: entry.process_id,
              account: {
                service: entry.service,
                provider: entry.provider,
                account_name: entry.account_name,
              },
              status: entry.status,
              last_updated: Date.now(),
            };
          }
          return next;
        });
      })
      .catch((e) => {
        // Non-fatal: the user simply sees idle cards until they act, which
        // is exactly the pre-hydration behaviour.
        console.error("Failed to load active scrapers:", e);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
        const processId = res.data;
        setRunningScrapers((prev) => ({
          ...prev,
          [processId]: {
            process_id: processId,
            account: acc,
            status: "in_progress",
            last_updated: Date.now(),
          },
        }));
      } catch (e) {
        console.error("Failed to start scraper:", e);
      }
    },
    [],
  );

  // Start all accounts, skipping any that already have an active scraper
  // (in_progress or waiting_for_2fa). Without this guard, clicking
  // "Scrape All" while one account is mid-2FA would fire a second
  // concurrent scrape for that same account — exactly the burst the
  // backend single-flight guard + OTP rate-limiter (Tasks 1-2) exist to
  // stop, just triggered from the UI instead of a double-click.
  const scrapeAll = useCallback(
    (accounts: Account[], scrapingPeriodDays: number | null) => {
      const activeScrapers = Object.values(runningScrapers).filter(
        (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
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
      setRunningScrapers((prev) => ({
        ...prev,
        [scraper.process_id]: {
          ...scraper,
          status: "in_progress",
          last_updated: Date.now(),
        },
      }));
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
  const resendTfa = useCallback(
    async (scraper: ScraperState) => {
      const oldProcessId = scraper.process_id;
      setResendErrors((prev) => {
        const next = { ...prev };
        delete next[oldProcessId];
        return next;
      });
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
          setRunningScrapers((prev) => {
            const next = { ...prev };
            delete next[oldProcessId];
            next[newProcessId] = {
              process_id: newProcessId,
              account: scraper.account,
              status: "waiting_for_2fa",
              last_updated: Date.now(),
            };
            return next;
          });
        } else {
          // Resent in place: same process stays alive, just bump the
          // freshness timestamp so the polling effect doesn't treat it as
          // stale.
          setRunningScrapers((prev) => {
            const existing = prev[oldProcessId];
            if (!existing) return prev;
            return {
              ...prev,
              [oldProcessId]: { ...existing, last_updated: Date.now() },
            };
          });
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
        setResendCooldownEnd((prev) => ({
          ...prev,
          [cooldownProcessId]: Date.now() + RESEND_COOLDOWN_SECONDS * 1000,
        }));
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
        setResendErrors((prev) => ({ ...prev, [oldProcessId]: resendError }));
        // Even a failed attempt (e.g. rate-limited) should still start the
        // cooldown so the user isn't tempted to hammer the button.
        setResendCooldownEnd((prev) => ({
          ...prev,
          [oldProcessId]: Date.now() + RESEND_COOLDOWN_SECONDS * 1000,
        }));
        console.error("Failed to resend code:", e);
      }
    },
    [],
  );

  // Abort a scraper
  const abortScraper = useCallback(async (scraper: ScraperState) => {
    try {
      await scrapingApi.abort(scraper.process_id);
      setRunningScrapers((prev) => ({
        ...prev,
        [scraper.process_id]: {
          ...scraper,
          status: "failed",
          error_message: "Aborted by user",
          last_updated: Date.now(),
        },
      }));
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

  // Check if any scraper is actively running
  const isAnyScraping = Object.values(runningScrapers).some(
    (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
  );

  // Polling effect
  useEffect(() => {
    const activeScrapers = Object.values(runningScrapers).filter(
      (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
    );
    if (activeScrapers.length === 0) return;

    const checkStatus = async () => {
      for (const scraper of activeScrapers) {
        try {
          const res = await scrapingApi.getStatus(scraper.process_id);
          const newStatus = res.data.status;
          const errorMessage = res.data.error_message;
          const errorType = res.data.error_type;

          if (newStatus === "waiting_for_2fa") {
            // Seed the resend cooldown from the moment the button appears.
            // `!== undefined` rather than a falsy check: an already-elapsed
            // deadline must not be re-seeded, and it also keeps a real resend's
            // longer cooldown from being clobbered back down to 30s.
            setResendCooldownEnd((prev) =>
              prev[scraper.process_id] !== undefined
                ? prev
                : {
                    ...prev,
                    [scraper.process_id]:
                      Date.now() + INITIAL_2FA_COOLDOWN_SECONDS * 1000,
                  },
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
            setRunningScrapers((prev) => ({
              ...prev,
              [scraper.process_id]: {
                ...scraper,
                status: newStatus,
                error_message: errorMessage,
                error_type: errorType,
                last_updated: Date.now(),
              },
            }));
          }
        } catch (e) {
          console.error("Failed to check status for", scraper.process_id, e);
        }
      }
    };

    const interval = setInterval(checkStatus, 2000);
    return () => clearInterval(interval);
  }, [runningScrapers, queryClient]);

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
