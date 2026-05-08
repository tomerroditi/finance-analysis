import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Creates a new monthly budget rule and verifies it appears in the list,
 * then deletes it to keep the demo dataset stable.
 */
test.describe("Budget rule creation flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("creates a new monthly budget rule", async ({ page }) => {
    const ruleName = `E2E Test Budget ${Date.now()}`;
    await gotoAndWait(page, "/budget");

    // Open the Add Rule modal.
    await page.getByRole("button", { name: /^add rule$/i }).first().click();
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
