import type { QueryClient } from "@tanstack/react-query";

import {
  analyticsApi,
  bankBalancesApi,
  budgetApi,
  cashBalancesApi,
  fireApi,
  insuranceAccountsApi,
  investmentsApi,
  liabilitiesApi,
  pendingRefundsApi,
  savingsGoalsApi,
  taggingApi,
  transactionsApi,
} from "./api";
import { makeQueryKeys } from "./queryKeys";
import { useAppStore } from "../stores/appStore";
import { needsTransactionList, readDashboardLayout } from "../hooks/useDashboardLayout";
import { loadRouteChunk } from "../routeChunks";

/**
 * Warms a route *before* the user navigates to it — its lazy page chunk and
 * the React Query cache for its primary data — so the destination page paints
 * instantly instead of showing skeletons while it loads.
 *
 * Runs when the user shows intent to navigate (hovering, focusing, or pressing
 * a nav link), and once at boot for the route the app opened on, in parallel
 * with that page's chunk and the IndexedDB restore rather than after them.
 *
 * Each entry MUST mirror the exact `queryKey` + fetch call the page uses, or
 * the prefetched data won't be found in the cache when the page mounts. Factory
 * -managed keys are built from `makeQueryKeys(isDemoMode)` (the pure function
 * form of the `useQueryKeys()` hook — prefetch runs outside React, so it can't
 * call hooks), which makes drift structurally impossible: any change to
 * `services/queryKeys.ts` propagates here automatically.
 *
 * NEVER hand-write a literal key array here. `/early-retirement` used to,
 * and drifted: the literals lacked the trailing demo-mode segment every
 * factory key carries, so the four prefetched responses landed under keys no
 * page ever read — four wasted requests, four orphan IndexedDB entries, and
 * a page that still booted cold.
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
    // The whole history is the dashboard's largest read; only the recent
    // feed and the heatmap use it, so it is warmed only when one is shown.
    if (needsTransactionList(readDashboardLayout())) {
      warm(qc, k.transactions.list(undefined, false), () =>
        transactionsApi.getAll(undefined, false).then((r) => r.data),
      );
    }
    warm(qc, k.balances.cash(), () => cashBalancesApi.getAll().then((r) => r.data));
    warm(qc, k.tagging.icons(), () => taggingApi.getIcons().then((r) => r.data));
  },
  "/transactions": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.pendingRefunds.all(), () =>
      pendingRefundsApi.getAll().then((r) => r.data),
    );
    if (useAppStore.getState().selectedService === "refunds") {
      warm(qc, k.pendingRefunds.sources(), () =>
        pendingRefundsApi.getRefundSources().then((r) => r.data),
      );
      return;
    }
    // Every service filter reads the merged list (see Transactions.tsx).
    warm(qc, k.transactions.list(undefined, false), () =>
      transactionsApi.getAll(undefined, false).then((r) => r.data),
    );
    // What the table and its row actions read.
    warm(qc, k.tagging.categories(), () =>
      taggingApi.getCategories().then((r) => r.data),
    );
    warm(qc, k.tagging.icons(), () => taggingApi.getIcons().then((r) => r.data));
    warm(qc, k.tagging.rules(), () => taggingApi.getRules().then((r) => r.data));
    warm(qc, k.balances.cash(), () => cashBalancesApi.getAll().then((r) => r.data));
    // The goal links drive each row's goal icon; the goals themselves load
    // only when a row's goal picker opens.
    warm(qc, k.savingsGoals.links(), () => savingsGoalsApi.getLinks().then((r) => r.data));
  },
  "/budget": (qc, { isDemoMode }) => {
    // The Overview tab, which the page opens on, for the current month.
    const k = makeQueryKeys(isDemoMode);
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth() + 1;
    warm(qc, k.budget.overview(year, month, false), () =>
      budgetApi.getOverview(year, month).then((r) => r.data),
    );
    warm(qc, k.budget.analysis(year, month, false), () =>
      budgetApi.getAnalysis(year, month, false).then((r) => r.data),
    );
    warm(qc, k.budget.trend(year, month, 12, false), () =>
      budgetApi.getTrend(year, month, 12, false).then((r) => r.data),
    );
  },
  "/categories": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.tagging.categories(), () =>
      taggingApi.getCategories().then((r) => r.data),
    );
    warm(qc, k.tagging.icons(), () => taggingApi.getIcons().then((r) => r.data));
    warm(qc, k.tagging.categoryUsage(), () =>
      taggingApi.getCategoryUsage().then((r) => r.data),
    );
    warm(qc, k.tagging.rules(), () => taggingApi.getRules().then((r) => r.data));
  },
  "/investments": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.investments.list(true), () =>
      investmentsApi.getAll(true).then((r) => r.data),
    );
    warm(qc, k.investments.portfolio(), () =>
      investmentsApi.getPortfolioAnalysis().then((r) => r.data),
    );
    warm(qc, k.investments.balanceHistory(true), () =>
      investmentsApi.getPortfolioBalanceHistory(true).then((r) => r.data),
    );
  },
  "/liabilities": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.liabilities.list(true), () =>
      liabilitiesApi.getAll(true).then((r) => r.data),
    );
    warm(qc, k.liabilities.debtOverTime(), () =>
      liabilitiesApi.getDebtOverTime().then((r) => r.data),
    );
  },
  "/insurances": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.insurance.accounts(), () =>
      insuranceAccountsApi.getAll().then((r) => r.data),
    );
    warm(qc, k.insurance.clearingHouseReports(), () =>
      insuranceAccountsApi.getClearingHouseReports().then((r) => r.data),
    );
    warm(qc, k.transactions.list("insurances", false), () =>
      transactionsApi.getAll("insurances").then((r) => r.data),
    );
  },
  "/early-retirement": (qc, { isDemoMode }) => {
    const k = makeQueryKeys(isDemoMode);
    warm(qc, k.fire.plan(), () => fireApi.getPlan().then((r) => r.data));
    warm(qc, k.fire.planProjection(), () =>
      fireApi.getPlanProjection().then((r) => r.data),
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

/**
 * Warm a single route: its page chunk and its data (on nav-link hover /
 * focus / pointerdown, and at boot for the route the app opened on).
 */
export function prefetchRoute(
  queryClient: QueryClient,
  path: string,
  ctx: PrefetchContext,
): void {
  loadRouteChunk(path);
  ROUTE_PREFETCH[path]?.(queryClient, ctx);
}
