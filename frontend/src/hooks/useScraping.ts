import { useState, useEffect, useCallback, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";

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
  error_message?: string;
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
  const cooldownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );

  useEffect(() => {
    const anyActive = Object.values(resendCooldownEnd).some(
      (end) => end > Date.now(),
    );
    if (!anyActive) {
      if (cooldownIntervalRef.current) {
        clearInterval(cooldownIntervalRef.current);
        cooldownIntervalRef.current = null;
      }
      return;
    }
    if (cooldownIntervalRef.current) return;
    cooldownIntervalRef.current = setInterval(() => {
      setCooldownTick((tick) => tick + 1);
    }, 1000);
    return () => {
      if (cooldownIntervalRef.current) {
        clearInterval(cooldownIntervalRef.current);
        cooldownIntervalRef.current = null;
      }
    };
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

  // Start all accounts
  const scrapeAll = useCallback(
    (accounts: Account[], scrapingPeriodDays: number | null) => {
      accounts.forEach((acc) => startScraper(acc, scrapingPeriodDays));
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
    async (scraper: ScraperState, _scrapingPeriodDays: number | null) => {
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

        const cooldownProcessId =
          status === "restarted" ? newProcessId : oldProcessId;
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

          if (
            newStatus !== scraper.status ||
            Date.now() - scraper.last_updated > 5000
          ) {
            if (newStatus === "success" && scraper.status !== "success") {
              queryClient.invalidateQueries({ queryKey: ["last-scrapes"] });
              queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
            }
            setRunningScrapers((prev) => ({
              ...prev,
              [scraper.process_id]: {
                ...scraper,
                status: newStatus,
                error_message: errorMessage,
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
