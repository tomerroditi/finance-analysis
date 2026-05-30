import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Auto-tagging rule management lives on the Categories page (opened via the
 * "Auto-Tagging Rules" launcher, which presents a full-screen manager). These
 * tests assert the manager entry point works and the rule editor opens — the
 * high-value regression to catch. Creating a rule end-to-end is brittle
 * (depends on demo categories), so we stop at the editor.
 */
test.describe("Auto-tagging rule flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("opens the Auto-Tagging Rules manager and shows existing rules", async ({ page }) => {
    await gotoAndWait(page, "/categories");
    await expect(
      page.getByRole("button", { name: /auto-tagging rules/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Open the full-screen rules manager.
    await page.getByRole("button", { name: /auto-tagging rules/i }).click();

    // The manager dialog shows the New Rule / Apply Rules controls.
    const manager = page.locator(
      '[role="dialog"][aria-labelledby="rules-manager-title"]',
    );
    await expect(manager).toBeVisible({ timeout: 5_000 });
    await expect(
      manager.getByRole("button", { name: /^new rule$/i }).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("new rule defaults the conditions group to OR", async ({ page }) => {
    await gotoAndWait(page, "/categories");
    await expect(
      page.getByRole("button", { name: /auto-tagging rules/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /auto-tagging rules/i }).click();
    const manager = page.locator(
      '[role="dialog"][aria-labelledby="rules-manager-title"]',
    );
    await expect(manager).toBeVisible({ timeout: 5_000 });
    await manager.getByRole("button", { name: /^new rule$/i }).first().click();

    const dialog = page.getByRole("dialog").last();
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
