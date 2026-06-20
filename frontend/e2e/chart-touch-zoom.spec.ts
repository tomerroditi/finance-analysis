import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Drives the double-tap-to-enter native zoom mode (utils/chartTouchZoom.ts).
 *
 * A plain swipe scrolls the page (dragmode off). Double-tapping a chart enters
 * Plotly's native zoom mode (`dragmode: "zoom"`); a one-finger drag then marks
 * a rectangle and zooms into it, and the zoom persists after lifting the finger
 * (native GUI interaction + `chartTheme.uirevision`). Touching outside the
 * chart leaves zoom mode.
 *
 * Runs under `hasTouch` emulation (the handler installs on touch devices only)
 * and dispatches real TouchEvents.
 */
test.describe("Chart double-tap native zoom mode (touch)", () => {
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

  /** Mark the first zoomable (cartesian) chart and return its x-span, or null. */
  async function markChart(page: Page): Promise<number | null> {
    return page.evaluate(() => {
      for (const el of document.querySelectorAll<HTMLElement>(".js-plotly-plot")) {
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

  const xSpan = (page: Page) =>
    page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const xa = (el as { _fullLayout?: { xaxis?: { range?: [unknown, unknown]; r2l?: (v: unknown) => number } } })
        ._fullLayout!.xaxis!;
      return Math.abs(xa.r2l!(xa.range![1]) - xa.r2l!(xa.range![0]));
    });

  const dragmode = (page: Page) =>
    page.evaluate(
      () =>
        (document.querySelector('[data-zoom-test="1"]') as { _fullLayout?: { dragmode?: unknown } })
          ._fullLayout?.dragmode,
    );

  /** Double-tap the marked chart's center to toggle zoom mode on. */
  async function doubleTap(page: Page) {
    await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const r = el.getBoundingClientRect();
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      const t = () => new Touch({ identifier: 0, target: el, clientX: x, clientY: y });
      const tap = () => {
        el.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, cancelable: true, touches: [t()], changedTouches: [t()] }));
        el.dispatchEvent(new TouchEvent("touchend", { bubbles: true, cancelable: true, touches: [], changedTouches: [t()] }));
      };
      tap();
      tap();
    });
    await page.waitForTimeout(150);
  }

  test("double-tap enters zoom mode; native drag zooms and persists", async ({ page }) => {
    await navigateTo(page, "/");
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({ timeout: 45_000 });
    const before = await markChart(page);
    expect(before, "expected a zoomable cartesian chart").not.toBeNull();

    await doubleTap(page);
    expect(await dragmode(page)).toBe("zoom");
    await expect(page.locator('[data-zoom-test="1"].chart-zoom-active')).toBeVisible();

    // Drag a rectangle on Plotly's native drag layer — its own zoom interaction.
    await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('[data-zoom-test="1"]')!;
      const nsew = el.querySelector(".nsewdrag")!;
      const r = nsew.getBoundingClientRect();
      const x1 = r.left + r.width * 0.35;
      const y1 = r.top + r.height * 0.4;
      const x2 = r.left + r.width * 0.65;
      const y2 = r.top + r.height * 0.6;
      const T = (x: number, y: number) =>
        new Touch({ identifier: 1, target: nsew, clientX: x, clientY: y, pageX: x, pageY: y } as TouchInit);
      const fire = (type: string, x: number, y: number, list: Touch[]) =>
        nsew.dispatchEvent(
          new TouchEvent(type, { bubbles: true, cancelable: true, touches: list, targetTouches: list, changedTouches: [T(x, y)] }),
        );
      fire("touchstart", x1, y1, [T(x1, y1)]);
      fire("touchmove", x2, y2, [T(x2, y2)]);
      fire("touchend", x2, y2, []);
    });
    await page.waitForTimeout(250);

    const afterDrag = await xSpan(page);
    expect(afterDrag).toBeLessThan((before as number) * 0.95);

    // Lifting the finger keeps the zoom; a re-render must not reset it.
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await page.waitForTimeout(150);
    expect(await xSpan(page)).toBeLessThan((before as number) * 0.95);
  });

  test("touching outside the chart leaves zoom mode", async ({ page }) => {
    await navigateTo(page, "/");
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({ timeout: 45_000 });
    await markChart(page);

    await doubleTap(page);
    expect(await dragmode(page)).toBe("zoom");

    // A touch outside any chart exits zoom mode (back to scroll).
    await page.evaluate(() => {
      const target = document.body;
      const t = new Touch({ identifier: 2, target, clientX: 5, clientY: 5 });
      target.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, cancelable: true, touches: [t], changedTouches: [t] }));
    });
    await page.waitForTimeout(150);

    expect(await dragmode(page)).toBe(false);
    await expect(page.locator('[data-zoom-test="1"].chart-zoom-active')).toHaveCount(0);
  });
});
