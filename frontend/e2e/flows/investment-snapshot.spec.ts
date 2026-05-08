import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Adds a balance snapshot to one of the demo investments by opening its
 * detail card and submitting the snapshot form.
 */
test.describe("Investment balance snapshot flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("opens the Update Balance modal for an active investment", async ({ page }) => {
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
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: /^save$/i }).click(),
    ]);
    expect(response.status()).toBe(200);
    await expect(modalHeading).toBeHidden({ timeout: 5_000 });
  });
});
