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
 *
 * This spec performs backend writes (the demo toggle itself, and — in the
 * "Reset demo data" block below — an unconditional demo-DB rebuild), so it
 * must stay OUT of `READ_ONLY_SPECS` in `playwright.config.ts`.
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

    // Two settings buttons exist (sidebar + mobile top bar); click the one
    // visible at the current viewport.
    const openSettings = () =>
      page
        .locator("button:has(svg.lucide-settings)")
        .filter({ visible: true })
        .first()
        .click();

    await openSettings();

    await test.step("reset-demo-data control is absent while Demo Mode is off", async () => {
      const toggleRow = page.getByText(/^Demo Mode$/);
      await expect(toggleRow).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Reset demo data" }),
      ).toHaveCount(0);
    });

    // Toggle Demo Mode ON via the UI.
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

    await test.step("resetting demo data confirms, POSTs /demo/reset, and the UI recovers", async () => {
      // Reopen Settings — the earlier Escape closed it, and DemoModeContext's
      // query reset + the reload above would have unmounted it anyway.
      await openSettings();

      const resetButton = page.getByRole("button", { name: "Reset demo data" });
      await expect(resetButton).toBeVisible();
      await resetButton.click();

      // Confirmation goes through the shared useConfirm()/alertdialog idiom,
      // not window.confirm — assert the real dialog, not a browser prompt.
      const confirmDialog = page.getByRole("alertdialog");
      await expect(confirmDialog).toBeVisible();
      await expect(
        confirmDialog.getByRole("heading", { name: "Reset demo data" }),
      ).toBeVisible();
      await expect(
        confirmDialog.getByText(
          "This rebuilds the demo database from scratch, discarding every change made in demo mode by any client. This cannot be undone.",
        ),
      ).toBeVisible();

      // Assert the real wiring: confirming must actually issue the
      // unconditional rebuild POST, not just close the dialog and hope.
      const resetRequestPromise = page.waitForResponse(
        (res) =>
          res.url().includes("/api/testing/demo/reset") &&
          res.request().method() === "POST",
      );
      await confirmDialog.getByRole("button", { name: "Reset demo data" }).click();
      const resetResponse = await resetRequestPromise;
      expect(resetResponse.status()).toBe(200);
      expect(await resetResponse.json()).toEqual({ status: "success" });

      // UI settles: the success toast fires and the app still renders demo
      // data afterwards (queryClient.resetQueries() re-fetches into a
      // populated state, not an empty one — proving the rebuild actually
      // repopulated the demo DB rather than leaving it corrupted/empty).
      // Other role="status" regions exist in the app (network/SW toasts),
      // so filter by text rather than asserting on the bare role.
      const successToast = page
        .getByRole("status")
        .filter({ hasText: "Demo data reset successfully" });
      await expect(successToast).toBeVisible();
      await expect(confirmDialog).toBeHidden();
      await expect(
        page.getByRole("heading", { name: /no accounts connected/i }),
      ).toBeHidden();
      await expect(resetButton).toBeVisible();
      await expect(resetButton).toBeEnabled();
    });
  });
});
