import { test, expect, request } from "@playwright/test";
import { enableDemoMode, navigateTo, API_BASE } from "../helpers";

/**
 * The core regression for per-client Demo Mode: two browser contexts against
 * one backend, in opposite modes, must not affect each other. Before this
 * work the flag was a process-global singleton, so the demo context switching
 * on would have switched the real context's database too.
 */
test.describe("Demo Mode isolation", () => {
  test("two contexts in opposite modes do not interfere", async ({
    browser,
  }) => {
    const demoContext = await browser.newContext();
    const realContext = await browser.newContext();

    try {
      const demoPage = await demoContext.newPage();
      const realPage = await realContext.newPage();

      await enableDemoMode(demoPage);
      await navigateTo(demoPage, "/");
      await navigateTo(realPage, "/");

      // The demo client sends the header; the real client must not.
      const demoHeader = await demoPage.evaluate(() =>
        localStorage.getItem("fad_demo_mode"),
      );
      const realHeader = await realPage.evaluate(() =>
        localStorage.getItem("fad_demo_mode"),
      );
      expect(demoHeader).toBe("1");
      expect(realHeader).not.toBe("1");

      // The demo client shows the Cohen family's seeded accounts; the real
      // client, against an empty real DB, shows its empty state. Assert on a
      // positive anchor in each rather than networkidle.
      await expect(demoPage.getByRole("navigation").first()).toBeVisible();
      await expect(realPage.getByRole("navigation").first()).toBeVisible();

      const demoRequest = demoPage.waitForRequest(
        (req) =>
          req.url().includes("/api/") && req.headers()["x-fad-demo"] === "1",
      );
      await demoPage.reload();
      await demoRequest;

      const realRequests: string[] = [];
      realPage.on("request", (req) => {
        if (req.url().includes("/api/") && req.headers()["x-fad-demo"]) {
          realRequests.push(req.url());
        }
      });
      await realPage.reload();
      await expect(realPage.getByRole("navigation").first()).toBeVisible();
      expect(realRequests).toEqual([]);

      // The header being sent (asserted above) proves nothing about whether
      // the backend actually branches on it — a backend that ignored
      // X-FAD-Demo entirely and served one shared database would still pass
      // every assertion so far. Hit the same read-only endpoint from two
      // direct API contexts, one with the header and one without, and prove
      // the backend returns genuinely different data. Assert "differ" rather
      // than "the real one is empty": in the isolated harness each shard
      // gets a fresh, empty real DB, but that's not true on a developer
      // machine with real data — difference is the invariant that holds
      // everywhere.
      const demoCtx = await request.newContext({
        extraHTTPHeaders: { "X-FAD-Demo": "1" },
      });
      const realCtx = await request.newContext();
      try {
        const [demoRes, realRes] = await Promise.all([
          demoCtx.get(`${API_BASE}/transactions/`),
          realCtx.get(`${API_BASE}/transactions/`),
        ]);
        expect(demoRes.ok()).toBe(true);
        expect(realRes.ok()).toBe(true);

        const [demoBody, realBody] = await Promise.all([
          demoRes.json(),
          realRes.json(),
        ]);

        // The demo DB is stocked with the Cohen family's seeded transactions.
        expect(Array.isArray(demoBody) ? demoBody.length : 0).toBeGreaterThan(
          0,
        );
        expect(JSON.stringify(demoBody)).not.toBe(JSON.stringify(realBody));
      } finally {
        await demoCtx.dispose();
        await realCtx.dispose();
      }
    } finally {
      await demoContext.close();
      await realContext.close();
    }
  });
});
