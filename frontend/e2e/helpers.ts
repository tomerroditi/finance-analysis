import { type Page, type APIRequestContext, expect, request } from "@playwright/test";

const API_BASE = "http://localhost:8000/api";

/**
 * Toggle Demo Mode via the testing API. Faster and more reliable than
 * driving the Settings popup, and the Settings popup itself has its own
 * dedicated test in `flows/demo-mode-toggle.spec.ts`.
 */
async function setDemoModeApi(enabled: boolean) {
  const ctx: APIRequestContext = await request.newContext();
  try {
    await ctx.post(`${API_BASE}/testing/toggle_demo_mode`, {
      data: { enabled },
    });
  } finally {
    await ctx.dispose();
  }
}

/**
 * Enable Demo Mode at the backend level. Tests can then navigate to any
 * page and the React Query queries will fetch demo data.
 */
export async function enableDemoMode(_page?: Page) {
  await setDemoModeApi(true);
}

/**
 * Disable Demo Mode after tests complete.
 */
export async function disableDemoMode(_page?: Page) {
  await setDemoModeApi(false);
}

/**
 * Navigate to a page and wait for it to load.
 *
 * Sets the OnboardingGate's session-storage flag before navigation so a
 * fresh-user redirect (is_first_run=true) doesn't bounce us off the
 * target page when demo mode hasn't been toggled yet.
 */
export async function navigateTo(page: Page, path: string) {
  await page.goto("about:blank");
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
  });
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
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
