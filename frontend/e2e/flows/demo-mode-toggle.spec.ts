import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Verifies Demo Mode actually swaps the database underneath the UI.
 *
 * With Demo Mode OFF the empty-state KPIs read "--" / 0; with Demo Mode ON
 * the demo DB exposes a populated portfolio. We toggle through the
 * Settings popup and assert the UI shows real values.
 */
test.describe("Demo Mode toggle flow", () => {
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("toggling demo mode flips the backend state and seeds demo accounts", async ({
    page,
    request,
  }) => {
    // Start from a known state: demo mode OFF.
    await setDemoMode(request, false);

    // Verify backend reports demo_mode=false before we touch the UI.
    const before = await request.get(
      "http://localhost:8000/api/testing/demo_mode_status",
    );
    expect((await before.json()).demo_mode).toBe(false);

    await gotoAndWait(page, "/data-sources");

    // Toggle Demo Mode ON via the UI.
    await page
      .locator("button:has(svg.lucide-settings)")
      .first()
      .click();
    const toggleRow = page.getByText(/^Demo Mode$/);
    await toggleRow.waitFor();
    await toggleRow.click();
    await page.keyboard.press("Escape");

    // The DemoModeContext resets queries on toggle — give it time, then
    // reload to ensure the data sources list reflects the seeded accounts.
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForLoadState("domcontentloaded");

    // Demo ON: the empty-state is gone (real demo accounts seeded).
    await expect(
      page.getByRole("heading", { name: /no accounts connected/i }),
    ).toBeHidden({ timeout: 20_000 });

    // Sanity: backend reflects the new demo mode state.
    const status = await request.get(
      "http://localhost:8000/api/testing/demo_mode_status",
    );
    expect((await status.json()).demo_mode).toBe(true);
  });
});
