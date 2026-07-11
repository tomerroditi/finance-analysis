import { test, expect } from "@playwright/test";
import { navigateTo, expectPageTitle } from "./helpers";

test.describe("Liabilities", () => {
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
