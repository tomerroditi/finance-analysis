import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Hold every request matching `pattern` until the returned `release` is
 * called, so a test can look at the screen while the data is still loading.
 */
async function holdRequests(page: Page, pattern: string) {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(pattern, async (route) => {
    await gate;
    await route.continue();
  });
  return release;
}

test.describe("Loading states", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("project budgets show a spinner, not 'no projects', while loading", async ({
    page,
  }) => {
    const release = await holdRequests(page, "**/api/budget/projects/status");
    await navigateTo(page, "/budget");

    await page.getByRole("button", { name: /Project Budgets/i }).first().click();
    await expect(page.getByTestId("loading-spinner")).toBeVisible();
    await expect(page.getByText(/No Projects Found/i)).toHaveCount(0);

    release();
    await expect(page.getByTestId("loading-spinner")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.getByTestId("ledger-figures").first()).toBeVisible();
    await expect(page.getByText(/No Projects Found/i)).toHaveCount(0);
  });

  test("the net worth card shows a spinner, not 'no data', while loading", async ({
    page,
  }) => {
    const release = await holdRequests(page, "**/api/analytics/net-worth-over-time*");
    await navigateTo(page, "/");

    const card = page.locator('[data-card-id="net_worth"]');
    await expect(card).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();
    await expect(card.getByTestId("loading-spinner")).toBeVisible();
    await expect(card.getByText(/No net worth data/i)).toHaveCount(0);

    release();
    await expect(card.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(card.getByTestId("loading-spinner")).toHaveCount(0);
  });
});
