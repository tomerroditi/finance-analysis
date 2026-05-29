import { test, expect } from "@playwright/test";
import { navigateTo, enableDemoMode, disableDemoMode } from "./helpers";

/**
 * E2E coverage for two auto-tagging fixes:
 *
 *  1. The `service` rule-condition field used to offer text operators
 *     (contains, starts_with, ends_with) that the backend silently ignores —
 *     it only honors `service` with `equals`. The field is now restricted to a
 *     single `equals` operator and defaults to it on selection.
 *  2. The apply-rules success message was hardcoded English; it now goes
 *     through i18n with a {{count}} interpolation. We assert the apply-rules
 *     flow surfaces a localized success toast with no raw translation-key leak.
 *
 * The "New Rule" / "Apply Rules" buttons live inside the Auto Tagging side
 * panel, which is collapsed by default — open it first (same pattern as
 * rule-editor-preview.spec.ts). The rule editor renders the condition form in
 * two layout variants (mobile + desktop), so option locators are filtered to
 * the visible one.
 */

test.describe("Auto-tagging: service operator restriction + apply toast", () => {
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

  test("service field exposes only the Equals operator", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await page.waitForLoadState("networkidle");

    // Open the Auto Tagging panel, then open the rule editor.
    await page.getByRole("button", { name: /^Auto Tagging$/ }).click();
    await page.getByRole("button", { name: /^New Rule$/ }).click();

    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();

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
    await navigateTo(page, "/transactions");
    await page.waitForLoadState("networkidle");

    // Open the Auto Tagging panel, then apply all rules.
    await page.getByRole("button", { name: /^Auto Tagging$/ }).click();
    await page.getByRole("button", { name: /^Apply Rules$/ }).click();

    // The success toast goes through i18n: "Applied rules! N tagged." It must
    // render real copy, never the raw key path.
    await expect(page.getByText(/Applied rules!/).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/transactions\.autoTagging\./)).toHaveCount(0);
  });
});
