import { useQuery } from "@tanstack/react-query";
import { scrapingApi } from "../services/api";
import { useDemoMode } from "../context/DemoModeContext";
import { daysSince } from "../utils/dateFormatting";

/**
 * Freshness tiers, ordered worst-to-best in severity. Drives the budget
 * data-freshness badge, the stale-KPI treatment, and the sync banner.
 *
 * - `none`      — no scrapable accounts exist (cash/manual-only user); hide UI
 * - `fresh`     — newest weakest-link sync ≤ 1 day old
 * - `aging`     — 2–3 days old
 * - `stale`     — 4–6 days old
 * - `veryStale` — ≥ 7 days old
 * - `never`     — at least one account has never been synced
 */
export type FreshnessTier =
  | "none"
  | "fresh"
  | "aging"
  | "stale"
  | "veryStale"
  | "never";

export interface StaleAccount {
  service: string;
  provider: string;
  accountName: string;
  /** ISO date of last successful scrape, or null if never synced. */
  lastScrapeDate: string | null;
}

export interface BudgetFreshness {
  tier: FreshnessTier;
  /** ISO date of the oldest (weakest-link) sync; null when an account never synced. */
  oldestSyncDate: string | null;
  /** Accounts that are stale (≥ 4 days) or never synced — for the popover + banner. */
  staleAccounts: StaleAccount[];
  /** True when at least one scrapable account exists (badge should render). */
  hasScrapableAccounts: boolean;
  isLoading: boolean;
}

const STALE_THRESHOLD_DAYS = 4;
const VERY_STALE_THRESHOLD_DAYS = 7;
const AGING_THRESHOLD_DAYS = 2;

/**
 * Computes how current the budget's underlying transaction data is, based on
 * the *oldest* successful scrape across all scrapable accounts (the weakest
 * link). A single account that hasn't synced in a week makes the whole budget
 * provisional, so we surface that rather than the most-recent sync.
 *
 * Demo mode short-circuits to `none` — scrape recency is meaningless there.
 */
export function useBudgetFreshness(): BudgetFreshness {
  const { isDemoMode } = useDemoMode();

  const { data, isLoading } = useQuery({
    queryKey: ["last-scrapes", isDemoMode],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
    enabled: !isDemoMode,
  });

  // Insurance is scraped but never produces budget transactions, so a stale
  // insurance sync says nothing about the budget's completeness — exclude it.
  const budgetRelevant = (data ?? []).filter((s) => s.service !== "insurances");

  if (isDemoMode || budgetRelevant.length === 0) {
    return {
      tier: "none",
      oldestSyncDate: null,
      staleAccounts: [],
      hasScrapableAccounts: false,
      isLoading: isDemoMode ? false : isLoading,
    };
  }

  const accounts: StaleAccount[] = budgetRelevant.map((s) => ({
    service: s.service,
    provider: s.provider,
    accountName: s.account_name,
    lastScrapeDate: s.last_scrape_date,
  }));

  const neverSynced = accounts.filter((a) => a.lastScrapeDate === null);
  const synced = accounts.filter(
    (a): a is StaleAccount & { lastScrapeDate: string } =>
      a.lastScrapeDate !== null,
  );

  // Weakest link: the largest day-gap drives the tier. Never-synced accounts
  // are infinitely stale and dominate.
  let tier: FreshnessTier;
  let oldestSyncDate: string | null;

  if (neverSynced.length > 0) {
    tier = "never";
    oldestSyncDate = null;
  } else {
    // synced is guaranteed non-empty here (accounts.length > 0, none null).
    const oldest = synced.reduce((acc, a) =>
      daysSince(a.lastScrapeDate) > daysSince(acc.lastScrapeDate) ? a : acc,
    );
    oldestSyncDate = oldest.lastScrapeDate;
    const worstDays = daysSince(oldest.lastScrapeDate);
    if (worstDays >= VERY_STALE_THRESHOLD_DAYS) tier = "veryStale";
    else if (worstDays >= STALE_THRESHOLD_DAYS) tier = "stale";
    else if (worstDays >= AGING_THRESHOLD_DAYS) tier = "aging";
    else tier = "fresh";
  }

  const staleAccounts = accounts.filter(
    (a) =>
      a.lastScrapeDate === null ||
      daysSince(a.lastScrapeDate) >= STALE_THRESHOLD_DAYS,
  );

  return {
    tier,
    oldestSyncDate,
    staleAccounts,
    hasScrapableAccounts: true,
    isLoading,
  };
}
