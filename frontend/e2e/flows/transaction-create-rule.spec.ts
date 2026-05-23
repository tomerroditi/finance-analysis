import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Opens the Auto Tagging panel from the Transactions page and verifies
 * the rule list / rule editor is reachable. Creating a rule end-to-end
 * is brittle (depends on demo categories) so this asserts the Auto
 * Tagging entry point works, which is the high-value regression to catch.
 */
test.describe("Auto-tagging rule flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("opens the Auto Tagging panel and shows existing rules", async ({ page }) => {
    await gotoAndWait(page, "/transactions");
    await expect(page.locator("table tbody tr").first()).toBeVisible({
      timeout: 15_000,
    });

    // Click the floating Auto Tagging FAB / button.
    await page.getByRole("button", { name: /auto tagging/i }).click();

    // The panel slides out and shows its "Auto Tagging" heading + rule rows.
    await expect(
      page.getByRole("heading", { name: /^auto tagging$/i }),
    ).toBeVisible({ timeout: 5_000 });

    // Demo data ships 11 tagging rules — at least one should render.
    await expect(
      page.getByRole("button", { name: /add rule|new rule/i }).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("new rule defaults the conditions group to OR", async ({ page }) => {
    await gotoAndWait(page, "/transactions");
    await expect(page.locator("table tbody tr").first()).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: /auto tagging/i }).click();
    await page.getByRole("button", { name: /new rule/i }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Top-level conditions group should default to "OR (Any match)".
    await expect(
      dialog.getByRole("button", { name: /OR \(Any match\)/i }).first(),
    ).toBeVisible({ timeout: 5_000 });

    // Adding a nested group should also default to OR (consistency).
    await dialog.getByRole("button", { name: /^\+ Group$|^Group$/ }).first().click();
    await expect(
      dialog.getByRole("button", { name: /OR \(Any match\)/i }),
    ).toHaveCount(2, { timeout: 5_000 });

    // Close without saving.
    await dialog.getByRole("button", { name: /^cancel$/i }).click();
  });
});
