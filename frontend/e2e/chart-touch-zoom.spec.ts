import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";
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
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test.use({ hasTouch: true, isMobile: true });
  /**
   * Scroll a cartesian (zoomable) chart card into view so it mounts.
   *
   * The dashboard defers below-the-fold cards (DeferUntilVisible), and the
   * only eager Plotly chart in the default layout is the Income-by-source
   * donut — a pie, which has no zoomable cartesian axis. The Net Worth Over
   * Time line chart is a full-width card further down, so it must be scrolled
   * into view before it exists in the DOM for markChart to find. (The Income &
   * Expenses card no longer renders a Plotly chart — it's a CSS ledger now.)
   */
  async function revealZoomableChart(page: Page) {
    const card = page.locator('[data-card-id="net_worth"]');
    await card.scrollIntoViewIfNeeded();
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible({ timeout: 45_000 });
  }

  /**
   * Mark the zoomable (cartesian) chart in the Net Worth card and return its
   * x-span, or null if it isn't interactive yet. Poll this via `expect.poll`
   * instead of gating on `.js-plotly-plot` visibility: Plotly adds that class
   * in `makePlotFramework`, *before* autorange has produced a concrete
   * `_fullLayout.xaxis.range` and before the `.nsewdrag` drag layer has
   * geometry — so "visible" is not "ready to be dragged". Requiring a real
   * x-axis range, an `r2l` scale fn, and a laid-out `.nsewdrag` makes the gate
   * match exactly what the double-tap + drag steps depend on. Scoping to the
   * `net_worth` card also pins which chart is under test (the global scan could
   * mark whichever `DeferUntilVisible` card happened to mount first).
   */
  async function markChart(page: Page): Promise<number | null> {
    return page.evaluate(() => {
      const root = document.querySelector('[data-card-id="net_worth"]') ?? document;
      for (const el of root.querySelectorAll<HTMLElement>(".js-plotly-plot")) {
        const xa = (el as { _fullLayout?: { xaxis?: { range?: [unknown, unknown]; r2l?: (v: unknown) => number } } })
          ._fullLayout?.xaxis;
        const nsew = el.querySelector(".nsewdrag");
        if (xa?.range && typeof xa.r2l === "function" && nsew && nsew.getBoundingClientRect().width > 0) {
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
  }

  test("double-tap enters zoom mode; native drag zooms and persists", async ({ page }) => {
    await navigateTo(page, "/");
    await revealZoomableChart(page);
    // Wait for the chart to be genuinely interactive (range + drag layer laid
    // out), not merely present. markChart tags it and returns its x-span.
    await expect
      .poll(() => markChart(page), { message: "expected a zoomable cartesian chart", timeout: 45_000 })
      .not.toBeNull();
    const before = await xSpan(page);

    await doubleTap(page);
    // dragmode flips async: the handler does `void import(...).then(Plotly.relayout)`,
    // so poll for the settled state instead of reading once after a fixed sleep.
    await expect.poll(() => dragmode(page), { timeout: 10_000 }).toBe("zoom");
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
    // touchend → Plotly's async zoomDone relayout shrinks the x-span; poll for it.
    await expect.poll(() => xSpan(page), { timeout: 10_000 }).toBeLessThan(before * 0.95);

    // Lifting the finger keeps the zoom; a re-render must not reset it.
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await expect.poll(() => xSpan(page), { timeout: 10_000 }).toBeLessThan(before * 0.95);
  });

  test("touching outside the chart leaves zoom mode", async ({ page }) => {
    await navigateTo(page, "/");
    await revealZoomableChart(page);
    await expect.poll(() => markChart(page), { timeout: 45_000 }).not.toBeNull();

    await doubleTap(page);
    await expect.poll(() => dragmode(page), { timeout: 10_000 }).toBe("zoom");

    // A touch outside any chart exits zoom mode (back to scroll).
    await page.evaluate(() => {
      const target = document.body;
      const t = new Touch({ identifier: 2, target, clientX: 5, clientY: 5 });
      target.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, cancelable: true, touches: [t], changedTouches: [t] }));
    });

    // exitZoom's `dragmode: false` relayout is also async — poll for it.
    await expect.poll(() => dragmode(page), { timeout: 10_000 }).toBe(false);
    await expect(page.locator('[data-zoom-test="1"].chart-zoom-active')).toHaveCount(0);
  });
});
