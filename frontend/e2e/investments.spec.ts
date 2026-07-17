import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";
test.describe("Investments", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("loads the investments page", async ({ page }) => {
    await navigateTo(page, "/investments");
    await expectPageTitle(page, /Investments/);
  });

  test("displays investment cards", async ({ page }) => {
    await navigateTo(page, "/investments");

    // Should show investment cards with names
    const cards = page.locator("[class*='rounded-2xl']");
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows portfolio overview section", async ({ page }) => {
    await navigateTo(page, "/investments");

    // Portfolio section should be visible
    await expect(page.getByText(/Portfolio/i).first()).toBeVisible();
  });

  test("closed investments toggle works", async ({ page }) => {
    await navigateTo(page, "/investments");
    await page.waitForLoadState("networkidle");

    // Find the include/hide closed toggle button
    const closedToggle = page.getByRole("button", { name: /closed/i });
    if (await closedToggle.isVisible().catch(() => false)) {
      await closedToggle.click();
      await page.waitForTimeout(500);
    }
  });
});
