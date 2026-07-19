import { test, expect } from "@playwright/test";
import { navigateTo, enableDemoMode, disableDemoMode } from "./helpers";

/**
 * E2E coverage for the auto-tagging rules manager + rule editor, consolidated
 * onto as few (expensive) page loads as possible:
 *
 *  1. Rule management lives in a full-screen manager opened from the
 *     "Auto-Tagging Rules" launcher on the Categories page (not a cramped
 *     inline section).
 *  2. A new rule's conditions group (and any nested group) defaults to OR.
 *  3. The editor's matching-transactions preview is not capped at 50 rows.
 *  4. The `service` rule-condition field used to offer text operators
 *     (contains, starts_with, ends_with) that the backend silently ignores —
 *     it only honors `service` with `equals`. The field is now restricted to a
 *     single `equals` operator and defaults to it on selection.
 *  5. The apply-rules success message goes through i18n with a {{count}}
 *     interpolation — the flow must surface a localized toast with no raw
 *     translation-key leak.
 *
 * The rule editor renders the condition form in two layout variants
 * (mobile + desktop), so option locators are filtered to the visible one.
 */

test.describe("Auto-tagging rules manager + editor", () => {
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

  test("manager opens full-screen; editor defaults to OR, previews uncapped, restricts the service operator", async ({
    page,
  }) => {
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

    // Top-level conditions group defaults to "OR (Any match)".
    await expect(
      modal.getByRole("button", { name: /OR \(Any match\)/i }).first(),
    ).toBeVisible({ timeout: 5_000 });

    // --- Preview is not capped at 50 ---
    // Pick the visible Value input (there can be a duplicate hidden one for
    // the mobile layout) and type a merchant with many demo transactions.
    const valueInput = modal.locator('input[placeholder="Value"]:visible').first();
    await expect(valueInput).toBeVisible();
    await valueInput.fill("WOLT");

    // Debounce in the modal is 300ms; wait for the preview query.
    await page.waitForResponse(
      (res) =>
        res.url().includes("/api/tagging-rules/rules/preview") &&
        res.request().method() === "POST",
    );

    // The matches count and the rendered row count should both exceed 50,
    // proving the previous 50-row cap is gone.
    const matchesLabel = modal.getByText(/\d+\s*matches/).first();
    await expect(matchesLabel).toBeVisible();
    const labelText = await matchesLabel.textContent();
    const matchCount = parseInt(labelText?.match(/(\d+)/)?.[1] ?? "0", 10);
    expect(matchCount).toBeGreaterThan(50);

    // The modal's preview table should render every match.
    const previewRows = modal.locator("table tbody tr");
    await expect(previewRows).toHaveCount(matchCount);

    // --- Adding a nested group also defaults to OR (consistency) ---
    await modal.getByRole("button", { name: /^\+ Group$|^Group$/ }).first().click();
    await expect(
      modal.getByRole("button", { name: /OR \(Any match\)/i }),
    ).toHaveCount(2, { timeout: 5_000 });

    // --- Service field exposes only the Equals operator ---
    // The first condition row defaults to field=Description, operator=Contains.
    // Switch the field dropdown to "Service".
    await modal.getByRole("button", { name: /^Description$/ }).first().click();
    await page
      .getByRole("option", { name: /^Service$/ })
      .filter({ visible: true })
      .first()
      .click();

    // After selecting Service, the operator must reset to "Equals" — the only
    // operator the backend honors for the service field.
    const operatorTrigger = modal
      .getByRole("button", { name: /^Equals$/ })
      .first();
    await expect(operatorTrigger).toBeVisible();

    // The operator dropdown must offer exactly one option: Equals. The old
    // behavior also exposed contains / starts_with / ends_with.
    await operatorTrigger.click();
    const options = page.getByRole("option").filter({ visible: true });
    await expect(options).toHaveCount(1);
    await expect(options.first()).toHaveText(/Equals/);

    await page.keyboard.press("Escape");
  });

  test("applying all rules surfaces a localized success toast", async ({ page }) => {
    await navigateTo(page, "/categories");

    // Open the rules manager, then apply all rules.
    await page.getByRole("button", { name: /Auto-Tagging Rules/i }).click();
    await page.getByRole("button", { name: /^Apply Rules$/ }).click();

    // The success toast goes through i18n: "Applied rules! N tagged." It must
    // render real copy, never the raw key path.
    await expect(page.getByText(/Applied rules!/).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/transactions\.autoTagging\./)).toHaveCount(0);
  });
});
