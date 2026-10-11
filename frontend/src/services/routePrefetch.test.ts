import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { prefetchRoute } from "./routePrefetch";
import { makeQueryKeys } from "./queryKeys";

function newClient() {
  return new QueryClient({
    // gcTime must outlive the test: with gcTime 0 the flush below would let
    // the garbage collector wipe resolved prefetch entries mid-assertion.
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

async function settle(qc: QueryClient) {
  await Promise.all(
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
