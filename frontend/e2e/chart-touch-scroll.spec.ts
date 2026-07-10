import { test, expect, type Page } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Guards the touch-scroll fix in utils/plotlyLocale.ts.
 *
 * On touch devices Plotly's default `dragmode: "zoom"` hijacks a single-finger
 * drag to draw a zoom box, so dragging over a chart zooms it instead of
 * scrolling the page. The shared chartTheme sets `dragmode: false` on touch
 * devices (and config `scrollZoom: false`) so the gesture falls through to page
 * scroll; desktop keeps drag-to-zoom.
 *
 * `isTouchDevice` (in plotlyLocale.ts) is computed at module load from
 * `navigator.maxTouchPoints`, so these tests flip Playwright's `hasTouch`
 * emulation to exercise both branches and read the computed `_fullLayout` off
 * the Plotly graph div.
 *
 * Run via with_server.py so both backend + frontend are up. Demo Mode supplies
 * the Cohen-family data the dashboard charts need.
 */

/** Read the computed Plotly dragmode off the first rendered graph div. */
async function firstChartDragmode(page: Page): Promise<unknown> {
  const plot = page.locator(".js-plotly-plot").first();
  // Plotly is lazy-loaded (LazyPlot); a cold first fetch+eval of the dev
  // chunk can take tens of seconds on slow CI/sandbox machines.
  await expect(plot).toBeVisible({ timeout: 45_000 });
  return plot.evaluate(
    (el) => (el as unknown as { _fullLayout?: { dragmode?: unknown } })._fullLayout?.dragmode,
  );
}

test.describe("Chart touch-scroll (dragmode)", () => {
  test.describe("on a touch device", () => {
    test.use({ hasTouch: true, isMobile: true });

    test("charts disable drag so a finger scroll passes through", async ({ page }) => {
      await navigateTo(page, "/");
      // Plotly normalizes a disabled dragmode to the boolean false.
      expect(await firstChartDragmode(page)).toBe(false);
    });
  });

  test.describe("on a desktop (non-touch) device", () => {
    test.use({ hasTouch: false, isMobile: false });

    test("charts keep drag-to-zoom", async ({ page }) => {
      await navigateTo(page, "/");
      // Desktop has no scroll/zoom conflict, so the default zoom drag stays on.
      expect(await firstChartDragmode(page)).not.toBe(false);
    });
  });
});
