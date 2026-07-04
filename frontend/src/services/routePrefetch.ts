import type { QueryClient } from "@tanstack/react-query";

import {
  analyticsApi,
  bankBalancesApi,
  cashBalancesApi,
  insuranceAccountsApi,
  investmentsApi,
  liabilitiesApi,
  pendingRefundsApi,
  retirementApi,
  taggingApi,
  transactionsApi,
} from "./api";
import { useAppStore } from "../stores/appStore";

/**
 * Warms the React Query cache for a route's primary data *before* the user
 * navigates to it, so the destination page paints instantly instead of showing
 * skeletons while it fetches.
 *
 * Pages are already all in the loaded bundle (no per-page code chunk), so the
 * lag on first navigation is the page's initial data fetch — not code. This
 * module prefetches that data when the user shows intent to navigate (hovering,
 * focusing, or pressing a nav link), so the click lands on an already-fetched
 * page instead of a loading skeleton.
 *
 * Each entry MUST mirror the exact `queryKey` + fetch call the page uses, or
 * the prefetched data won't be found in the cache when the page mounts. Keep
 * these in sync with the pages when their query keys change.
 */

export interface PrefetchContext {
  /** Demo mode flag — part of the query key for demo-scoped queries. */
  isDemoMode: boolean;
}

// A prefetch counts as fresh for this long, so repeated hovers and the idle
// warm-up never refire a request whose data is already cached.
const PREFETCH_STALE_TIME = 1000 * 60 * 5;

type RoutePrefetch = (queryClient: QueryClient, ctx: PrefetchContext) => void;

function warm(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
  queryFn: () => Promise<unknown>,
): void {
  // prefetchQuery is a no-op when the query is already fresh or in flight.
  void queryClient.prefetchQuery({
    queryKey,
    queryFn,
    staleTime: PREFETCH_STALE_TIME,
  });
}

const ROUTE_PREFETCH: Record<string, RoutePrefetch> = {
  "/": (qc, { isDemoMode }) => {
    warm(qc, ["net-worth-over-time", isDemoMode], () =>
      analyticsApi.getNetWorthOverTime().then((r) => r.data),
    );
    warm(qc, ["all-transactions", isDemoMode], () =>
      transactionsApi.getAll(undefined, false).then((r) => r.data),
    );
    warm(qc, ["cash-balances", isDemoMode], () =>
      cashBalancesApi.getAll().then((r) => r.data),
    );
    warm(qc, ["bank-balances", isDemoMode], () =>
      bankBalancesApi.getAll().then((r) => r.data),
    );
    warm(qc, ["portfolio-analysis", isDemoMode], () =>
      investmentsApi.getPortfolioAnalysis().then((r) => r.data),
    );
    warm(qc, ["category-icons", isDemoMode], () =>
      taggingApi.getIcons().then((r) => r.data),
    );
  },
  "/transactions": (qc) => {
    const service = useAppStore.getState().selectedService;
    if (service !== "refunds") {
      warm(qc, ["transactions", service, false], () =>
        transactionsApi
          .getAll(service === "all" ? undefined : service, false)
          .then((r) => r.data),
      );
    }
    warm(qc, ["pendingRefunds", "all"], () =>
      pendingRefundsApi.getAll().then((r) => r.data),
    );
    warm(qc, ["categories"], () => taggingApi.getCategories().then((r) => r.data));
  },
  "/categories": (qc) => {
    warm(qc, ["categories"], () => taggingApi.getCategories().then((r) => r.data));
    warm(qc, ["category-icons"], () => taggingApi.getIcons().then((r) => r.data));
  },
  "/investments": (qc) => {
    warm(qc, ["investments"], () =>
      investmentsApi.getAll(true).then((r) => r.data),
    );
    warm(qc, ["portfolio-analysis"], () =>
      investmentsApi.getPortfolioAnalysis().then((r) => r.data),
    );
  },
  "/liabilities": (qc) => {
    warm(qc, ["liabilities"], () =>
      liabilitiesApi.getAll(true).then((r) => r.data),
    );
  },
  "/insurances": (qc) => {
    warm(qc, ["insurance-accounts"], () =>
      insuranceAccountsApi.getAll().then((r) => r.data),
    );
    warm(qc, ["transactions", "insurances"], () =>
      transactionsApi.getAll("insurances").then((r) => r.data),
    );
  },
  "/early-retirement": (qc) => {
    warm(qc, ["retirement", "goal"], () =>
      retirementApi.getGoal().then((r) => r.data),
    );
    warm(qc, ["retirement", "status"], () =>
      retirementApi.getStatus().then((r) => r.data),
    );
    warm(qc, ["retirement", "projections"], () =>
      retirementApi.getProjections().then((r) => r.data),
    );
    warm(qc, ["retirement", "suggestions"], () =>
      retirementApi.getSuggestions().then((r) => r.data),
    );
  },
  "/data-sources": (qc, { isDemoMode }) => {
    // Only the bank balances are safe/worthwhile to warm — credentials,
    // providers and last-scrapes are excluded from the persisted cache and
    // are real-time/scraping-tied, so we leave them to fetch on demand.
    warm(qc, ["bank-balances", isDemoMode], () =>
      bankBalancesApi.getAll().then((r) => r.data),
    );
  },
};

/** Warm the cache for a single route (on nav-link hover / focus / pointerdown). */
export function prefetchRoute(
  queryClient: QueryClient,
  path: string,
  ctx: PrefetchContext,
): void {
  ROUTE_PREFETCH[path]?.(queryClient, ctx);
}
