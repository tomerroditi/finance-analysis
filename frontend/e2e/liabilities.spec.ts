import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("Liabilities", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  // One navigation covers the page smoke, the debt chart section, and the
  // Recharts hydration guard (formerly a separate charts-render.spec.ts case).
  test("loads the liabilities page with the debt-over-time chart", async ({ page }) => {
    await navigateTo(page, "/liabilities");
    await expectPageTitle(page, /Liabilities/);

    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByText(/Debt Over Time/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 30_000,
    });
  });
});
