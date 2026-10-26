import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { prefetchRoute } from "./routePrefetch";
import { makeQueryKeys } from "./queryKeys";
import { loadRouteChunk } from "../routeChunks";
import type * as DashboardLayoutModule from "../hooks/useDashboardLayout";

vi.mock("../routeChunks", () => ({ loadRouteChunk: vi.fn() }));

const layout: { order: string[]; hidden: string[] } = { order: [], hidden: [] };
vi.mock("../hooks/useDashboardLayout", async (importOriginal) => ({
  ...(await importOriginal<typeof DashboardLayoutModule>()),
  readDashboardLayout: () => layout,
}));

function newClient() {
  return new QueryClient({
    // gcTime must outlive the test: with gcTime 0 the flush below would let
    // the garbage collector wipe resolved prefetch entries mid-assertion.
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

async function settle(qc: QueryClient) {
  await Promise.allSettled(
    qc
      .getQueryCache()
      .getAll()
      .map((q) => q.promise),
  );
}

describe("prefetchRoute", () => {
  // Regression: /early-retirement once used hand-written literal keys while
  // the page read the factory keys, which carry the demo flag as their last
  // segment — the prefetched responses landed under keys nothing reads.
  it.each([true, false])(
    "warms /early-retirement under the factory keys the page reads (demo=%s)",
    async (isDemoMode) => {
      const qc = newClient();
      const k = makeQueryKeys(isDemoMode);

      prefetchRoute(qc, "/early-retirement", { isDemoMode });
      await settle(qc);

      expect(qc.getQueryData(k.fire.plan())).toBeDefined();
      expect(qc.getQueryData(k.fire.planProjection())).toBeDefined();
    },
  );

  it("writes no key that the query-key factory did not produce", async () => {
    const qc = newClient();
    const k = makeQueryKeys(true);
    const known = new Set(
      [k.fire.plan(), k.fire.planProjection()].map((key) => JSON.stringify(key)),
    );

    prefetchRoute(qc, "/early-retirement", { isDemoMode: true });
    await settle(qc);

    for (const entry of qc.getQueryCache().getAll()) {
      expect(known.has(JSON.stringify(entry.queryKey))).toBe(true);
    }
  });
});

const keysAfter = async (path: string) => {
  const qc = newClient();
  prefetchRoute(qc, path, { isDemoMode: false });
  await settle(qc);
  return qc
    .getQueryCache()
    .getAll()
    .map((q) => JSON.stringify(q.queryKey));
};

describe("prefetchRoute — what each route warms", () => {
  beforeEach(() => {
    vi.mocked(loadRouteChunk).mockClear();
    layout.order = ["budget", "recurring"];
  });

  it("loads the route's page chunk with its data", async () => {
    await keysAfter("/liabilities");
    expect(loadRouteChunk).toHaveBeenCalledWith("/liabilities");
  });

  it("leaves the whole history alone when no dashboard card shows it", async () => {
    const list = JSON.stringify(makeQueryKeys(false).transactions.list(undefined, false));
    expect(await keysAfter("/")).not.toContain(list);

    layout.order = ["budget", "recent"];
    expect(await keysAfter("/")).toContain(list);
  });

  it("warms the transactions table's own reads with the list", async () => {
    const k = makeQueryKeys(false);
    const keys = await keysAfter("/transactions");
    for (const key of [
      k.transactions.list(undefined, false),
      k.tagging.categories(),
      k.tagging.icons(),
      k.tagging.rules(),
      k.balances.cash(),
      k.savingsGoals.links(),
    ]) {
      expect(keys).toContain(JSON.stringify(key));
    }
    expect(keys).not.toContain(JSON.stringify(k.savingsGoals.all()));
  });

  it("warms the budget Overview for the current month", async () => {
    const k = makeQueryKeys(false);
    const now = new Date();
    const [year, month] = [now.getFullYear(), now.getMonth() + 1];
    const keys = await keysAfter("/budget");
    expect(keys).toContain(JSON.stringify(k.budget.overview(year, month, false)));
    expect(keys).toContain(JSON.stringify(k.budget.trend(year, month, 12, false)));
  });
});
