import { type Page, expect } from "@playwright/test";

/**
 * Enable Demo Mode via the UI toggle in the header.
 * Must be called at the start of each test suite to ensure
 * tests run against the demo database with sample data.
 */
export async function enableDemoMode(page: Page) {
  // Navigate to the app
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  // Check if demo mode is already active
  const demoIndicator = page.locator("text=Demo Mode");
  if (await demoIndicator.isVisible().catch(() => false)) {
    return; // Already in demo mode
  }

  // Find and click the demo mode toggle in the header
  const demoToggle = page.getByRole("button", { name: /demo/i });
  if (await demoToggle.isVisible().catch(() => false)) {
    await demoToggle.click();
    // Wait for the page to reload with demo data
    await page.waitForLoadState("networkidle");
  }
}

/**
 * Disable Demo Mode after tests complete.
 */
export async function disableDemoMode(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const demoToggle = page.getByRole("button", { name: /demo/i });
  if (await demoToggle.isVisible().catch(() => false)) {
    await demoToggle.click();
    await page.waitForLoadState("networkidle");
  }
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
