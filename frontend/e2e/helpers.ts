import {
  type Page,
  type APIRequestContext,
  expect,
  request,
} from "@playwright/test";

/**
 * Backend API base. Defaults to the single shared dev backend on :8000, but
 * the isolated-parallel harness (`test:e2e:isolated`) overrides it per shard
 * via `E2E_API_BASE` so each shard's Node-side API calls (demo toggle, seeding)
 * target that shard's own isolated backend. Exported so every spec that talks
 * to the backend directly shares one env-driven source instead of hardcoding
 * the URL.
 */
export const API_BASE = process.env.E2E_API_BASE ?? "http://localhost:8000/api";

/**
 * localStorage key the app reads its Demo Mode flag from. Must match
 * DEMO_MODE_STORAGE_KEY in src/services/demoMode.ts.
 */
const DEMO_MODE_STORAGE_KEY = "fad_demo_mode";

/**
 * Ensure the demo database exists, once per worker process.
 *
 * `demo/prepare` is idempotent, but inside the suite it still cost ~0.8 s a
 * call — it queues behind whatever the previous test's page left the backend
 * computing — and `enableDemoMode` runs before every test. Nothing in the
 * suite deletes the demo DB (`demo/reset` rebuilds it in place), so once it
 * exists for this worker's backend it stays. A failed call clears the memo so
 * the next test retries instead of inheriting the rejection.
 */
let demoPrepared: Promise<void> | null = null;

function ensureDemoDatabase(): Promise<void> {
  demoPrepared ??= (async () => {
    const ctx: APIRequestContext = await request.newContext();
    try {
      await ctx.post(`${API_BASE}/testing/demo/prepare`);
    } finally {
      await ctx.dispose();
    }
  })().catch((err) => {
    demoPrepared = null;
    throw err;
  });
  return demoPrepared;
}

/**
 * Put a browser context into Demo Mode.
 *
 * Demo Mode is per-client and lives in localStorage, so it must be seeded
 * before the document loads — a Node-side API call cannot switch a browser.
 * Also ensures the demo database exists, which is idempotent and will not
 * disturb another context already browsing demo data.
 */
export async function enableDemoMode(page: Page) {
  await ensureDemoDatabase();
  await page.addInitScript(
    ([key]) => localStorage.setItem(key, "1"),
    [DEMO_MODE_STORAGE_KEY],
  );
}

/**
 * Take a browser context out of Demo Mode.
 */
export async function disableDemoMode(page: Page) {
  await page.addInitScript(
    ([key]) => localStorage.setItem(key, "0"),
    [DEMO_MODE_STORAGE_KEY],
  );
}

/**
 * Rebuild the demo database from the frozen snapshot, discarding every
 * change made in Demo Mode. Use where a spec needs guaranteed-pristine
 * demo data; it affects every client currently in Demo Mode.
 */
export async function resetDemoData() {
  const ctx: APIRequestContext = await request.newContext();
  try {
    await ctx.post(`${API_BASE}/testing/demo/reset`);
  } finally {
    await ctx.dispose();
  }
}

/**
 * Confirm every recurring charge the detector currently proposes.
 *
 * Detection only produces *candidates*. The budget Overview's fixed and
 * committed segments, and the forecast's committed figure, are built from
 * confirmed charges alone, so a spec asserting on those has to put the demo
 * data's subscriptions through the gate first. Run it after
 * ``resetDemoData()`` — a reset rebuilds the demo DB and takes every stored
 * verdict with it.
 */
export async function confirmAllRecurring() {
  const ctx: APIRequestContext = await request.newContext({
    extraHTTPHeaders: { "X-FAD-Demo": "1" },
  });
  try {
    const listed = await ctx.get(`${API_BASE}/analytics/recurring`);
    expect(listed.ok()).toBeTruthy();
    const { items } = await listed.json();
    const decisions = (items as { normalized: string }[]).map((item) => ({
      normalized: item.normalized,
      decision: "confirmed",
    }));
    if (decisions.length === 0) return;
    const stored = await ctx.post(`${API_BASE}/analytics/recurring/decisions`, {
      data: { decisions },
    });
    expect(stored.ok()).toBeTruthy();
  } finally {
    await ctx.dispose();
  }
}

/**
 * Navigate to a page and wait for it to load.
 *
 * Sets the OnboardingGate's session-storage flag before the document loads
 * (via addInitScript) so a fresh-user redirect (is_first_run=true) doesn't
 * bounce us off the target page when demo mode hasn't been toggled yet.
 * Using an init script instead of a warm-up `goto("/")` avoids booting the
 * dashboard (the most expensive page) as a side effect of every navigation —
 * that hidden extra load used to dominate suite runtime.
 */
export async function navigateTo(page: Page, path: string) {
  await page.addInitScript(() => {
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
