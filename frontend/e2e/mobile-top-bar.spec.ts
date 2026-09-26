import { test, expect } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * On mobile, the utility entries from the desktop sidebar footer — Budget
 * Alerts, Settings and Data Flow — live only in the top bar. The menu drawer
 * holds page links alone.
 */
test.describe("mobile top bar", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("utilities sit in the top bar, not the menu drawer", async ({ page }) => {
    await page.goto("/");

    const topBar = page.getByTestId("mobile-top-bar");
    await expect(topBar).toBeVisible();
    await expect(topBar.getByRole("button", { name: "Settings" })).toBeVisible();
    await expect(topBar.getByRole("button", { name: /Budget Alerts/i })).toBeVisible();
    const dataFlowLink = topBar.getByRole("link", { name: "Data Flow" });
    await expect(dataFlowLink).toBeVisible();

    await topBar.getByTestId("mobile-menu-button").click();
    const drawer = page.getByTestId("mobile-menu-drawer");
    await expect(drawer.getByRole("link", { name: "Transactions" })).toBeVisible();
    await expect(drawer.getByText("Settings", { exact: true })).toHaveCount(0);
    await expect(drawer.getByText("Budget Alerts", { exact: true })).toHaveCount(0);
    await expect(drawer.getByText("Data Flow", { exact: true })).toHaveCount(0);
    await drawer.getByRole("button").first().click();
    await expect(drawer).toHaveCount(0);

    await dataFlowLink.click();
    await expect(page).toHaveURL(/\/data-flow$/);
  });
});
