import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Renames the Food category via the panel's click-to-rename heading, verifies
 * the PUT /api/tagging/categories/{name} endpoint is called with the correct
 * payload, and confirms the new name appears in the UI.
 * Renames back to "Food" for cleanup.
 */
test.describe("Categories rename flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("renames a category by opening the panel and clicking its name", async ({ page }) => {
    const newName = `e2e-cat-${Date.now()}`;
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
    await renameInput.fill(newName);
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
    expect(body.new_name).toBe(newName);

    // Panel heading updates immediately to the new name (before grid refetches).
    await expect(panel.getByRole("heading", { name: new RegExp(`^${newName}$`, "i") })).toBeVisible({ timeout: 5_000 });

    // Close the panel so the grid is unobscured.
    await panel.getByRole("button", { name: /^close$/i }).click();
    await expect(panel).toBeHidden({ timeout: 3_000 });

    // The grid card should now show the new category name.
    await expect(page.getByTestId(`category-card-${newName}`)).toBeVisible({ timeout: 10_000 });

    // Cleanup: open the panel for the renamed category and rename back to "Food".
    await page.locator(`[data-testid="category-card-${newName}"]`).click();
    const renamedPanel = page.locator('[data-testid="category-panel"]');
    await expect(renamedPanel).toBeVisible({ timeout: 5_000 });
    const renamedHeading = renamedPanel.getByRole("heading", { name: new RegExp(`^${newName}$`, "i") });
    await renamedHeading.click();
    const cleanupInput = renamedPanel.locator("input:focus");
    await cleanupInput.fill("Food");
    await cleanupInput.press("Enter");
    await page.waitForResponse(
      (r) =>
        /\/api\/tagging\/categories\//.test(r.url()) &&
        r.request().method() === "PUT",
      { timeout: 10_000 },
    );

    // Panel heading updates immediately; close it before checking the grid.
    await expect(renamedPanel.getByRole("heading", { name: /^food$/i })).toBeVisible({ timeout: 5_000 });
    await renamedPanel.getByRole("button", { name: /^close$/i }).click();
    await expect(renamedPanel).toBeHidden({ timeout: 3_000 });
    await expect(page.getByTestId("category-card-Food")).toBeVisible({ timeout: 10_000 });
  });
});
