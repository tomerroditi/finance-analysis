import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * E2E coverage for the auto-tagging refactor:
 *
 *  1. Rule management moved off the Transactions side panel into an
 *     "Auto-Tagging Rules" section on the Categories page.
 *  2. While marking transactions, the bulk actions bar surfaces an
 *     "Add Rule" / "View Rule" quick action. "Add Rule" opens the rule editor
 *     pre-filled with a description condition derived from the selection.
 */
test.describe("Auto-tagging quick action + Categories rules section", () => {
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

  test("Categories page hosts the Auto-Tagging Rules section", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // The launcher card opens the full-screen rules manager.
    await page.getByRole("button", { name: /Auto-Tagging Rules/i }).click();
    await expect(
      page.getByRole("heading", { name: /Auto-Tagging Rules/i }),
    ).toBeVisible({ timeout: 10_000 });

    // The "New Rule" button in the manager opens the rule editor.
    await page.getByRole("button", { name: /^New Rule$/ }).click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();
  });

  test("bulk selection surfaces the Add/View rule quick action", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Credit-card transactions are rule-applicable, so the quick action shows.
    await page.getByRole("button", { name: /Credit Card/i }).click();
    await page.waitForLoadState("networkidle");

    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Select a single credit-card transaction to surface the bulk actions bar.
    await rows.first().locator('input[type="checkbox"]').check();

    const bulkBar = page
      .locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8")
      .last();
    await expect(bulkBar).toBeVisible({ timeout: 5_000 });

    const ruleButton = bulkBar.getByRole("button", { name: /Add Rule|View Rule/ });
    await expect(ruleButton).toBeVisible();

    const label = (await ruleButton.textContent())?.trim() ?? "";
    // A disabled button means the selection is ambiguous; nothing to open.
    if (await ruleButton.isDisabled()) return;

    await ruleButton.click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();

    if (/Add Rule/.test(label)) {
      // "Add Rule" pre-fills a description-contains condition from the
      // selected transaction (cleaned of noise like .com / dashes / digits).
      const valueInput = modal
        .locator('input[placeholder="Value"]:visible')
        .first();
      await expect(valueInput).toBeVisible();
      await expect(valueInput).not.toHaveValue("");
    }
  });
});
