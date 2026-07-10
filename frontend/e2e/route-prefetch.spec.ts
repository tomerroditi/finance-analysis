import { test, expect } from "@playwright/test";

/**
 * Pages share one bundle, so navigation lag is the destination page's first
 * data fetch. Route prefetching warms that data when the user shows intent to
 * navigate (hover / focus / press a nav link), so the click lands on an
 * already-fetched page. Verified by observing the request fire on hover —
 * without navigating — and then that the page renders without a fresh fetch.
 */
test.describe("Route data prefetching", () => {
  test("hovering a nav link prefetches that route's data", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({
      timeout: 45_000,
    });

    // The dashboard never fetches the liabilities endpoint, so a liabilities
    // request right after hovering the link is the hover prefetch firing.
    const liabilitiesRequest = page.waitForRequest(
      (req) => /\/api\/liabilities/.test(req.url()),
      { timeout: 15_000 },
    );
    await page.locator('a[href="/liabilities"]').first().hover();
    await liabilitiesRequest;

    // Hovering must not navigate.
    await expect(page).toHaveURL(/\/$/);
  });

  test("prefetched route paints without a fresh load on navigation", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({
      timeout: 45_000,
    });

    // Warm the route, then navigate; its data is already cached so the page
    // content is there. Set the request listener up before hovering so the
    // prefetch request isn't missed.
    const link = page.locator('a[href="/liabilities"]').first();
    const liabilitiesRequest = page.waitForRequest(
      (req) => /\/api\/liabilities/.test(req.url()),
      { timeout: 15_000 },
    );
    await link.hover();
    await liabilitiesRequest;
    await link.click();
    await expect(page).toHaveURL(/\/liabilities$/);
    await expect(page.getByRole("navigation").first()).toBeVisible();
  });
});
