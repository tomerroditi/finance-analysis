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
      "cash_flow",
      "category",
      "income_by_source",
      "income_expenses",
      "net_worth",
    ],
    v: 3,
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
    await expect(cards.first()).toBeVisible({ timeout: 45_000 });
    const before = await cards.count();
    const dismissedKey = await cards.first().getAttribute("data-insight-key");
    expect(dismissedKey).toBeTruthy();

    // --- dismiss: the card goes, the rest stay ---
    await cards.first().getByTestId("insight-dismiss").click();
    await expect(page.locator(`[data-insight-key="${dismissedKey}"]`)).toHaveCount(0);
    await expect(cards).toHaveCount(before - 1);

    // --- it is a real write, not just local state ---
    await page.reload();
    await expect(cards.first()).toBeVisible({ timeout: 45_000 });
    await expect(page.locator(`[data-insight-key="${dismissedKey}"]`)).toHaveCount(0);

    // --- undo brings it back ---
    await cards.first().getByTestId("insight-dismiss").click();
    const undo = page.getByRole("button", { name: /undo|שחזר/i });
    await expect(undo).toBeVisible();
    await undo.click();
    await expect(page.getByTestId("insight-card").first()).toBeVisible();
    await expect(cards).toHaveCount(before - 1);
  });
});
