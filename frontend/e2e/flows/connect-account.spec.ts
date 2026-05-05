import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Verifies the Connect Account flow on the Data Sources page opens the
 * service type chooser with all expected provider categories.
 */
test.describe("Connect Account flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("opens the Connect Account dialog with all service types", async ({ page }) => {
    await gotoAndWait(page, "/data-sources");

    // Click either "Connect Account" header button or the empty-state CTA.
    const connectButton = page
      .getByRole("button", { name: /^connect account$/i })
      .or(page.getByRole("button", { name: /connect first account/i }))
      .first();
    await connectButton.click();

    // Verify the chooser surfaces all three top-level service types.
    await expect(page.getByRole("heading", { name: /connect new account/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /bank account/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /credit card/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^insurance/i })).toBeVisible();

    // Picking Bank Account drills into the provider list.
    await page.getByRole("button", { name: /^bank account/i }).click();
    // Expect at least one Israeli bank shown — Hapoalim is in the demo set.
    await expect(page.getByText(/hapoalim|leumi|discount/i).first()).toBeVisible({
      timeout: 5_000,
    });
  });
});
