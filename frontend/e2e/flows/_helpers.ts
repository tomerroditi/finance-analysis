import { type Page, type APIRequestContext } from "@playwright/test";

const API_BASE = "http://localhost:8000/api";

/**
 * Toggle Demo Mode via the testing API rather than the Settings popup.
 * Faster and more reliable than driving the UI for setup/teardown — the UI
 * helper exists in `../helpers.ts` for tests that exercise the toggle itself.
 */
export async function setDemoMode(request: APIRequestContext, enabled: boolean) {
  await request.post(`${API_BASE}/testing/toggle_demo_mode`, {
    data: { enabled },
  });
}

/**
 * Navigate to the app, wiping any persisted React Query / IndexedDB cache
 * first so the frontend doesn't hydrate stale data from a previous Demo
 * Mode session. Then wait for the network to settle.
 *
 * The dashboard persists its query cache to IndexedDB (`finance-analysis`).
 * If we leave it intact, switching demo mode via the testing API leaves
 * the page rendering production-mode data even though the backend now
 * serves demo data. Clearing storage at navigation time forces a cold load.
 */
export async function gotoAndWait(page: Page, path: string) {
  // Land on a placeholder page so storage APIs are available without
  // booting the React app, then wipe persisted state, then load the real
  // path from a clean slate.
  await page.goto("about:blank");
  await page.goto("/");
  await page.evaluate(async () => {
    try {
      localStorage.clear();
      sessionStorage.clear();
      const dbs = (await indexedDB.databases?.()) ?? [];
      await Promise.all(
        dbs.map(
          (d) =>
            new Promise<void>((resolve) => {
              if (!d.name) return resolve();
              const req = indexedDB.deleteDatabase(d.name);
              req.onsuccess = req.onerror = req.onblocked = () => resolve();
            }),
        ),
      );
      // The PWA service worker keeps its own Cache API store of /api
      // responses. Wipe both the caches and the worker registration so
      // the next navigation hits the network fresh.
      if ("caches" in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }
      if (navigator.serviceWorker) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map((r) => r.unregister()));
      }
    } catch {
      /* best-effort cleanup */
    }
  });
  // Hard reload so React, i18next, and React Query all initialise from the
  // wiped storage rather than from in-memory state of the previous goto.
  // We always tag with a cache-busting query so the SPA fully remounts,
  // even when the target path matches the page we cleared from.
  const sep = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${sep}_e2e=${Date.now()}`);
  await page.waitForLoadState("domcontentloaded");
  // The PWA service worker keeps the network active indefinitely, so
  // `networkidle` never settles. A short post-load grace gives queries
  // time to fire without that risk.
  await page.waitForTimeout(800);
}

/**
 * Click a sidebar nav link by its visible English label. Falls back to a
 * direct goto if the link isn't visible (e.g. mobile drawer is closed).
 */
export async function navigateViaSidebar(page: Page, label: RegExp, fallbackPath: string) {
  const link = page.getByRole("link", { name: label }).first();
  if (await link.isVisible().catch(() => false)) {
    await link.click();
  } else {
    await page.goto(fallbackPath);
  }
  await page.waitForLoadState("domcontentloaded");
  // The PWA service worker keeps the network active indefinitely, so
  // `networkidle` never settles. A short post-load grace gives queries
  // time to fire without that risk.
  await page.waitForTimeout(800);
}
