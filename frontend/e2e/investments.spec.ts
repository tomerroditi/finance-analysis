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

    // Assert the toggle exists instead of skipping the whole body when the
    // button is missing or renamed (the old conditional passed vacuously).
    const closedToggle = page
      .getByRole("button", { name: /closed/i })
      .first();
    await expect(closedToggle).toBeVisible();

    // Demo data includes closed investments: toggling on must reveal the
    // Closed Investments section, toggling off must hide it.
    await closedToggle.click();
    const closedSection = page.getByText(/Closed Investments/i).first();
    await expect(closedSection).toBeVisible();

    await closedToggle.click();
    await expect(closedSection).toBeHidden();
  });
});
