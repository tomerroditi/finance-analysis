import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Regression coverage for SplitTransactionModal.tsx.
 *
 * Split rows are keyed by a stable, monotonic id (`makeSplitId()`), not the
 * array index. Before that fix, removing a middle row reused the removed
 * row's index as the React key, so the inputs below it kept their old DOM
 * nodes and showed the wrong amounts. This drives the exact repro: open the
 * modal, add rows, give each a distinct amount, remove a middle row, and
 * assert the surviving rows still carry their own values.
 */
test.describe("Split transaction modal stable keys", () => {
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

  test("removing a middle row keeps the remaining rows' amounts intact", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for the table to populate.
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await page.waitForLoadState("networkidle");

    // The split action button carries title="Split transaction"
    // (t("tooltips.splitTransaction")). Open the modal for the first row.
    const splitButton = page
      .locator('table tbody button[title="Split transaction"]')
      .first();
    await expect(splitButton).toBeVisible({ timeout: 10_000 });
    await splitButton.click();

    // Modal heading confirms it opened.
    await expect(page.getByRole("heading", { name: /Split Transaction/i })).toBeVisible();

    // The modal seeds two rows. Each row's amount input is the only
    // number input inside that row block. Add two more rows so we have four.
    const addSplit = page.getByRole("button", { name: /Add Split/i });
    const amountInputs = page.locator('input[type="number"]');

    await expect(amountInputs).toHaveCount(2);
    await addSplit.click();
    await addSplit.click();
    await expect(amountInputs).toHaveCount(4);

    // Give each row a distinct, recognisable amount so we can detect a
    // value bleeding into the wrong row after removal.
    const values = ["11", "22", "33", "44"];
    for (let i = 0; i < values.length; i++) {
      await amountInputs.nth(i).fill(values[i]);
    }
    for (let i = 0; i < values.length; i++) {
      await expect(amountInputs.nth(i)).toHaveValue(values[i]);
    }

    // Remove the middle row (index 1, value "22"). Each row has its own
    // delete button (aria-label = t("common.delete")) inside the modal body.
    const deleteButtons = page
      .getByRole("dialog")
      .getByRole("button", { name: /Delete/i });
    await deleteButtons.nth(1).click();

    // Three rows remain. The bug would have shifted/duplicated values; with
    // stable keys the surviving rows keep their own amounts: 11, 33, 44.
    await expect(amountInputs).toHaveCount(3);
    await expect(amountInputs.nth(0)).toHaveValue("11");
    await expect(amountInputs.nth(1)).toHaveValue("33");
    await expect(amountInputs.nth(2)).toHaveValue("44");

    // "22" must no longer appear in any amount input.
    const remaining = await amountInputs.evaluateAll((els) =>
      (els as HTMLInputElement[]).map((el) => el.value),
    );
    expect(remaining).not.toContain("22");
    expect(remaining).toEqual(["11", "33", "44"]);
  });
});
