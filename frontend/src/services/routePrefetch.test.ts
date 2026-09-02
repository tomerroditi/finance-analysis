import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { prefetchRoute } from "./routePrefetch";
import { makeQueryKeys } from "./queryKeys";
import { server } from "../mocks/server";

function newClient() {
  return new QueryClient({
    // gcTime must outlive the test: with gcTime 0 the flush below would let
    // the garbage collector wipe resolved prefetch entries mid-assertion.
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

/** Let the goal-chained warms (see routePrefetch) enqueue, then settle all. */
async function settle(qc: QueryClient) {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await Promise.all(
    qc
      .getQueryCache()
      .getAll()
      .map((q) => q.promise),
  );
}

describe("prefetchRoute", () => {
  // Regression: /early-retirement used hand-written literal keys
  // (["retirement","goal"] …) while the page reads the factory keys, which
  // carry the demo flag as their last segment. The four prefetched responses
  // landed under keys nothing reads — four wasted requests, four orphan
  // IndexedDB entries, and a page that still booted cold.
  it.each([true, false])(
    "warms /early-retirement under the factory keys the page reads (demo=%s)",
    async (isDemoMode) => {
      const qc = newClient();
      const k = makeQueryKeys(isDemoMode);

      prefetchRoute(qc, "/early-retirement", { isDemoMode });
      await qc.getQueryCache().find({ queryKey: k.retirement.goal() })?.promise;
      await settle(qc);

      expect(qc.getQueryData(k.retirement.goal())).toBeDefined();
      expect(qc.getQueryData(k.retirement.status())).toBeDefined();
      expect(qc.getQueryData(k.retirement.projections())).toBeDefined();
      expect(qc.getQueryData(k.retirement.suggestions())).toBeDefined();
    },
  );

  // Regression: projections/suggestions were warmed unconditionally, but both
  // endpoints 404 when no goal is configured — two guaranteed-failing
  // requests per nav hover, parked as error entries the page never reads.
  it("skips projections/suggestions when no goal is configured", async () => {
    server.use(
      http.get("/api/retirement/goal", () => HttpResponse.json(null)),
    );
    const qc = newClient();
    const k = makeQueryKeys(false);

    prefetchRoute(qc, "/early-retirement", { isDemoMode: false });
    await qc.getQueryCache().find({ queryKey: k.retirement.goal() })?.promise;
    await settle(qc);

    expect(qc.getQueryData(k.retirement.status())).toBeDefined();
    expect(
      qc.getQueryCache().find({ queryKey: k.retirement.projections() }),
    ).toBeUndefined();
    expect(
      qc.getQueryCache().find({ queryKey: k.retirement.suggestions() }),
    ).toBeUndefined();
  });

  it("writes no key that the query-key factory did not produce", async () => {
    const qc = newClient();
    const k = makeQueryKeys(true);
    const known = new Set(
      [
        k.retirement.goal(),
        k.retirement.status(),
        k.retirement.projections(),
        k.retirement.suggestions(),
      ].map((key) => JSON.stringify(key)),
    );

    prefetchRoute(qc, "/early-retirement", { isDemoMode: true });
    await settle(qc);

    for (const entry of qc.getQueryCache().getAll()) {
      expect(known.has(JSON.stringify(entry.queryKey))).toBe(true);
    }
  });
});
