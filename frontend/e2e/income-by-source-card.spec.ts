import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * The "Income by source" dashboard card (id `income_by_source`) renders a
 * donut chart + a breakdown table with a Total row, plus range-preset
 * buttons (All time / This year / Last 12 months / Custom). It's visible by
 * default on the dashboard route; Demo Mode supplies sample income data so the
 * donut + table render. This spec guards that the card mounts and that
 * switching range presets doesn't crash it.
 *
 * All checks are client-side interactions on one rendered card, so they run
 * as a single test on a single dashboard load (the cold dashboard boot is the
 * expensive step — it used to be paid once per assertion group, 4×).
 */
test.describe("Income by source dashboard card", () => {
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll. enableDemoMode's demo/prepare call is idempotent, so this
  // is still cheap and order-independent when sharded alongside mutating
  // specs.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  /**
   * Locate the card container by its title, then climb to the enclosing
   * card div so we can scope the donut/table lookups (the dashboard renders
   * several other charts). The dashboard ships mobile + desktop layout
   * variants simultaneously, so we filter to the visible instance.
   */
  function cardContainer(page: Page) {
    return page
      .locator("div")
      .filter({ has: page.getByText("Income by source", { exact: true }) })
      .filter({ has: page.locator(".recharts-wrapper") })
      .filter({ visible: true })
      .last();
  }

  test("renders donut + Total row; range preset, Breakdown toggle, and label reveal all work", async ({
    page,
  }) => {
    await navigateTo(page, "/");

    // --- Card mounts: title, donut, and a Total row in the table ---
    await expect(
      page.getByText("Income by source", { exact: true }).first(),
    ).toBeVisible({ timeout: 45_000 });

    const card = cardContainer(page);

    await expect(card.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      card.getByText("Total", { exact: true }).first(),
    ).toBeVisible();

    // --- Switching to "Last 12 months" keeps the card rendered (no crash) ---
    await card.getByRole("button", { name: "Last 12 months" }).first().click();
    await expect(card.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      card.getByText("Total", { exact: true }).first(),
    ).toBeVisible();

    // --- Breakdown toggle collapses and restores the table ---
    await expect(card.locator("table").first()).toBeVisible();
    const toggle = card.getByRole("button", { name: "Breakdown" }).first();

    // Collapse: the table is removed but the donut stays.
    await toggle.click();
    await expect(card.locator("table")).toHaveCount(0);
    await expect(card.locator(".recharts-wrapper").first()).toBeVisible();

    // Expand again: the table comes back.
    await toggle.click();
    await expect(card.locator("table").first()).toBeVisible();

    // --- Tapping a source name reveals and hides the full label ---
    // Source names are truncated to fit the column. Tapping a name toggles a
    // full-name reveal (the label switches from `truncate` to a wrapped,
    // `whitespace-normal` display). Each row's source cell is a button
    // carrying `aria-expanded`; the Breakdown toggle lives outside the table,
    // so scoping to `table button` isolates the source-name buttons.
    const sourceButton = card.locator("table button[aria-expanded]").first();
    const label = sourceButton.locator("span").last();

    // Collapsed by default: label truncates.
    await expect(sourceButton).toHaveAttribute("aria-expanded", "false");
    await expect(label).toHaveClass(/truncate/);

    // Tap reveals the full name (wraps instead of truncating).
    await sourceButton.click();
    await expect(sourceButton).toHaveAttribute("aria-expanded", "true");
    await expect(label).toHaveClass(/whitespace-normal/);

    // Tap again collapses back to the truncated view.
    await sourceButton.click();
    await expect(sourceButton).toHaveAttribute("aria-expanded", "false");
    await expect(label).toHaveClass(/truncate/);

    // --- The breakdown scrolls in place instead of stretching the card ---
    // A household with many salary + other-income tags produces a long list.
    // It is capped at 20rem and scrolls internally, with the column header
    // and the Total row pinned by `position: sticky` so both stay readable
    // at any scroll offset. Read the geometry rather than the class list:
    // a className assertion would pass against a dead Tailwind class.
    const scroller = card.getByTestId("income-by-source-breakdown-scroll");
    await expect(scroller).toBeVisible();

    const capped = await scroller.evaluate((el) => ({
      overflowY: getComputedStyle(el).overflowY,
      clientHeight: el.clientHeight,
    }));
    expect(capped.overflowY).toBe("auto");
    // 20rem at the default 16px root font size.
    expect(capped.clientHeight).toBeLessThanOrEqual(320);

    await expect(scroller.locator("thead th").first()).toHaveCSS(
      "position",
      "sticky",
    );
    await expect(scroller.locator("tfoot td").first()).toHaveCSS(
      "position",
      "sticky",
    );

    // Scrolled to the bottom, the header still sits at the top edge of the
    // scroll box and the Total row at its bottom edge. The demo household has
    // only a handful of income sources — fewer than the cap holds — so the cap
    // is lowered here to force the overflow a real user with a dozen salary and
    // other-income tags hits. That exercises the sticky cells for real instead
    // of asserting geometry against a list that never scrolls.
    const pinned = await scroller.evaluate((el) => {
      el.style.maxHeight = "120px";
      el.scrollTop = el.scrollHeight;
      const box = el.getBoundingClientRect();
      const header = el.querySelector("thead th")!.getBoundingClientRect();
      const footer = el.querySelector("tfoot td")!.getBoundingClientRect();
      return {
        scrolled: el.scrollTop,
        headerOffset: header.top - box.top,
        footerOffset: box.bottom - footer.bottom,
      };
    });
    // The list really did scroll, and both pinned rows held their edges
    // (1px container border, so allow a few pixels of slack).
    expect(pinned.scrolled).toBeGreaterThan(0);
    expect(Math.abs(pinned.headerOffset)).toBeLessThanOrEqual(3);
    expect(Math.abs(pinned.footerOffset)).toBeLessThanOrEqual(3);
  });
});
