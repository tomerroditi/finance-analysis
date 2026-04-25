import { type Page, expect } from "@playwright/test";

/**
 * Open the Settings popup (sidebar Settings button) and toggle Demo Mode.
 * Used by both enable/disable helpers — Demo Mode lives inside the Settings
 * popup, not directly in the sidebar, so we must open the popup first.
 */
async function toggleDemoMode(page: Page, expectedAfter: "on" | "off") {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /^settings$/i }).click();
  const toggleRow = page.getByText(/^Demo Mode$/);
  await toggleRow.waitFor();
  // Read current state from background color of the inner switch indicator
  const isOn = await page.evaluate(() => {
    const labels = Array.from(document.querySelectorAll("*"));
    const row = labels.find((el) => el.textContent?.trim() === "Demo Mode");
    if (!row) return null;
    const switchEl = row.parentElement?.querySelector('[class*="amber"]');
    return !!switchEl;
  });
  if ((expectedAfter === "on" && !isOn) || (expectedAfter === "off" && isOn)) {
    await toggleRow.click();
  }
  // Click somewhere else to dismiss the settings popup, then wait for reload.
  await page.keyboard.press("Escape");
  await page.waitForLoadState("networkidle");
}

/**
 * Enable Demo Mode via the Settings popup. Must be called at the start of
 * each test suite to ensure tests run against the demo database.
 */
export async function enableDemoMode(page: Page) {
  await toggleDemoMode(page, "on");
}

/**
 * Disable Demo Mode after tests complete.
 */
export async function disableDemoMode(page: Page) {
  await toggleDemoMode(page, "off");
}

/**
 * Navigate to a page and wait for it to load.
 */
export async function navigateTo(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

/**
 * Assert that a page's title heading is visible.
 */
export async function expectPageTitle(page: Page, title: string | RegExp) {
  await expect(page.getByRole("heading", { level: 1 }).filter({ hasText: title })).toBeVisible({
    timeout: 10_000,
  });
}
