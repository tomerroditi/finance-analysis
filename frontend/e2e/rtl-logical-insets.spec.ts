import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Regression guard for Tailwind 4 logical *inset* utilities.
 *
 * Tailwind names these after the shorthand (`start-*` / `end-*` /
 * `inset-x-*`), not the CSS property. Classes spelled after the property
 * (`inset-inline-start-0`) match no utility, emit no CSS, and fail silently:
 * the element falls back to its static position instead of erroring. Two
 * places shipped that way — the settings toggle knob never travelled, and
 * the sidebar footer shrink-wrapped instead of spanning the sidebar.
 *
 * Asserting on *computed geometry* is what makes this a real guard: a dead
 * class still leaves the class string in the DOM, so a className assertion
 * would pass against the bug.
 */

/** Width of the desktop sidebar and of its absolutely-positioned footer. */
async function sidebarWidths(page: Page) {
  return page.evaluate(() => {
    const aside = document.querySelector("aside");
    const footer = aside?.querySelector("div.absolute.bottom-0");
    if (!aside || !footer) return null;
    return {
      aside: aside.getBoundingClientRect().width,
      footer: footer.getBoundingClientRect().width,
    };
  });
}

/**
 * Horizontal offset of a settings toggle's knob within its track, in px,
 * once the knob's `transition-all` has finished.
 *
 * Awaiting the animation matters: `getBoundingClientRect` mid-transition
 * returns the interpolated position, and reading it in the same tick as the
 * click returns the *pre*-toggle position — which looks exactly like the bug
 * this spec guards against. Offsets are measured from the track's left edge
 * in both directions, so the caller can assert which way the knob travels.
 */
async function settledKnobOffset(page: Page, labelText: string) {
  return page.evaluate(async (label) => {
    const el = Array.from(document.querySelectorAll("label")).find(
      (l) => l.textContent?.trim() === label,
    );
    const track = el?.parentElement?.querySelector("div.w-9");
    const knob = track?.firstElementChild;
    if (!track || !knob) return null;
    await Promise.all(knob.getAnimations().map((a) => a.finished));
    return Math.round(
      knob.getBoundingClientRect().left - track.getBoundingClientRect().left,
    );
  }, labelText);
}

/** Whether a settings toggle currently reads as on (knob at the inline-end). */
async function knobIsOn(page: Page, labelText: string) {
  return page.evaluate((label) => {
    const el = Array.from(document.querySelectorAll("label")).find(
      (l) => l.textContent?.trim() === label,
    );
    const knob = el?.parentElement?.querySelector("div.w-9")?.firstElementChild;
    return knob ? knob.className.includes("calc(") : null;
  }, labelText);
}

test.describe("logical inset utilities", () => {
  // Self-heal demo mode, matching the other read-only specs, so the spec is
  // order-independent. Demo Mode lives in the browser context's
  // localStorage, so it must be seeded per-test (each test gets a fresh
  // context) rather than once in beforeAll via a throwaway page — that page
  // is a different browser context from the one the test navigates in, so
  // anything set there never reaches the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("sidebar footer spans the sidebar and the settings toggle knob travels, in both directions", async ({
    page,
  }) => {
    // One cold navigation covers both directions: the settings popup's own
    // language control flips the app live, with no reload.
    await navigateTo(page, "/");
    await expect(page.locator("aside")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

    // --- Sidebar footer stretches to the sidebar's full width (LTR) ---
    // With the dead class it shrink-wrapped to ~187px inside a 256px
    // sidebar, leaving the top border visibly short of the edge.
    const ltrWidths = await sidebarWidths(page);
    expect(ltrWidths).not.toBeNull();
    expect(ltrWidths!.footer).toBeGreaterThan(ltrWidths!.aside - 4);

    await page.locator("aside").getByRole("button", { name: "Settings" }).click();

    // --- Toggle knob travels between states (LTR) ---
    // Budget Alerts defaults to on and persists to localStorage only, so
    // toggling it performs no backend write (this spec is read-only).
    const alertsRow = page
      .locator("label")
      .filter({ hasText: /^Budget Alerts$/ })
      .locator("..");

    const ltrOn = await settledKnobOffset(page, "Budget Alerts");
    await alertsRow.click();
    // Confirm React actually re-rendered the off state before measuring, so a
    // knob that never moves fails on the offset assertion rather than here.
    await expect.poll(() => knobIsOn(page, "Budget Alerts")).toBe(false);
    const ltrOff = await settledKnobOffset(page, "Budget Alerts");

    expect(ltrOn).not.toBeNull();
    expect(ltrOff).not.toBeNull();
    // The bug pinned both states to offset 0 — the knob never moved.
    expect(Math.abs(ltrOn! - ltrOff!)).toBeGreaterThanOrEqual(8);
    // In LTR, "on" sits at the inline-end (right) side of the track.
    expect(ltrOn!).toBeGreaterThan(ltrOff!);

    // --- Flip to Hebrew and re-check, mirrored ---
    await page.getByText("עברית", { exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const rtlOff = await settledKnobOffset(page, "התראות תקציב");
    await page
      .locator("label")
      .filter({ hasText: /^התראות תקציב$/ })
      .locator("..")
      .click();
    await expect.poll(() => knobIsOn(page, "התראות תקציב")).toBe(true);
    const rtlOn = await settledKnobOffset(page, "התראות תקציב");

    expect(rtlOn).not.toBeNull();
    expect(rtlOff).not.toBeNull();
    expect(Math.abs(rtlOn! - rtlOff!)).toBeGreaterThanOrEqual(8);
    // In RTL the inline axis flips: "on" sits at the left side of the track.
    expect(rtlOn!).toBeLessThan(rtlOff!);

    // --- Sidebar footer still spans the sidebar in RTL ---
    await page.keyboard.press("Escape");
    const rtlWidths = await sidebarWidths(page);
    expect(rtlWidths).not.toBeNull();
    expect(rtlWidths!.footer).toBeGreaterThan(rtlWidths!.aside - 4);
  });
});
