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

    // Find the Food category card and expand it — Add Tag is now only
    // available inside the expanded section, not in the header.
    const foodHeading = page.getByRole("heading", { name: /^food$/i });
    await expect(foodHeading).toBeVisible();
    const foodCard = foodHeading.locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");

    // Expand the card by clicking the heading.
    await foodHeading.click();

    // The inline "Add Tag" button appears in the expanded tag list.
    const addTagBtn = foodCard.locator('button[title="Add Tag"]').first();
    await expect(addTagBtn).toBeVisible({ timeout: 5_000 });
    await addTagBtn.click();

    // Fill the tag name field in the modal.
    const dialog = page.getByRole("dialog", { name: /add tag to food/i });
    await expect(dialog).toBeVisible();
    await dialog.getByPlaceholder(/tag name/i).fill(tagName);
    await dialog.getByRole("button", { name: /^add tag$/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });

    // The new tag should appear inside the expanded Food category card.
    await expect(page.getByText(tagName)).toBeVisible({ timeout: 10_000 });
  });
});
