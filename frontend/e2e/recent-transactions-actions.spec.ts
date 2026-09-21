import { test, expect, type Locator, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Dashboard "Recent Transactions" card — the row action bar, the
 * only-untagged filter and scroll retention.
 *
 * Covers six regressions the card shipped with:
 *  1. Collapsing a row's action bar left the category/tag editor (and the
 *     details sheet) stranded on screen under a row with no bar.
 *  2. Tagging a row reset the feed's page size to the first 20 rows, throwing
 *     the reader back to the top of the card.
 *  3. The card offered only three of the actions the transactions table has.
 *  4. Nothing in the card said where the money moved (account / card).
 *  5. Each date header was sticky inside its own group wrapper, so it unpinned
 *     the moment its group ended and left a strip of the outgoing group's last
 *     row exposed above the next pinned date.
 *  6. The action bar was indented past the row's icon column, which wrapped its
 *     buttons onto three lines on a phone.
 */

const RECENT_CARD = '[data-card-id="recent"]';

function recentCard(page: Page): Locator {
  return page.locator(RECENT_CARD);
}

/** Scroll the feed's own scroll container by `delta` and return its scrollTop. */
async function scrollFeed(page: Page, delta: number): Promise<number> {
  return page.evaluate(
    ([selector, by]) => {
      const root = document
        .querySelector(selector as string)
        ?.querySelector<HTMLElement>("[data-scroll-root]");
      if (!root) throw new Error("recent transactions scroll root not found");
      root.scrollTop += by as number;
      return root.scrollTop;
    },
    [RECENT_CARD, delta] as const,
  );
}

/**
 * Largest gap, over a scroll sweep, between the top of the feed's scroll port
 * and the nearest date header still on screen.
 *
 * A date header is meant to be pinned flush to that edge at every offset, so
 * anything above zero is a band of scrolling rows left uncovered — the thin
 * line of a half-scrolled row that used to show above the pinned date.
 */
async function worstUncoveredBandAboveDate(page: Page): Promise<number> {
  return page.evaluate(async (selector) => {
    const root = document
      .querySelector(selector)
      ?.querySelector<HTMLElement>("[data-scroll-root]");
    if (!root) throw new Error("recent transactions scroll root not found");
    const headers = () => [
      ...root.querySelectorAll<HTMLElement>('[data-testid="recent-tx-date"]'),
    ];
    const rootTop = () => root.getBoundingClientRect().top;
    // Sticky offsets are recomputed by the compositor, not by a forced
    // layout, so every scroll has to cross a frame before it can be read.
    const settle = () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );

    // Natural (unpinned) offset of each header. Read at scrollTop 0, where
    // every header below the fold still sits at its flow position.
    root.scrollTop = 0;
    await settle();
    const boundaries = headers()
      .map((header) => header.getBoundingClientRect().top - rootTop())
      .filter((offset) => offset > 0);

    // Only the handover from one date to the next can leave a gap, so probe
    // finely around each boundary instead of sweeping the whole feed coarsely.
    const offsets = new Set<number>([0]);
    for (const boundary of boundaries) {
      for (let delta = -48; delta <= 12; delta += 3) {
        offsets.add(Math.max(0, Math.round(boundary + delta)));
      }
    }

    let worst = 0;
    for (const scrollTop of offsets) {
      root.scrollTop = scrollTop;
      await settle();
      const top = rootTop();
      const visible = headers()
        .map((header) => header.getBoundingClientRect())
        .filter((box) => box.bottom - top > 0.5)
        .map((box) => box.top - top);
      if (visible.length) worst = Math.max(worst, Math.min(...visible));
    }
    return worst;
  }, RECENT_CARD);
}

async function feedScrollTop(page: Page): Promise<number> {
  return page.evaluate((selector) => {
    const root = document
      .querySelector(selector)
      ?.querySelector<HTMLElement>("[data-scroll-root]");
    return root?.scrollTop ?? -1;
  }, RECENT_CARD);
}

