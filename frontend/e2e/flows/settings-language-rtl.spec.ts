import { test, expect } from "@playwright/test";
import { gotoAndWait } from "./_helpers";
import { enableDemoMode, resetDemoData } from "../helpers";

/**
 * Switches the UI language between English and Hebrew via the Settings
 * popup and verifies that the document direction flips to RTL.
 *
 * Demo Mode is seeded per-page via `enableDemoMode` in `beforeEach` rather
 * than a `beforeAll` — the flag lives in the test's own browser context
 * (localStorage), which doesn't exist yet in `beforeAll` (no `page`
 * fixture there), and wouldn't carry over from a separately-created page
 * even if it did.
 */
test.describe("Settings language toggle flow", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("switching to Hebrew flips document direction to RTL", async ({
    page,
  }) => {
    await gotoAndWait(page, "/");

    // Sanity: starts as LTR.
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

    // The Settings button label flips between languages, so target the
    // lucide-settings icon's parent button — language-agnostic selector.
    // Two such buttons exist (sidebar + mobile top bar); pick the visible one.
    const settingsButton = page
      .locator("button:has(svg.lucide-settings)")
      .filter({ visible: true })
      .first();

    await settingsButton.click();
    await page.getByText("עברית").click();
    await page.keyboard.press("Escape");

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl", {
      timeout: 5_000,
    });

    // Cleanup: switch back to English.
    await settingsButton.click();
    await page
      .getByText(/^English$/i)
      .first()
      .click();
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr", {
      timeout: 5_000,
    });
  });
});
