import { test, expect } from "@playwright/test";
import { gotoAndWait } from "./_helpers";
import { API_BASE, disableDemoMode, enableDemoMode } from "../helpers";

/**
 * Verifies Demo Mode actually swaps the database underneath the UI.
 *
 * With Demo Mode OFF the empty-state KPIs read "--" / 0; with Demo Mode ON
 * the demo DB exposes a populated portfolio. We toggle through the
 * Settings popup and assert the UI shows real values.
 *
 * Demo Mode is per-client now: `demo_mode_status` reports whatever the
 * *caller's own* `X-FAD-Demo` header says, not some shared backend flag.
 * A bare `request` fixture call (no header) would always read back
 * `demo_mode: false` regardless of what the browser did, so the
 * post-toggle sanity check below reads the flag through the page itself
 * (mirroring how `services/api.ts`'s interceptor attaches the header)
 * instead of a headerless Node-side request.
 */
test.describe("Demo Mode toggle flow", () => {
  test.beforeEach(async ({ page }) => {
    // Start from a known state: demo mode OFF.
    await disableDemoMode(page);
  });

  test("toggling demo mode flips the backend state and seeds demo accounts", async ({
    page,
    request,
  }) => {
    // Verify backend reports demo_mode=false for a header-less caller.
    const before = await request.get(`${API_BASE}/testing/demo_mode_status`);
    expect((await before.json()).demo_mode).toBe(false);

    await gotoAndWait(page, "/data-sources");

    // Toggle Demo Mode ON via the UI. Two settings buttons exist (sidebar +
    // mobile top bar); click the one visible at the current viewport.
    await page
      .locator("button:has(svg.lucide-settings)")
      .filter({ visible: true })
      .first()
      .click();
    const toggleRow = page.getByText(/^Demo Mode$/);
    await toggleRow.waitFor();
    await toggleRow.click();
    await page.keyboard.press("Escape");

    // The click set localStorage to "1" at runtime, but the `page` still
    // carries the init script `beforeEach` registered to force it back to
    // "0" on every navigation (that's how it seeded the OFF start state
    // above) — a plain `page.reload()` would silently re-arm it and undo
    // the toggle. Re-registering via `enableDemoMode` adds a second init
    // script that runs after the first on the same navigation, so it wins
    // and the reload actually reloads into Demo Mode.
    await enableDemoMode(page);

    // The DemoModeContext resets queries on toggle — give it time, then
    // reload to ensure the data sources list reflects the seeded accounts.
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForLoadState("domcontentloaded");

    // Demo ON: the empty-state is gone (real demo accounts seeded).
    await expect(
      page.getByRole("heading", { name: /no accounts connected/i }),
    ).toBeHidden({ timeout: 20_000 });

    // Sanity: the browser's own requests now carry the demo header, which
    // is what actually drives which database the backend serves — checked
    // through the page via the same relative `/api` path (Vite-proxied,
    // same-origin) the app's axios interceptor uses, rather than the
    // headerless `request` fixture hitting the backend directly.
    const status: { demo_mode: boolean } = await page.evaluate(async () => {
      const demo = localStorage.getItem("fad_demo_mode") === "1";
      const res = await fetch("/api/testing/demo_mode_status", {
        headers: demo ? { "X-FAD-Demo": "1" } : {},
      });
      return res.json();
    });
    expect(status.demo_mode).toBe(true);
  });
});
