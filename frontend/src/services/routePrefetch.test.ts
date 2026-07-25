import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { prefetchRoute } from "./routePrefetch";
import { makeQueryKeys } from "./queryKeys";

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
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
      await Promise.all(
        qc
          .getQueryCache()
          .getAll()
          .map((q) => q.promise),
      );

      expect(qc.getQueryData(k.retirement.goal())).toBeDefined();
      expect(qc.getQueryData(k.retirement.status())).toBeDefined();
      expect(qc.getQueryData(k.retirement.projections())).toBeDefined();
      expect(qc.getQueryData(k.retirement.suggestions())).toBeDefined();
    },
  );

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
    await Promise.all(
      qc
        .getQueryCache()
        .getAll()
        .map((q) => q.promise),
    );

    for (const entry of qc.getQueryCache().getAll()) {
      expect(known.has(JSON.stringify(entry.queryKey))).toBe(true);
    }
  });
});
