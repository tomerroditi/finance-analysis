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

    // Demo data always includes closed investments, so the section renders
    // unconditionally — assert it instead of skipping (the old conditional
    // body passed vacuously when the button was missing).
    await expect(
      page.getByText(/Closed Investments/i).first(),
    ).toBeVisible();

    // The balance-over-time chart's closed toggle defaults ON ("Hide
    // Closed") and flips its label per state.
    const hideToggle = page.getByRole("button", { name: "Hide Closed" });
    await expect(hideToggle).toBeVisible();
    await hideToggle.click();

    const includeToggle = page.getByRole("button", { name: "Include Closed" });
    await expect(includeToggle).toBeVisible();
    await includeToggle.click();
    await expect(hideToggle).toBeVisible();
  });
});
