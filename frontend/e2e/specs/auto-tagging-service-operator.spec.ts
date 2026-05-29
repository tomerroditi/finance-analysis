import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, gotoPage } from "../helpers";

/**
 * E2E spec for the rule-builder service-field operator restriction and the
 * auto-tagging apply-rules toast.
 *
 * Regression coverage for two fixes:
 *  1. The `service` field used to offer text operators (contains, starts_with,
 *     ends_with) that the backend silently ignores — it only honors `service`
 *     with `equals`. The field is now restricted to a single `equals` operator
 *     and defaults to it on selection.
 *  2. The apply-rules success message was hardcoded English; it now goes
 *     through i18n with a {{count}} interpolation. We assert the apply-rules
 *     flow surfaces a localized success toast with no raw translation-key leak.
 *
 * The rule editor renders the condition form in more than one layout variant
 * (only one is visible at the desktop viewport), so every locator is scoped to
 * the dialog and filtered to the visible element.
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
    await gotoPage(page, "/transactions");
    await page.getByRole("button", { name: /new rule/i }).first().click();

    const dialog = page.getByRole("dialog");

    // The first condition row defaults to field=Description, operator=contains.
    // Switch the visible field dropdown to "Service".
    await dialog
      .getByRole("button", { name: /^description$/i })
      .filter({ visible: true })
      .first()
      .click();
    await page
      .getByRole("option", { name: /^service$/i })
      .filter({ visible: true })
      .first()
      .click();

    // After selecting Service, the operator must reset to "Equals" (the only
    // operator the backend honors for the service field).
    const operatorTrigger = dialog
      .getByRole("button", { name: /^equals$/i })
      .filter({ visible: true })
      .first();
    await expect(operatorTrigger).toBeVisible();

    // The operator dropdown must offer exactly one option: Equals. The old
    // behavior exposed contains/starts_with/ends_with too.
    await operatorTrigger.click();
    const options = page.getByRole("option").filter({ visible: true });
    await expect(options).toHaveCount(1);
    await expect(options.first()).toHaveText(/equals/i);

    await page.keyboard.press("Escape");
  });

  test("applying all rules surfaces a localized success toast", async ({ page }) => {
    await gotoPage(page, "/transactions");

    await page.getByRole("button", { name: /apply rules/i }).first().click();

    // The success toast goes through i18n: "Applied rules! N tagged." It must
    // render real copy, never the raw key path.
    await expect(page.getByText(/applied rules!/i).first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/transactions\.autoTagging\./i)).toHaveCount(0);
  });
});
