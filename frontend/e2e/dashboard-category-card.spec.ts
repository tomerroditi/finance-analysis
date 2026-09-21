import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * The Categories dashboard card (id `category`) breaks spend down per
 * category. It is opt-in (hidden by default), so the layout is seeded before
 * the document loads rather than toggled through Settings — that also keeps
 * this spec write-free, so it can live in the `read-only` project.
 *
 * What is guarded here is the range strip: the card reads all time by default
 * and re-queries `/analytics/by-category` with a start/end window when another
 * preset is picked, which must narrow what the card totals.
 */
test.describe("Categories dashboard card", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
    // Opt the card in and hide every other one: the dashboard ships Categories
    // hidden (the Settings route to it is covered by
    // dashboard-chart-cards.spec.ts), and a lone card boots fast and renders
    // eagerly, so nothing here waits on a dozen unrelated analytics queries.
    await page.addInitScript(() =>
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          v: 5,
          order: ["category"],
          hidden: [
            "forecast", "insights", "budget", "recent", "recurring", "goals",
            "heatmap", "income_by_source", "income_expenses", "net_worth",
            "cash_flow", "refunds", "retirement",
          ],
        }),
      ),
    );
  });

  /** The visible card body (the dashboard ships mobile + desktop variants). */
  function cardContainer(page: Page) {
    return page.locator('[data-card-id="category"]').filter({ visible: true }).first();
  }

  /** The card's "Total Expenses" tile, as a number. */
  async function totalExpenses(page: Page): Promise<number> {
    const amount = cardContainer(page)
      .getByText("Total Expenses", { exact: true })
      .locator("xpath=following-sibling::p");
    const text = await amount.textContent();
    // formatCurrency emits "1,234 ₪" inside bidi isolates — keep the digits.
    return Number((text ?? "").replace(/[^0-9.]/g, ""));
  }

  test("reads all time by default and narrows to the picked range", async ({
    page,
  }) => {
    await page.goto("/");

    const card = cardContainer(page);
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(card.getByText("Expenses", { exact: true }).first()).toBeVisible();

    // --- All time is the default, and it asks for no window ---
    const allTime = card.getByRole("button", { name: "All time" });
    await expect(allTime).toHaveAttribute("aria-pressed", "true");
    // The tiles render at zero until the breakdown lands, so poll rather than
    // reading the total the instant the card mounts.
    await expect
      .poll(() => totalExpenses(page), { timeout: 45_000 })
      .toBeGreaterThan(0);
    const allTimeTotal = await totalExpenses(page);

    // --- Picking a range re-queries with an explicit window ---
    const windowed = page.waitForRequest(
      (req) =>
        req.url().includes("/analytics/by-category") &&
        req.url().includes("start=") &&
        req.url().includes("end="),
    );
    await card.getByRole("button", { name: "Last 3 months" }).click();
    await windowed;

    await expect(card.getByRole("button", { name: "Last 3 months" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(allTime).toHaveAttribute("aria-pressed", "false");

    // The demo household has years of history, so a quarter of it must total
    // less than the whole — the window is doing real work, not just relabeling.
    await expect
      .poll(() => totalExpenses(page), { timeout: 30_000 })
      .toBeLessThan(allTimeTotal);

    // --- Every preset keeps the card rendered (no crash on an empty window) ---
    for (const preset of ["Last month", "This year", "Last 12 months"]) {
      await card.getByRole("button", { name: preset }).click();
      await expect(card.getByRole("button", { name: preset })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      await expect(card.getByText("Expenses", { exact: true }).first()).toBeVisible();
    }

    // --- And back to all time restores the full total ---
    await allTime.click();
    await expect.poll(() => totalExpenses(page), { timeout: 30_000 }).toBe(allTimeTotal);
  });
});
