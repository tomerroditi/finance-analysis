import { describe, it, expect } from "vitest";

/**
 * The `/api` runtime cache is NetworkFirst, and its network timeout decides
 * how long a live-but-slow backend is given before the service worker
 * abandons it and answers from the previous response.
 *
 * At 4 s that was not a fallback, it was data loss: every derived analytics
 * read (recurring detection, budget overview, forecast, insights) passes 4 s
 * on a real database, and *always* does right after a write, because the
 * commit discards the backend's `data_cache` generation and the next read
 * pays the full recompute. So the refetch that follows a write was answered
 * with the body from *before* it — confirm a recurring charge and it went
 * back to "needs review" a few seconds later, permanently, because the
 * optimistic update had already been replaced by a pre-write payload.
 *
 * Offline never depended on this number: NetworkFirst falls back the moment
 * a request errors. The timeout only bounds a connection that is up and
 * silent, so it belongs above any plausible recompute.
 *
 * A source scan rather than a config import: the value lives inside the
 * VitePWA plugin's Workbox options, which are not reachable from the built
 * plugin object. Read through `import.meta.glob` rather than `node:fs`, for
 * the reason `tailwindLogicalProperties.test.ts` gives — `tsconfig.app.json`
 * is browser-only, so a `node:fs` import breaks `npm run build`, not just
 * this test.
 */

const MINIMUM_SECONDS = 20;

const CONFIG = Object.values(
  import.meta.glob("../vite.config.ts", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>,
)[0];

describe("service worker /api runtime cache", () => {
  it("gives a slow backend longer than any recompute before serving a stale body", () => {
    const match = CONFIG.match(/networkTimeoutSeconds:\s*(\d+)/);

    expect(match, "networkTimeoutSeconds not found in vite.config.ts").toBeTruthy();
    expect(Number(match![1])).toBeGreaterThanOrEqual(MINIMUM_SECONDS);
  });

  it("still keeps written-to and sensitive endpoints out of the cache", () => {
    for (const path of [
      "/api/scraping/",
      "/api/credentials",
      "/api/backups",
      "/api/testing/",
    ]) {
      expect(CONFIG).toContain(path);
    }
    // Demo responses must never land in a cache keyed only by URL.
    expect(CONFIG).toContain("X-FAD-Demo");
  });
});
