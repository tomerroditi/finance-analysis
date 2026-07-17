import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Retirement page — editable Current Financial Status snapshot fields.
 *
 * The 6 "Current Financial Status" cards are editable number inputs
 * pre-populated from the backend's calculated status. Monthly Savings and
 * Savings Rate are computed/read-only; the other 4 (Net Worth, Avg Monthly
 * Income, Avg Monthly Expenses, Total Investments) are editable with a
 * reset button that appears when the value differs from the calculated one.
 */
test.describe("Retirement snapshot fields", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test("snapshot section is visible and pre-populated with non-zero values", async ({
    page,
  }) => {
    await navigateTo(page, "/early-retirement");
    await page.waitForLoadState("networkidle");

    // The CURRENT FINANCIAL STATUS header should be visible
    await expect(
      page.getByText("CURRENT FINANCIAL STATUS"),
    ).toBeVisible();

    // All 4 editable snapshot inputs should have non-zero values
    const snapshotInputs = page
      .locator(
        ".p-3.rounded-xl input[type='number']",
      )
      .filter({ visible: true });

    const count = await snapshotInputs.count();
    expect(count).toBeGreaterThanOrEqual(4);

    for (let i = 0; i < Math.min(count, 4); i++) {
      const val = await snapshotInputs.nth(i).inputValue();
      expect(Number(val)).toBeGreaterThan(0);
    }
  });

  test("computed cards (Monthly Savings, Savings Rate) are read-only display", async ({
    page,
  }) => {
    await navigateTo(page, "/early-retirement");

    // The "auto-calculated" label appears twice (once for each computed card)
    const computedLabels = page.getByText("auto-calculated");
    await expect(computedLabels).toHaveCount(2);
  });

  test("editing a snapshot field shows the reset button", async ({ page }) => {
    await navigateTo(page, "/early-retirement");
    await page.waitForLoadState("networkidle");

    // No reset buttons should be visible initially (form = calculated values)
    const resetBtns = page.locator("button[title='Reset to calculated']");
    await expect(resetBtns).toHaveCount(0);

    // Change the Net Worth value (first snapshot input)
    const netWorthInput = page
      .locator(".p-3.rounded-xl input[type='number']")
      .first();
    const originalValue = await netWorthInput.inputValue();
    await netWorthInput.fill("999999");
    await netWorthInput.press("Tab");

    // Reset button should now appear for that field
    await expect(resetBtns.first()).toBeVisible();

    // Click reset — value should revert
    await resetBtns.first().click();
    await expect(netWorthInput).toHaveValue(originalValue);

    // Reset button should disappear again
    await expect(resetBtns).toHaveCount(0);
  });

  test("modified snapshot fields are sent when saving the plan", async ({
    page,
  }) => {
    await navigateTo(page, "/early-retirement");

    // Set a custom net worth
    const netWorthInput = page
      .locator(".p-3.rounded-xl input[type='number']")
      .first();
    await netWorthInput.fill("1234567");

    // Save plan and verify the API receives the override
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/retirement/goal") &&
          (r.request().method() === "POST" ||
            r.request().method() === "PUT"),
      ),
      page.getByRole("button", { name: /Save Plan/i }).click(),
    ]);

    expect(resp.ok()).toBeTruthy();
    const body = await resp.request().postDataJSON();
    expect(body.net_worth_override).toBe(1234567);
  });
});
