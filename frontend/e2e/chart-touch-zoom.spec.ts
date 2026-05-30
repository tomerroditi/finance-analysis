import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Drives the double-tap-then-drag figure zoom (utils/chartTouchZoom.ts).
 *
 * On touch devices a plain swipe scrolls the page (dragmode is off); zoom is
 * offered behind an explicit gesture: tap, then on the second tap keep the
 * finger down and drag up to zoom in. A plain double-tap resets to autorange.
 *
 * The handler is installed from App on touch devices only, so the suite runs
 * with `hasTouch` emulation and dispatches real TouchEvents at the first
 * zoomable (cartesian) chart, then reads the axis range Plotly computed.
 */
test.describe("Chart double-tap-drag zoom (touch)", () => {
  test.use({ hasTouch: true, isMobile: true });

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  /** Linear-space width of the first zoomable chart's x-axis, or null. */
  async function xSpan(page: Page): Promise<number | null> {
    return page.evaluate(() => {
      const plots = Array.from(
        document.querySelectorAll<HTMLElement>(".js-plotly-plot"),
      );
      for (const el of plots) {
        const xa = (el as { _fullLayout?: { xaxis?: { range?: [unknown, unknown]; r2l?: (v: unknown) => number } } })
          ._fullLayout?.xaxis;
        if (xa?.range && typeof xa.r2l === "function") {
          el.setAttribute("data-zoom-test", "1");
          return Math.abs(xa.r2l(xa.range[1]) - xa.r2l(xa.range[0]));
        }
      }
      return null;
    });
  }

  /**
   * Dispatch a tap, then a tap-and-drag of `dyUp` pixels (positive = up = zoom
   * in) on the marked chart. Mirrors a real one-finger double-tap-drag.
   */
  async function doubleTapDrag(page: Page, dyUp: number) {
    await page.evaluate((dy) => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const touchAt = (y: number) =>
        new Touch({ identifier: 0, target: el, clientX: cx, clientY: y });
      const fire = (type: string, y: number, list: Touch[]) =>
        el.dispatchEvent(
          new TouchEvent(type, {
            bubbles: true,
            cancelable: true,
            touches: list,
            targetTouches: list,
            changedTouches: [touchAt(y)],
          }),
        );
      // First tap.
      fire("touchstart", cy, [touchAt(cy)]);
      fire("touchend", cy, []);
      // Second tap — held — then dragged up to zoom in.
      fire("touchstart", cy, [touchAt(cy)]);
      fire("touchmove", cy - dy, [touchAt(cy - dy)]);
      fire("touchend", cy - dy, []);
    }, dyUp);
    // Plotly.relayout resolves on the next tick; let the range settle.
    await page.waitForTimeout(300);
  }

  test("double-tap-drag up zooms the figure in", async ({ page }) => {
    await navigateTo(page, "/");
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });
    const before = await xSpan(page);
    expect(before, "expected a zoomable cartesian chart").not.toBeNull();

    await doubleTapDrag(page, 120);

    const after = await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const xa = (el as { _fullLayout?: { xaxis?: { range?: [unknown, unknown]; r2l?: (v: unknown) => number } } })
        ._fullLayout!.xaxis!;
      return Math.abs(xa.r2l!(xa.range![1]) - xa.r2l!(xa.range![0]));
    });

    // Zooming in shrinks the visible x-range.
    expect(after).toBeLessThan((before as number) * 0.95);
  });

  test("a plain double-tap resets the zoom", async ({ page }) => {
    await navigateTo(page, "/");
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });
    const before = await xSpan(page);
    expect(before).not.toBeNull();

    // Zoom in first, then double-tap (no drag) to reset.
    await doubleTapDrag(page, 120);
    await doubleTapDrag(page, 0);

    const after = await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const xa = (el as { _fullLayout?: { xaxis?: { range?: [unknown, unknown]; r2l?: (v: unknown) => number } } })
        ._fullLayout!.xaxis!;
      return Math.abs(xa.r2l!(xa.range![1]) - xa.r2l!(xa.range![0]));
    });

    // Reset restores (autoranges back to) roughly the original span.
    expect(after).toBeGreaterThan((before as number) * 0.9);
  });
});