test.describe("Dashboard recent transactions — row actions", () => {
  // The demo database is process-global and this file tags a transaction;
  // start from the frozen snapshot so a predecessor's writes can't leak in.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("action bar exposes the full action set, details and untagged filter", async ({
    page,
  }) => {
    await navigateTo(page, "/");

    const card = recentCard(page);
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(card.getByTestId("recent-tx-row").first()).toBeVisible({
      timeout: 15_000,
    });

    // --- The action bar carries every per-row action ---------------------
    await card.getByRole("button", { name: "More actions" }).first().click();

    for (const name of ["Tag", "Clear category and tag", "Split", "Details"]) {
      await expect(
        card.getByRole("button", { name, exact: true }).first(),
      ).toBeVisible();
    }
    // The rule quick action is the same one the transactions page offers: a
    // demo bank/credit-card row either has no matching rule ("Add Rule") or
    // exactly one ("View Rule").
    await expect(
      card.getByRole("button", { name: /Add Rule|View Rule/ }).first(),
    ).toBeVisible();

    // --- Details sheet names the account the money moved through ---------
    await card.getByRole("button", { name: "Details", exact: true }).first().click();
    await expect(card.getByText("Account", { exact: true })).toBeVisible();
    await expect(card.getByText("Provider", { exact: true })).toBeVisible();

    // --- Collapsing the bar takes its panels with it ---------------------
    await card.getByRole("button", { name: "Tag", exact: true }).first().click();
    const doneButton = card.getByRole("button", { name: "Done" });
    await expect(doneButton).toBeVisible();

    await card.getByRole("button", { name: "More actions" }).first().click();
    await expect(doneButton).toHaveCount(0);
    await expect(card.getByText("Provider", { exact: true })).toHaveCount(0);

    // --- Only-untagged filter --------------------------------------------
    const untaggedFilter = card.getByRole("button", { name: /Only Untagged/ });
    await untaggedFilter.click();
    await expect(untaggedFilter).toHaveAttribute("aria-pressed", "true");

    // Every remaining row is untagged, so no row's meta label carries the
    // "Category / Tag" separator. A negative assertion, hence the explicit
    // wait for the feed to settle on its filtered render first.
    await expect(card.getByTestId("recent-tx-row").first()).toBeVisible();
    await expect(
      card.getByTestId("recent-tx-meta").filter({ hasText: "/" }),
    ).toHaveCount(0);

    await untaggedFilter.click();
    await expect(untaggedFilter).toHaveAttribute("aria-pressed", "false");

    // --- Phone width: the action bar spans the row, in at most two lines ---
    // The bar used to sit indented past the row's icon column, which left it
    // narrow enough to wrap seven actions onto three lines.
    await page.setViewportSize({ width: 390, height: 900 });
    const row = card.getByTestId("recent-tx-row").first();
    await expect(row).toBeVisible();
    await row.click();

    const actionBar = card.getByTestId("recent-tx-actions").first();
    await expect(actionBar).toBeVisible();
    const barLayout = await actionBar.evaluate((el) => {
      const buttons = [...el.children]
        .map((child) => child.getBoundingClientRect())
        .filter((box) => box.height > 0);
      const scrollRoot = el.closest("[data-scroll-root]") as HTMLElement;
      return {
        buttons: buttons.length,
        // Buttons sharing a rounded top offset are on the same wrapped line.
        lines: new Set(buttons.map((box) => Math.round(box.top))).size,
        insetStart:
          el.getBoundingClientRect().left -
          scrollRoot.getBoundingClientRect().left,
      };
    });
    expect(barLayout.buttons).toBeGreaterThanOrEqual(6);
    expect(barLayout.lines).toBeLessThanOrEqual(2);
    // Only the bar's own horizontal margin, not an icon-column indent.
    expect(barLayout.insetStart).toBeLessThanOrEqual(12);
    await row.click();
    await expect(actionBar).toHaveCount(0);

    // --- A date header is pinned flush to the top at every scroll offset ---
    expect(await worstUncoveredBandAboveDate(page)).toBeLessThanOrEqual(0.5);
  });

  test("tagging a row keeps the feed's scroll position", async ({ page }) => {
    await navigateTo(page, "/");

    const card = recentCard(page);
    await expect(card.getByTestId("recent-tx-row").first()).toBeVisible({
      timeout: 45_000,
    });

    // Page past the initial 20 rows, then back off the very bottom so the
    // editor opening and closing can't clamp scrollTop on its own.
    const rows = card.getByTestId("recent-tx-row");
    await scrollFeed(page, 4000);
    await expect
      .poll(async () => rows.count(), { timeout: 15_000 })
      .toBeGreaterThan(20);
    await scrollFeed(page, 2000);
    await scrollFeed(page, -400);

    const rowsBefore = await rows.count();
    expect(rowsBefore).toBeGreaterThan(20);
    const scrollBefore = await feedScrollTop(page);
    expect(scrollBefore).toBeGreaterThan(200);

    // Tag a row that is currently on screen.
    const editButtons = card.getByRole("button", { name: "Edit category / tag" });
    await editButtons.nth(rowsBefore - 3).click();

    const editor = card.getByTestId("recent-tx-editor");
    await expect(editor).toBeVisible();
    // The editor's first two buttons are the category and tag dropdowns.
    await editor.getByRole("button").nth(0).click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    await listbox.getByRole("option").first().click();
    await editor.getByRole("button", { name: "Done" }).click();
    await expect(editor).toHaveCount(0);

    // The write rewrites the cached transactions array; the feed must not
    // fall back to its first page (which would collapse scrollTop to 0).
    await expect.poll(async () => rows.count()).toBeGreaterThan(20);
    await expect
      .poll(async () => feedScrollTop(page), { timeout: 10_000 })
      .toBeGreaterThan(scrollBefore - 100);
  });
});
