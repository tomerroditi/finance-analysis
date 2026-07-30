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

  // All three scenarios are client-side reads/edits against one rendered
  // page, so they share a single navigation — the page load (and its
  // status/goal queries) is the expensive step.
  test("snapshot fields pre-populate, computed cards are read-only, and edits show a reset button", async ({
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

    // The "auto-calculated" label appears twice (once for each computed
    // card: Monthly Savings and Savings Rate — read-only display).
    const computedLabels = page.getByText("auto-calculated");
    await expect(computedLabels).toHaveCount(2);

    // Exactly one reset button is visible initially: the demo goal ships
    // with an Avg Monthly Expenses override (steady-state spending without
    // the wedding/renovation arcs), so that field differs from calculated.
    const resetBtns = page.locator("button[title='Reset to calculated']");
    await expect(resetBtns).toHaveCount(1);

    // Change the Net Worth value (first snapshot input — not overridden)
    const netWorthInput = page
      .locator(".p-3.rounded-xl input[type='number']")
      .first();
    const originalValue = await netWorthInput.inputValue();
    await netWorthInput.fill("999999");
    await netWorthInput.press("Tab");

    // A second reset button appears; Net Worth's card comes first in the
    // grid, so its reset button is the first one.
    await expect(resetBtns).toHaveCount(2);

    // Click reset — value should revert
    await resetBtns.first().click();
    await expect(netWorthInput).toHaveValue(originalValue);

    // Back to just the shipped expenses-override reset button
    await expect(resetBtns).toHaveCount(1);
  });

  test("modified snapshot fields are sent when saving the plan", async ({
    page,
  }) => {
    await navigateTo(page, "/early-retirement");

    const netWorthInput = page
      .locator(".p-3.rounded-xl input[type='number']")
      .first();
    // Anchor on the calculated status having pre-populated the field before
    // typing. Filling inside the pre-populate window is racy — the form is
    // still syncing from the status/goal queries, so the typed value can be
    // lost or Save Plan can stay disabled, and the save request never fires
    // (surfaces as a waitForResponse timeout under CPU load).
    await expect
      .poll(async () => Number(await netWorthInput.inputValue()), { timeout: 30_000 })
      .toBeGreaterThan(0);

    // Set a custom net worth
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
    // Untouched snapshot fields must save as null, NOT as frozen copies of
    // today's calculated values — the old behavior pinned net worth/income/
    // expenses at save-day numbers and the plan stopped tracking real data.
    expect(body.monthly_income).toBeNull();
    expect(body.total_investments_override).toBeNull();
    // The demo goal's stored expenses override (steady-state spending,
    // differs from calculated) survives the save untouched.
    expect(body.monthly_expenses_override).toBe(22000);
  });
});
