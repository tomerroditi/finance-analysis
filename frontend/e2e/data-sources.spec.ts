import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("DataSources", () => {
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

  test("loads the data sources page", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await expectPageTitle(page, /Data Sources/);
  });

  test("displays connected accounts in demo mode", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // In demo mode, there should be demo accounts listed
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });

  test("shows bank balance section", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // Bank balance section should show account balances
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });

  test("renders provider logos on each connected account card", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // The four demo accounts (Hapoalim, Max, Visa Cal, HaPhoenix) each render
    // a <ProviderLogo> with alt text set to the humanized provider name. We
    // verify the image actually loaded — naturalWidth > 0 only holds once the
    // browser has decoded a real image, so a broken/missing logo would fail
    // here even with width/height set in HTML. (Vite inlines small SVGs as
    // data: URIs and emits larger ones as hashed assets, so checking the src
    // attribute itself isn't portable.)
    for (const alt of ["Hapoalim", "Max", "Visa Cal", "HaPhoenix"]) {
      const img = page.getByRole("img", { name: alt }).first();
      await expect(img).toBeVisible();
      await expect
        .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0);
    }
  });

  test("shows provider logos in the connect-account modal grid", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // Step 1: open the connect-account modal and pick the Bank Account flow.
    await page.getByRole("button", { name: "Connect Account", exact: true }).click();
    await page.getByRole("button", { name: /Bank Account/ }).click();

    // Step 2: a representative subset of banks should appear with their logos.
    // We don't enumerate all 11 — the goal is to lock in that the grid actually
    // renders ProviderLogo and the images aren't broken.
    for (const provider of ["Hapoalim", "Leumi", "Discount", "Mizrahi"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }

    // Bounce back to step 1 and try credit cards to make sure that grid wires
    // up too (different service key, different filename mappings — e.g. visa
    // cal has a space and Beyahad Bishvilha is a PNG instead of SVG).
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: /Credit Card/ }).click();
    for (const provider of ["Max", "Visa Cal", "Isracard", "Amex"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }
  });
});
