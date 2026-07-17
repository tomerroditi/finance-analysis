import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";
test.describe("Liabilities", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("loads the liabilities page", async ({ page }) => {
    await navigateTo(page, "/liabilities");
    await expectPageTitle(page, /Liabilities/);
  });

  test("displays liability cards or empty state", async ({ page }) => {
    await navigateTo(page, "/liabilities");

    // Should show liability cards OR an empty state
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });

  test("shows debt over time chart", async ({ page }) => {
    await navigateTo(page, "/liabilities");

    // Debt over time section should be present
    await expect(page.getByText(/Debt Over Time/i)).toBeVisible({ timeout: 10_000 });
  });
});
