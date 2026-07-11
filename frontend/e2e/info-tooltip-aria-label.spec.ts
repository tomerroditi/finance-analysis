import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";
/**
 * Regression coverage for InfoTooltip.tsx.
 *
 * The info button's accessible name must come from i18n
 * (`aria-label={t("common.moreInfo")}`), not a hardcoded English string, so
 * it localizes with the rest of the UI. Demo investments carry `notes`
 * (e.g. "Tracking S&P 500 index fund"), which is exactly when the Investments
 * page renders the shared InfoTooltip. We assert the accessible name in both
 * English and Hebrew.
 *
 * en.json common.moreInfo = "More info"
 * he.json common.moreInfo = "מידע נוסף"
 */
test.describe("InfoTooltip aria-label i18n", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test.afterEach(async ({ page }) => {
    if (page.url().startsWith("http")) {
      await page.evaluate(() => localStorage.setItem("language", "en"));
    }
  });

  test("info button exposes the localized 'More info' accessible name in English", async ({
    page,
  }) => {
    await page.evaluate(() => localStorage.setItem("language", "en")).catch(() => {});
    await navigateTo(page, "/investments");

    const infoButton = page.getByRole("button", { name: "More info" }).first();
    await expect(infoButton).toBeVisible({ timeout: 30_000 });

    // The accessible name must be the i18n value, never empty / a key leak
    // like "common.moreInfo".
    await expect(infoButton).toHaveAttribute("aria-label", "More info");
  });

  test("info button localizes the accessible name to Hebrew", async ({ page }) => {
    await navigateTo(page, "/investments");
    await page.evaluate(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/investments");

    // Document direction flips to RTL once Hebrew is active — confirms the
    // language actually switched before we assert on the localized label.
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const infoButton = page.getByRole("button", { name: "מידע נוסף" }).first();
    await expect(infoButton).toBeVisible({ timeout: 30_000 });
    await expect(infoButton).toHaveAttribute("aria-label", "מידע נוסף");

    // The English label must be gone — proving the aria-label is driven by
    // i18n and not hardcoded.
    await expect(page.getByRole("button", { name: "More info" })).toHaveCount(0);
  });
});
