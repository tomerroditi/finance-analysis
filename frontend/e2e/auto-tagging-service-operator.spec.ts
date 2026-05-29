import { test, expect, type Page } from "@playwright/test";
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
 * The rule editor renders the condition form in two layout variants (mobile +
 * desktop), only one visible at a time, so every interactive locator is
 * intersected with `:visible`. (Playwright 1.49 predates `filter({visible})`.)
 */

const visible = (page: Page, locator: ReturnType<Page["getByRole"]>) =>
  locator.and(page.locator(":visible"));

test.describe("Auto-tagging: service operator restriction + apply toast", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test.afterAll(async () => {
    await disableDemoMode();
  });

  test("service field exposes only the Equals operator", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await page.getByRole("button", { name: /new rule/i }).first().click();

    // Wait for the rule editor to mount (its heading mentions "rule").
    await page.getByRole("heading", { name: /rule/i }).first().waitFor();

    // The first condition row defaults to field=Description, operator=Contains.
    // Switch the visible field dropdown to "Service".
    await visible(page, page.getByRole("button", { name: /^description$/i }))
      .first()
      .click();
    await visible(page, page.getByRole("option", { name: /^service$/i }))
      .first()
      .click();

    // After selecting Service, the operator must reset to "Equals" — the only
    // operator the backend honors for the service field.
    const operatorTrigger = visible(
      page,
      page.getByRole("button", { name: /^equals$/i }),
    ).first();
    await expect(operatorTrigger).toBeVisible();

    // The operator dropdown must offer exactly one option: Equals. The old
    // behavior also exposed contains / starts_with / ends_with.
    await operatorTrigger.click();
    const options = visible(page, page.getByRole("option"));
    await expect(options).toHaveCount(1);
    await expect(options.first()).toHaveText(/equals/i);

    await page.keyboard.press("Escape");
  });

  test("applying all rules surfaces a localized success toast", async ({ page }) => {
    await navigateTo(page, "/transactions");

    await page.getByRole("button", { name: /apply rules/i }).first().click();

    // The success toast goes through i18n: "Applied rules! N tagged." It must
    // render real copy, never the raw key path.
    await expect(page.getByText(/applied rules!/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/transactions\.autoTagging\./i)).toHaveCount(0);
  });
});
