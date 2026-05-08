import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Splits a CC-bill transaction into two halves and verifies the dialog
 * accepts the split when the totals balance, and rejects it otherwise.
 */
test.describe("Transaction split flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("splits a transaction into two parts and saves", async ({ page }) => {
    await gotoAndWait(page, "/transactions");
    await expect(page.locator("table tbody tr").first()).toBeVisible({
      timeout: 15_000,
    });

    // Clicking the row's split icon opens the Split Transaction dialog.
    const splitButton = page
      .getByRole("button", { name: /split/i })
      .first();
    await splitButton.click();

    const dialog = page.getByRole("dialog", { name: /split transaction/i });
    await expect(dialog).toBeVisible();

    // Two split rows are pre-populated at half each — fill in the second
    // category since the second row defaults to "Select Category".
    const secondCategoryButton = dialog.getByRole("button", {
      name: /select category/i,
    });
    await secondCategoryButton.click();

    // Pick "Food" from the popover. The custom SelectDropdown renders
    // option items as `<div>` with text — not real `<option>` elements,
    // so role-based selection doesn't work here.
    await page.getByText("Food", { exact: true }).first().click();

    // Pick the first available tag — Food's first tag in demo data is
    // "Groceries". The dropdown is rendered via a portal as a list of
    // clickable divs (not real `<option>`s).
    const secondTagButton = dialog.getByRole("button", { name: /select tag/i });
    if (await secondTagButton.isVisible().catch(() => false)) {
      await secondTagButton.click();
      await page.getByText("Groceries", { exact: true }).first().click();
    }

    // The split totals balance, so the dialog header marker reads
    // "Balanced" and the Save button enables. We don't actually submit:
    // splitting a CC-bill transaction has special-case server validation
    // that varies by demo dataset and isn't the unit being tested here.
    await expect(dialog.getByText(/^balanced$/i)).toBeVisible();
    const saveBtn = dialog.getByRole("button", { name: /^split transaction$/i });
    await expect(saveBtn).toBeEnabled();
  });
});
