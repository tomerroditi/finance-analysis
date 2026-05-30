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

  test("dragging a card reorders and persists", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Drag the first card ("This Month (forecast)") down past the second one.
    // The whole row is the drag handle; grab it by its label text.
    const firstRow = page
      .getByText("This Month (forecast)", { exact: true })
      .locator("xpath=..");
    await expect(firstRow).toBeVisible();
    const box = await firstRow.boundingBox();
    if (!box) throw new Error("no drag handle box");

    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down();
    // Move in steps so @dnd-kit's pointer sensor activates and animates.
    await page.mouse.move(box.x + 20, box.y + 80, { steps: 8 });
    await page.mouse.move(box.x + 20, box.y + 140, { steps: 8 });
    await page.mouse.up();

    // The persisted order should no longer start with "forecast".
    const order = await page.evaluate(() => {
      const raw = window.localStorage.getItem("fa.dashboard.layout");
      return raw ? (JSON.parse(raw).order as string[]) : [];
    });
    expect(order[0]).not.toBe("forecast");
    expect(order).toContain("forecast");
  });

  test("X button closes the settings popup", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    // The popup heading is visible.
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toBeVisible();
    await page.getByRole("button", { name: /^Close$/ }).click();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toHaveCount(0);
  });
});
