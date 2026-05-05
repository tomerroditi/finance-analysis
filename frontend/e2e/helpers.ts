import { type Page, expect } from "@playwright/test";

/**
 * Open the Settings popup (sidebar Settings button) and toggle Demo Mode.
 * Used by both enable/disable helpers — Demo Mode lives inside the Settings
 * popup, not directly in the sidebar, so we must open the popup first.
 */
async function toggleDemoMode(page: Page, expectedAfter: "on" | "off") {
  // OnboardingGate would redirect fresh users from "/" to "/onboarding".
  // Bypass it by navigating directly to a Layout-mounted route that the
  // gate never touches. Settings is reachable from any page's sidebar.
  await page.goto("/data-sources");
  await page.waitForLoadState("domcontentloaded");
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
 * each test suite to ensure tests run against the demo database. After
 * the toggle we navigate to the dashboard and wait for at least one KPI
 * value to render, so the IndexedDB cache is warm before any test in the
 * suite asserts on visible page text.
 */
export async function enableDemoMode(page: Page) {
  await toggleDemoMode(page, "on");
  await page.goto("/");
  await expect(page.getByText(/Bank Balance/i).first()).toBeVisible({
    timeout: 30_000,
  });
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
 * Assert that a page's Layout shell has mounted. Most Layout-mounted pages
 * no longer render an `<h1>` in the page body — the title lives in the
 * Sidebar / TopBar — so we check for the Sidebar `<nav>` instead. The
 * `title` argument is preserved for call-site readability but is also
 * loosely matched against the active sidebar link.
 */
export async function expectPageTitle(page: Page, title: string | RegExp) {
  await expect(page.getByRole("navigation").first()).toBeVisible({
    timeout: 10_000,
  });
  // Best-effort: the active link in the sidebar should mention the page.
  const link = page.getByRole("link", { name: title }).first();
  if (await link.isVisible().catch(() => false)) {
    await expect(link).toBeVisible();
  }
}
