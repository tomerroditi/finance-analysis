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

    await expect(page.locator("table tbody tr").first()).toBeVisible({
      timeout: 10_000,
    });

    // Select three demo transactions from DISTINCT merchants that match no
    // existing rule (see scripts/generate_demo_data.py rule-free untagged
    // entries). Each distinct description becomes its own OR branch, so this
    // drives the Add-Rule path deterministically.
    //
    // The default page shows 10 date-sorted rows, so these specific rows may
    // not all be on page 1. Use the table search to surface each merchant in
    // turn and tick it — selection persists across filter changes (only the
    // page index resets).
    const search = page.getByRole("textbox", { name: /search/i }).first();
    const merchants = ["CASTRO FASHION", "FOX HOME", "STEIMATZKY BOOKS"];
    for (const merchant of merchants) {
      await search.fill(merchant);
      const row = page
        .locator("table tbody tr")
        .filter({ hasText: merchant })
        .first();
      await expect(row).toBeVisible({ timeout: 10_000 });
      await row.locator('input[type="checkbox"]').check();
    }
    await search.fill("");

    const bulkBar = page
      .locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8")
      .last();
    const ruleButton = bulkBar.getByRole("button", { name: /^Add Rule$/ });
    await expect(ruleButton).toBeVisible({ timeout: 5_000 });
    await expect(ruleButton).toBeEnabled();

    await ruleButton.click();
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();

    // The seeded rule is an OR with one `description contains` branch per
    // distinct description — three distinct merchants -> three filled
    // Value inputs.
    const valueInputs = modal.locator('input[placeholder="Value"]:visible');
    // Anchor the count before evaluateAll (which does not auto-wait) so the
    // read can't race the modal populating its three OR branches.
    await expect(valueInputs).toHaveCount(3);
    const filled = await valueInputs.evaluateAll((els) =>
      els
        .map((el) => (el as HTMLInputElement).value.trim())
        .filter((v) => v !== ""),
    );
    expect(filled.length).toBe(3);
    // Each seeded value is the FULL transaction description, verbatim.
    expect(filled).toEqual(
      expect.arrayContaining([
        "CASTRO FASHION TLV 8842",
        "FOX HOME RAANANA 1290",
        "STEIMATZKY BOOKS 553",
      ]),
    );

    // And the OR rule actually matches transactions (description is trivially a
    // substring of itself) — the live preview must be non-zero.
    await page.waitForResponse(
      (res) =>
        res.url().includes("/api/tagging-rules/rules/preview") &&
        res.request().method() === "POST",
    );
    const matchesLabel = modal.getByText(/\d+\s*matches/).first();
    await expect(matchesLabel).toBeVisible();
    const matchCount = parseInt(
      (await matchesLabel.textContent())?.match(/(\d+)/)?.[1] ?? "0",
      10,
    );
    expect(matchCount).toBeGreaterThan(0);
  });
});
