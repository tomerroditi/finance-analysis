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
    await page.getByRole("spinbutton").last().fill("12345");

    // Footer Save button.
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(modalHeading).toBeHidden({ timeout: 10_000 });
  });
});
