import { test, expect } from "@playwright/test";
import { enableDemoMode, API_BASE } from "./helpers";

/**
 * Sidebar.tsx no longer fetches the full transaction list to compute the
 * uncategorized badge — it calls the dedicated
 * GET /api/transactions/uncategorized-count endpoint instead. This spec
 * verifies the badge rendered on the /transactions nav link agrees with
 * that endpoint's count, covering both branches: a numeric badge when
 * count > 0, and no numeric badge when everything is categorized.
 */
test.describe("sidebar uncategorized badge", () => {
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("badge count matches the backend count endpoint", async ({
    page,
    request,
  }) => {
    // The `request` fixture is Playwright's own HTTP client — it does not
    // run the app's JS, so the axios interceptor that attaches `X-FAD-Demo`
    // from localStorage never runs for it. Declare the header explicitly so
    // this reads the same (demo) count the page itself is about to render.
    const res = await request.get(
      `${API_BASE}/transactions/uncategorized-count`,
      {
        headers: { "X-FAD-Demo": "1" },
      },
    );
    expect(res.ok()).toBeTruthy();
    const { count } = await res.json();

    await page.goto("/");
    await page.waitForResponse(
      (r) =>
        r.url().includes("/api/transactions/uncategorized-count") && r.ok(),
    );
    await page.waitForLoadState("domcontentloaded");

    const transactionsLink = page
      .getByRole("link", { name: /transactions/i })
      .first();
    await expect(transactionsLink).toBeVisible();

    if (count > 0) {
      await expect(transactionsLink).toContainText(
        String(count > 99 ? "99+" : count),
      );
    } else {
      // No badge rendered when everything is categorized.
      await expect(transactionsLink).not.toContainText(/\d/);
    }
  });
});
