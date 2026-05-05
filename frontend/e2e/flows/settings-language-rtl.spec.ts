import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Switches the UI language between English and Hebrew via the Settings
 * popup and verifies that the document direction flips to RTL.
 */
test.describe("Settings language toggle flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("switching to Hebrew flips document direction to RTL", async ({ page }) => {
    await gotoAndWait(page, "/");

    // Sanity: starts as LTR.
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

    // The Settings button label flips between languages, so target the
    // lucide-settings icon's parent button — language-agnostic selector.
    const settingsButton = page.locator("button:has(svg.lucide-settings)").first();

    await settingsButton.click();
    await page.getByText("עברית").click();
    await page.keyboard.press("Escape");

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl", {
      timeout: 5_000,
    });

    // Cleanup: switch back to English.
    await settingsButton.click();
    await page.getByText(/^English$/i).first().click();
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr", {
      timeout: 5_000,
    });
  });
});
