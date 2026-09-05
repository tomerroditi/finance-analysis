import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "../helpers";

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
    } finally {
      await demoContext.close();
      await realContext.close();
    }
  });
});
