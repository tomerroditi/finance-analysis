import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Adds a new tag under the Food category, verifies it appears, then
 * deletes it for cleanup.
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

    // Find the Food category row by its heading.
    const foodHeading = page.getByRole("heading", { name: /^food$/i });
    await expect(foodHeading).toBeVisible();

    // The Add Tag button lives in the same header row as the Food heading.
    // Use the title attribute rather than getByRole to avoid accessible-name
    // computation quirks with emoji-content buttons (aria-label vs text content).
    const foodCard = foodHeading.locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");
    await foodCard.locator('button[title="Add Tag"]').first().click();

    // Fill the tag name field in the modal.
    const dialog = page.getByRole("dialog", { name: /add tag to food/i });
    await expect(dialog).toBeVisible();
    await dialog.getByPlaceholder(/tag name/i).fill(tagName);
    await dialog.getByRole("button", { name: /^add tag$/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });

    // The new tag should appear inside the Food category card. Categories
    // are accordions — expand if collapsed. Click the heading (left zone)
    // to expand, not the row center which hits the action-button zone.
    if (!(await page.getByText(tagName).isVisible().catch(() => false))) {
      await foodHeading.click();
    }
    await expect(page.getByText(tagName)).toBeVisible({ timeout: 10_000 });
  });
});
