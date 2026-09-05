import { test, expect } from "@playwright/test";
import { gotoAndWait } from "./_helpers";
import { enableDemoMode, resetDemoData } from "../helpers";

/**
 * Adds a balance snapshot to one of the demo investments by opening its
 * detail card and submitting the snapshot form.
 *
 * Demo Mode is seeded per-page via `enableDemoMode` in `beforeEach` rather
 * than a `beforeAll` — the flag lives in the test's own browser context
 * (localStorage), which doesn't exist yet in `beforeAll` (no `page`
 * fixture there), and wouldn't carry over from a separately-created page
 * even if it did.
 */
test.describe("Investment balance snapshot flow", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("opens the Update Balance modal for an active investment", async ({
    page,
  }) => {
    await gotoAndWait(page, "/investments");

    // Each active card has a circular "$" button (DollarSign icon) with
    // title="Update Balance". Use the title attribute to avoid matching
    // the heading text inside the modal that opens.
    const updateBtn = page.locator("button[title='Update Balance']").first();
    await expect(updateBtn).toBeVisible({ timeout: 15_000 });
    await updateBtn.scrollIntoViewIfNeeded();
    await updateBtn.click();

    // The Update Balance modal mounts with a heading and inputs.
    const modalHeading = page.getByRole("heading", {
      name: /^update balance$/i,
    });
    await expect(modalHeading).toBeVisible();

    // Fill the balance number input. Scope to input[type="number"] inside
    // the modal overlay to avoid matching any spinbuttons from the table.
    const balanceInput = page.locator(".modal-overlay input[type='number']");
    await balanceInput.fill("12345");

    // Wait for the API response to confirm the snapshot was saved, then
    // assert the modal closes. Using waitForResponse surfaces backend errors
    // immediately instead of timing out on toBeHidden.
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/balances") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /^save$/i }).click(),
    ]);
    expect(response.status()).toBe(200);
    await expect(modalHeading).toBeHidden({ timeout: 5_000 });
  });
});
