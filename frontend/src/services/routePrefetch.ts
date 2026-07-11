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
import { makeQueryKeys } from "./queryKeys";
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
 * the prefetched data won't be found in the cache when the page mounts. Factory
 * -managed keys are built from `makeQueryKeys(isDemoMode)` (the pure function
 * form of the `useQueryKeys()` hook — prefetch runs outside React, so it can't
 * call hooks), which makes drift structurally impossible: any change to
 * `services/queryKeys.ts` propagates here automatically. The `/early-retirement`
 * keys are still literal arrays (out of scope for the key-factory migration).
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
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.analytics.netWorthOverTime(), () =>
      analyticsApi.getNetWorthOverTime().then((r) => r.data),
    );
    warm(qc, k.transactions.list(undefined, false), () =>
      transactionsApi.getAll(undefined, false).then((r) => r.data),
    );
    warm(qc, k.balances.cash(), () => cashBalancesApi.getAll().then((r) => r.data));
    warm(qc, k.balances.bank(), () => bankBalancesApi.getAll().then((r) => r.data));
    warm(qc, k.investments.portfolio(), () =>
      investmentsApi.getPortfolioAnalysis().then((r) => r.data),
    );
    warm(qc, k.tagging.icons(), () => taggingApi.getIcons().then((r) => r.data));
  },
  "/transactions": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    const service = useAppStore.getState().selectedService;
    if (service !== "refunds") {
      warm(
        qc,
        k.transactions.list(service === "all" ? undefined : service, false),
        () =>
          transactionsApi
            .getAll(service === "all" ? undefined : service, false)
            .then((r) => r.data),
      );
    }
    warm(qc, k.pendingRefunds.all(), () =>
      pendingRefundsApi.getAll().then((r) => r.data),
    );
    warm(qc, k.tagging.categories(), () =>
      taggingApi.getCategories().then((r) => r.data),
    );
  },
  "/categories": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.tagging.categories(), () =>
      taggingApi.getCategories().then((r) => r.data),
    );
    warm(qc, k.tagging.icons(), () => taggingApi.getIcons().then((r) => r.data));
  },
  "/investments": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.investments.list(true), () =>
      investmentsApi.getAll(true).then((r) => r.data),
    );
    warm(qc, k.investments.portfolio(), () =>
      investmentsApi.getPortfolioAnalysis().then((r) => r.data),
    );
  },
  "/liabilities": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.liabilities.list(true), () =>
      liabilitiesApi.getAll(true).then((r) => r.data),
    );
  },
  "/insurances": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.insurance.accounts(), () =>
      insuranceAccountsApi.getAll().then((r) => r.data),
    );
    warm(qc, k.transactions.list("insurances", false), () =>
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
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.balances.bank(), () => bankBalancesApi.getAll().then((r) => r.data));
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
