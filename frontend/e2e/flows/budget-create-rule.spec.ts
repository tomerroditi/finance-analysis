import { test, expect } from "@playwright/test";
import { gotoAndWait } from "./_helpers";
import { enableDemoMode } from "../helpers";

/**
 * Creates a new monthly budget rule and verifies it appears in the list,
 * then deletes it to keep the demo dataset stable.
 *
 * Demo Mode is seeded per-page via `enableDemoMode` in `beforeEach` rather
 * than a `beforeAll` — the flag lives in the test's own browser context
 * (localStorage), which doesn't exist yet in `beforeAll` (no `page`
 * fixture there), and wouldn't carry over from a separately-created page
 * even if it did.
 */
test.describe("Budget rule creation flow", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("creates a new monthly budget rule", async ({ page }) => {
    const ruleName = `E2E Test Budget ${Date.now()}`;
    await gotoAndWait(page, "/budget");

    // Open the Add Rule modal.
    await page
      .getByRole("button", { name: /^add rule$/i })
      .first()
      .click();
    const dialog = page.getByRole("dialog", { name: /add budget rule/i });
    await expect(dialog).toBeVisible();

    await dialog.getByPlaceholder(/Monthly Groceries/i).fill(ruleName);
    await dialog.getByRole("spinbutton").fill("1234");

    // Pick the Food category.
    await dialog.getByRole("button", { name: /select category/i }).click();
    await page.getByRole("option", { name: /^food$/i }).click();

    // Save and verify it appears in the list.
    await dialog.getByRole("button", { name: /save rule/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });

    // The new rule appears as a row.
    await expect(page.getByText(ruleName).first()).toBeVisible({
      timeout: 10_000,
    });

    // Cleanup: delete the rule we just created.
    const ruleRow = page.locator("div", { hasText: ruleName }).first();
    const deleteBtn = ruleRow.getByRole("button", { name: /delete rule/i });
    if (await deleteBtn.isVisible().catch(() => false)) {
      page.once("dialog", (d) => d.accept());
      await deleteBtn.click();
    }
  });
});
