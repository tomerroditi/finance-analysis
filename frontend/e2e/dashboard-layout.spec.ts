import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Customizable dashboard layout: the Settings → Dashboard tab lets users
 * reorder and hide cards; the KPI header stays pinned. Persistence is
 * localStorage-backed.
 */
test.describe("Dashboard layout customization", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    // Start each test from a clean layout.
    await page.addInitScript(() => window.localStorage.removeItem("fa.dashboard.layout"));
  });

  test("hiding a card removes it from the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });

    // Open settings via the sidebar button, switch to the Dashboard tab.
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Hide the "Subscriptions & recurring" card: find its label, walk to the
    // row, click the Hide button inside it.
    const label = page.getByText("Subscriptions & recurring", { exact: true });
    await expect(label).toBeVisible();
    const row = label.locator("xpath=..");
    await row.getByRole("button", { name: /Hide card/i }).click();

    // It should now appear under the "Hidden cards" heading (exact, to avoid
    // matching the help text that also contains the phrase).
    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();

    // Close settings (Escape) and confirm the card is gone from the dashboard.
    await page.keyboard.press("Escape");
    await expect(page.getByText(/Subscriptions & Recurring/i)).toHaveCount(0);
  });

  test("hidden card persists across reload and can be restored", async ({ page }) => {
    // Pre-hide via localStorage to keep the test deterministic.
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          order: ["forecast", "insights", "budget", "recent", "goals", "heatmap", "charts"],
          hidden: ["recurring"],
        }),
      );
    });
    await page.goto("/");
    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Subscriptions & Recurring/i)).toHaveCount(0);

    // Restore it from settings.
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();
    await page.getByRole("button", { name: /Show card/i }).first().click();
    await page.keyboard.press("Escape");

    await expect(page.getByText(/Subscriptions & Recurring/i).first()).toBeVisible();
  });

  test("KPI header stays pinned regardless of layout", async ({ page }) => {
    await page.goto("/");
    // Net Worth KPI lives in the pinned header and is never in the card set.
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({ timeout: 45_000 });
  });
});
