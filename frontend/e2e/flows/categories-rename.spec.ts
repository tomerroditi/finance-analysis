import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Renames the Food category via the panel's click-to-rename heading, verifies
 * the PUT /api/tagging/categories/{name} endpoint is called with the correct
 * payload, and confirms the new name appears in the UI.
 * Renames back to "Food" for cleanup, then adds a new tag to Food (formerly
 * flows/categories-add-tag.spec.ts) — both mutations share one page load.
 */
test.describe("Categories rename + add-tag flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("renames a category via the panel, then adds a new tag to it", async ({ page }) => {
    // The backend's rename endpoint runs the new name through `to_title_case`,
    // which capitalizes each hyphen-separated segment (e.g. "e2e-cat-123" →
    // "E2e-Cat-123"). The DOM/data-testid reflect the stored (transformed)
    // name, not the input — so we track both. See backend/utils/text_utils.py.
    const timestamp = Date.now();
    const inputName = `e2e-cat-${timestamp}`;
    const storedName = `E2e-Cat-${timestamp}`;
    await gotoAndWait(page, "/categories");

    // Click the Food card to open the detail panel.
    const foodCard = page.locator('[data-testid="category-card-Food"]');
    await expect(foodCard).toBeVisible();
    await foodCard.click();

    // Wait for the panel to appear.
    const panel = page.locator('[data-testid="category-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // Click the category name h2 to enter inline rename mode.
    const panelHeading = panel.getByRole("heading", { name: /^food$/i });
    await expect(panelHeading).toBeVisible();
    await panelHeading.click();

    const renameInput = panel.locator("input:focus");
    await expect(renameInput).toBeVisible({ timeout: 3_000 });

    // Fill the new name and press Enter; intercept the PUT to verify payload + status.
    await renameInput.fill(inputName);

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          /\/api\/tagging\/categories\//.test(r.url()) &&
          r.request().method() === "PUT",
        { timeout: 10_000 },
      ),
      renameInput.press("Enter"),
    ]);

    expect(response.status(), "PUT /api/tagging/categories/{name} should return 200").toBe(200);

    const body = response.request().postDataJSON() as { new_name: string };
    expect(body.new_name).toBe(inputName);

    // Panel heading updates immediately to the new name (case-insensitive
    // because the panel renders the stored, title-cased version).
    await expect(panel.getByRole("heading", { name: new RegExp(`^${storedName}$`, "i") })).toBeVisible({ timeout: 5_000 });

    // Close the panel so the grid is unobscured.
    await panel.getByRole("button", { name: /^close$/i }).click();
    await expect(panel).toBeHidden({ timeout: 3_000 });

    // Poll the DOM for the renamed card. The mutation triggers a per-key
    // invalidation plus a 200ms-debounced global invalidation in
    // queryClient.ts; either should refetch the categories list. A direct
    // DOM poll is more reliable than waitForResponse with body inspection,
    // which has timing issues when reading r.json() inside the predicate.
    await expect(page.getByTestId(`category-card-${storedName}`)).toBeVisible({ timeout: 30_000 });

    // Cleanup: open the panel for the renamed category and rename back to "Food".
    await page.locator(`[data-testid="category-card-${storedName}"]`).click();
    const renamedPanel = page.locator('[data-testid="category-panel"]');
    await expect(renamedPanel).toBeVisible({ timeout: 5_000 });
    const renamedHeading = renamedPanel.getByRole("heading", { name: new RegExp(`^${storedName}$`, "i") });
    await renamedHeading.click();
    const cleanupInput = renamedPanel.locator("input:focus");
    await cleanupInput.fill("Food");

    await Promise.all([
      page.waitForResponse(
        (r) =>
          /\/api\/tagging\/categories\//.test(r.url()) &&
          r.request().method() === "PUT",
        { timeout: 10_000 },
      ),
      cleanupInput.press("Enter"),
    ]);

    // Panel heading updates to "Food" immediately.
    await expect(renamedPanel.getByRole("heading", { name: /^food$/i })).toBeVisible({ timeout: 5_000 });

    await renamedPanel.getByRole("button", { name: /^close$/i }).click();
    await expect(renamedPanel).toBeHidden({ timeout: 3_000 });
    await expect(page.getByTestId("category-card-Food")).toBeVisible({ timeout: 30_000 });

    // ---- Add a new tag to the (restored) Food category ----
    const tagName = `e2e-tag-${timestamp}`;
    await page.getByTestId("category-card-Food").click();

    const tagPanel = page.locator('[data-testid="category-panel"]');
    await expect(tagPanel).toBeVisible({ timeout: 5_000 });

    // Click the "Add Tag" button inside the panel.
    const addTagBtn = tagPanel.locator('button[title="Add Tag"]').first();
    await expect(addTagBtn).toBeVisible({ timeout: 5_000 });
    await addTagBtn.click();

    // Fill the tag name field in the modal.
    const addTagDialog = page.getByRole("dialog", { name: /add tag to food/i });
    await expect(addTagDialog).toBeVisible();
    await addTagDialog.getByPlaceholder(/tag name/i).fill(tagName);
    await addTagDialog.getByRole("button", { name: /^add tag$/i }).click();
    await expect(addTagDialog).toBeHidden({ timeout: 10_000 });

    // The new tag should appear inside the panel.
    await expect(tagPanel.getByText(tagName)).toBeVisible({ timeout: 10_000 });
  });
});
