import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Adds a new tag under the Food category, verifies it appears in the panel,
 * then deletes it for cleanup.
 */
test.describe("Categories add-tag flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("adds a new tag to the Food category", async ({ page }) => {
    const tagName = `e2e-tag-${Date.now()}`;
    await gotoAndWait(page, "/categories");

    // Click the Food category card to open the detail panel.
    const foodCard = page.locator('[data-testid="category-card-Food"]');
    await expect(foodCard).toBeVisible();
    await foodCard.click();

    // The panel should open.
    const panel = page.locator('[data-testid="category-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // Click the "Add Tag" button inside the panel.
    const addTagBtn = panel.locator('button[title="Add Tag"]').first();
    await expect(addTagBtn).toBeVisible({ timeout: 5_000 });
    await addTagBtn.click();

    // Fill the tag name field in the modal.
    const dialog = page.getByRole("dialog", { name: /add tag to food/i });
    await expect(dialog).toBeVisible();
    await dialog.getByPlaceholder(/tag name/i).fill(tagName);
    await dialog.getByRole("button", { name: /^add tag$/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });

    // The new tag should appear inside the panel.
    await expect(panel.getByText(tagName)).toBeVisible({ timeout: 10_000 });
  });
});
