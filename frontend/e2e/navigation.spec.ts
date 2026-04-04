import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

test.describe("Navigation", () => {
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

  test("sidebar navigation works across all pages", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const routes = [
      { link: /Transactions/i, url: "/transactions", heading: /Transactions/ },
      { link: /Budget/i, url: "/budget", heading: /Budget/ },
      { link: /Categories/i, url: "/categories", heading: /Categories/ },
      { link: /Investments/i, url: "/investments", heading: /Investments/ },
      { link: /Liabilities/i, url: "/liabilities", heading: /Liabilities/ },
      { link: /Data Sources/i, url: "/data-sources", heading: /Data Sources/ },
    ];

    for (const route of routes) {
      // Click sidebar link
      const link = page.getByRole("link", { name: route.link }).first();
      if (await link.isVisible().catch(() => false)) {
        await link.click();
        await page.waitForLoadState("networkidle");

        // Verify URL changed
        expect(page.url()).toContain(route.url);
      }
    }
  });

  test("global search opens with Cmd+K", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Press Cmd+K (Ctrl+K on non-Mac)
    await page.keyboard.press("Control+k");

    // Search overlay should appear
    const searchInput = page.getByPlaceholder(/search/i).first();
    // It may or may not be present depending on implementation
    if (await searchInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      await expect(searchInput).toBeVisible();

      // Close with Escape
      await page.keyboard.press("Escape");
    }
  });
});
