import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Renames the Food category via the click-to-rename inline editor,
 * verifies the PUT /api/tagging/categories/{name} endpoint is called with
 * the correct payload, and confirms the new name appears in the UI.
 * Renames back to "Food" for cleanup.
 */
test.describe("Categories rename flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("renames a category by clicking its name and submitting", async ({ page }) => {
    const newName = `e2e-cat-${Date.now()}`;
    await gotoAndWait(page, "/categories");

    // Locate the Food heading.
    const foodHeading = page.getByRole("heading", { name: /^food$/i });
    await expect(foodHeading).toBeVisible();

    // Clicking the name opens the inline rename input (h3 replaced by autoFocus input).
    await foodHeading.click();
    const renameInput = page.locator("input:focus");
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

    // Verify the payload sent the correct new_name.
    const body = response.request().postDataJSON() as { new_name: string };
    expect(body.new_name).toBe(newName);

    // The new name should be visible in the UI.
    await expect(page.getByRole("heading", { name: newName })).toBeVisible({
      timeout: 5_000,
    });

    // Cleanup: rename back to "Food".
    await page.getByRole("heading", { name: newName }).click();
    const cleanupInput = page.locator("input:focus");
    await cleanupInput.fill("Food");
    await cleanupInput.press("Enter");
    await page.waitForResponse(
      (r) =>
        /\/api\/tagging\/categories\//.test(r.url()) &&
        r.request().method() === "PUT",
      { timeout: 10_000 },
    );
    await expect(page.getByRole("heading", { name: /^food$/i })).toBeVisible({
      timeout: 5_000,
    });
  });
});
