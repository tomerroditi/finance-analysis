import { test, expect, type Locator, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Dashboard "Recent Transactions" card — the row action bar, the
 * only-untagged filter and scroll retention.
 *
 * Covers four regressions the card shipped with:
 *  1. Collapsing a row's action bar left the category/tag editor (and the
 *     details sheet) stranded on screen under a row with no bar.
 *  2. Tagging a row reset the feed's page size to the first 20 rows, throwing
 *     the reader back to the top of the card.
 *  3. The card offered only three of the actions the transactions table has.
 *  4. Nothing in the card said where the money moved (account / card).
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
