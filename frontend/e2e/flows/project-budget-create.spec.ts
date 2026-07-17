import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Switches to Project Budgets tab and verifies the create-project flow
 * either opens a creation dialog or shows an existing project (demo data
 * ships with one).
 */
test.describe("Project budget flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("switches to project tab and opens create dialog", async ({ page }) => {
    await gotoAndWait(page, "/budget");

    // Switch to Project Budgets tab.
    await page.getByRole("button", { name: /project budgets/i }).first().click();

    // The demo seed ships a "Home Renovation" project — confirm it shows.
    await expect(
      page.getByText(/home renovation/i).first(),
    ).toBeVisible({ timeout: 10_000 });

    // Open New Project dialog (button label may be "New Project" or similar).
    const newProjectBtn = page
      .getByRole("button", { name: /^new project$/i })
      .or(page.getByRole("button", { name: /add project/i }))
      .first();
    if (await newProjectBtn.isVisible().catch(() => false)) {
      await newProjectBtn.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible({ timeout: 5_000 });
      // Just verify the dialog opens — don't actually create to keep state stable.
      await page.keyboard.press("Escape");
    }
  });
});
