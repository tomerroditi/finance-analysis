import { useState, useEffect, useCallback } from "react";
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
  tfa_type?: "otp" | "browser"; // 'otp' = enter code in app, 'browser' = complete in bank's browser window
}

export function useScraping() {
  const queryClient = useQueryClient();
  const [runningScrapers, setRunningScrapers] = useState<
    Record<number, ScraperState>
  >({});

  // Start a single scraper
  const startScraper = useCallback(
    async (acc: Account, scrapingPeriodDays: number | null) => {
      try {
        const res = await scrapingApi.start({
          service: acc.service,
          provider: acc.provider,
          account: acc.account_name,
          ...(scrapingPeriodDays !== null && {
            scraping_period_days: scrapingPeriodDays,
          }),
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

  // Resend 2FA (abort + restart)
  const resendTfa = useCallback(
    async (scraper: ScraperState, scrapingPeriodDays: number | null) => {
      setRunningScrapers((prev) => {
        const newState = { ...prev };
        delete newState[scraper.process_id];
        return newState;
      });
      try {
        await scrapingApi.abort(scraper.process_id);
        startScraper(scraper.account, scrapingPeriodDays);
      } catch (e) {
        console.error("Failed to resend code:", e);
      }
    },
    [startScraper],
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
          const tfaType = res.data.tfa_type;

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
                tfa_type: tfaType,
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
  };
}
