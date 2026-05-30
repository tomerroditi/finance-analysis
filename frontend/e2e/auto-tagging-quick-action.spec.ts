import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * E2E coverage for the auto-tagging refactor:
 *
 *  1. Rule management moved off the Transactions side panel into an
 *     "Auto-Tagging Rules" section on the Categories page.
 *  2. While marking transactions, the bulk actions bar surfaces an
 *     "Add Rule" / "View Rule" quick action. "Add Rule" opens the rule editor
 *     pre-filled with a description condition derived from the selection.
 */
test.describe("Auto-tagging quick action + Categories rules section", () => {
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

  test("Categories page hosts the Auto-Tagging Rules section", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // The launcher card opens the full-screen rules manager.
    await page.getByRole("button", { name: /Auto-Tagging Rules/i }).click();
    const manager = page.locator(
      '[role="dialog"][aria-labelledby="rules-manager-title"]',
    );
    await expect(manager).toBeVisible({ timeout: 10_000 });

    // It opens full-screen, not as a cramped inline section.
    const managerBox = await manager.boundingBox();
    expect(managerBox?.height ?? 0).toBeGreaterThan(500);

    // The "New Rule" button in the manager opens the rule editor.
    await manager.getByRole("button", { name: /^New Rule$/ }).click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();
  });

  test("bulk selection surfaces the Add/View rule quick action", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Credit-card transactions are rule-applicable, so the quick action shows.
    await page.getByRole("button", { name: /Credit Card/i }).click();
    await page.waitForLoadState("networkidle");

    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Select a single credit-card transaction to surface the bulk actions bar.
    await rows.first().locator('input[type="checkbox"]').check();

    const bulkBar = page
      .locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8")
      .last();
    await expect(bulkBar).toBeVisible({ timeout: 5_000 });

    const ruleButton = bulkBar.getByRole("button", { name: /Add Rule|View Rule/ });
    await expect(ruleButton).toBeVisible();

    const label = (await ruleButton.textContent())?.trim() ?? "";
    // A disabled button means the selection is ambiguous; nothing to open.
    if (await ruleButton.isDisabled()) return;

    await ruleButton.click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();

    // The editor must open full-screen, not shrink to the bulk bar's footprint.
    // (Regression guard: rendering it inside the backdrop-blurred bar trapped
    // its `fixed inset-0` to the bar; it now portals to <body>.)
    const dialogBox = await modal.getByRole("dialog").boundingBox();
    expect(dialogBox?.height ?? 0).toBeGreaterThan(500);

    if (/Add Rule/.test(label)) {
      // "Add Rule" pre-fills a description-contains condition from the
      // selected transaction. The seeded keyword is a VERBATIM substring of the
      // description (merchant prefix up to the first generic word / number), so
      // the rule must actually match at least the transaction it came from —
      // the previous cleaner mutated the text and matched nothing.
      const valueInput = modal
        .locator('input[placeholder="Value"]:visible')
        .first();
      await expect(valueInput).toBeVisible();
      await expect(valueInput).not.toHaveValue("");

      // The editor's live preview must report a non-zero match count.
      await page.waitForResponse(
        (res) =>
          res.url().includes("/api/tagging-rules/rules/preview") &&
          res.request().method() === "POST",
      );
      const matchesLabel = modal.getByText(/\d+\s*matches/).first();
      await expect(matchesLabel).toBeVisible();
      const labelText = await matchesLabel.textContent();
      const matchCount = parseInt(labelText?.match(/(\d+)/)?.[1] ?? "0", 10);
      expect(matchCount).toBeGreaterThan(0);
    }
  });

  test("Add Rule from a multi-merchant selection OR-chains description conditions", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Restrict to credit-card transactions so the selection is rule-applicable.
    await page.getByRole("button", { name: /Credit Card/i }).click();
    await page.waitForLoadState("networkidle");

    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    const rowCount = await rows.count();
    test.skip(rowCount < 3, "needs at least 3 transactions to test OR-chaining");

    // Select several transactions; distinct merchants yield distinct keywords.
    const toSelect = Math.min(rowCount, 6);
    for (let i = 0; i < toSelect; i++) {
      await rows.nth(i).locator('input[type="checkbox"]').check();
    }

    const bulkBar = page
      .locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8")
      .last();
    const ruleButton = bulkBar.getByRole("button", { name: /Add Rule|View Rule/ });
    await expect(ruleButton).toBeVisible({ timeout: 5_000 });

    // Only meaningful when the selection has no existing rules (Add Rule path).
    test.skip(
      await ruleButton.isDisabled(),
      "ambiguous selection — not the Add Rule path",
    );
    const label = (await ruleButton.textContent())?.trim() ?? "";
    test.skip(!/Add Rule/.test(label), "selection already matches a rule");

    await ruleButton.click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();

    // The seeded rule is an OR with one `description contains` branch per
    // distinct merchant keyword. With multiple distinct merchants selected,
    // there should be more than one Value input pre-filled.
    const valueInputs = modal.locator('input[placeholder="Value"]:visible');
    const filled = await valueInputs.evaluateAll((els) =>
      els.filter((el) => (el as HTMLInputElement).value.trim() !== "").length,
    );
    expect(filled).toBeGreaterThan(1);
  });
});
