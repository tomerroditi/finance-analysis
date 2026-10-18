import { test, expect } from "@playwright/test";
import { enableDemoMode, resetDemoData } from "./helpers";

/**
 * The insights strip lets the user wave a card away with the small X in its
 * corner. The dismissal is a backend write keyed to what the card is about, so
 * it has to survive a reload — and the undo in the strip header has to bring
 * the card back.
 *
 * `insights` ships beta/hidden, so the layout is seeded. `forecast` and
 * `recurring` are hidden on purpose: the strip drops the cards those two
 * panels already carry, so hiding them is what gives this test cards to work
 * with on demo data.
 */
test.describe("Dashboard insight dismissal", () => {
  const LAYOUT = {
    order: ["insights", "budget", "recent", "heatmap"],
    hidden: [
      "forecast",
      "recurring",
      "goals",
      "category",
      "income_expenses",
      "net_worth",
    ],
    v: 4,
  };

  // Mutating spec: the dismissal writes to the shared demo DB, so the file
  // starts from pristine data of its own accord.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
    await page.addInitScript((layout) => {
      window.localStorage.setItem("fa.dashboard.layout", JSON.stringify(layout));
    }, LAYOUT);
  });

  test("an insight can be dismissed, survives a reload, and can be undone", async ({
    page,
  }) => {
    await page.goto("/");

    const cards = page.getByTestId("insight-card");
    await expect(cards.nth(1)).toBeVisible({ timeout: 45_000 });
    const before = await cards.count();

    // Let the React Query persister's 1 s throttle write this list to
    // IndexedDB *before* anything is dismissed. Reloading into that stale
    // snapshot is exactly how a dismissed card used to come back: hydration
    // is instant and the global five-minute staleTime meant nothing
    // refetched. There is no event to await here — it is a timer.
    await page.waitForTimeout(1500);
    const firstKey = await cards.nth(0).getAttribute("data-insight-key");
    const secondKey = await cards.nth(1).getAttribute("data-insight-key");
    expect(firstKey).toBeTruthy();
    expect(secondKey).toBeTruthy();
    const first = page.locator(`[data-insight-key="${firstKey}"]`);
    const second = page.locator(`[data-insight-key="${secondKey}"]`);

    // --- dismiss: the card goes, the rest stay ---
    await first.getByTestId("insight-dismiss").click();
    await expect(first).toHaveCount(0);
    await expect(second).toBeVisible();
    await second.getByTestId("insight-dismiss").click();
    await expect(second).toHaveCount(0);

    // --- undo walks back through every dismissal, most recent first, and
    // puts each card back at once rather than after the insights recompute ---
    const undo = page.getByTestId("insight-undo");
    await undo.click();
    await expect(second).toBeVisible({ timeout: 1_000 });
    await expect(first).toHaveCount(0);
    await undo.click();
    await expect(first).toBeVisible({ timeout: 1_000 });
    await expect(undo).toHaveCount(0);
    await expect(cards).toHaveCount(before);

    // --- the undos were real writes ---
    await page.reload();
    await expect(first).toBeVisible({ timeout: 45_000 });
    await expect(second).toBeVisible();

    // --- and so is a dismissal ---
    await first.getByTestId("insight-dismiss").click();
    await expect(first).toHaveCount(0);
    await expect(undo).toBeVisible();
    await page.reload();
    await expect(second).toBeVisible({ timeout: 45_000 });
    await expect(first).toHaveCount(0);
  });
});
