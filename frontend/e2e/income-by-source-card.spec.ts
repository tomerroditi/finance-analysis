import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * The "Income by source" dashboard card (id `income_by_source`) renders a
 * Plotly donut + a breakdown table with a Total row, plus range-preset
 * buttons (All time / This year / Last 12 months / Custom). It's visible by
 * default on the dashboard route; Demo Mode supplies sample income data so the
 * donut + table render. This spec guards that the card mounts and that
 * switching range presets doesn't crash it.
 */
test.describe("Income by source dashboard card", () => {
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

  /**
   * Locate the card container by its title, then climb to the enclosing
   * card div so we can scope the donut/table lookups (the dashboard renders
   * several other Plotly charts). The dashboard ships mobile + desktop layout
   * variants simultaneously, so we filter to the visible instance.
   */
  function cardContainer(page: Page) {
    return page
      .locator("div")
      .filter({ has: page.getByText("Income by source", { exact: true }) })
      .filter({ has: page.locator(".js-plotly-plot") })
      .filter({ visible: true })
      .last();
  }

  test("renders the title, donut, and Total row", async ({ page }) => {
    await navigateTo(page, "/");

    // Card title.
    await expect(
      page.getByText("Income by source", { exact: true }).first(),
    ).toBeVisible({ timeout: 45_000 });

    const card = cardContainer(page);

    // Donut renders inside the card.
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });

    // Breakdown table has a Total row.
    await expect(card.getByText("Total", { exact: true }).first()).toBeVisible();
  });

  test("switching to Last 12 months keeps the card rendered", async ({ page }) => {
    await navigateTo(page, "/");

    await expect(
      page.getByText("Income by source", { exact: true }).first(),
    ).toBeVisible({ timeout: 45_000 });

    const card = cardContainer(page);
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });

    // Click the "Last 12 months" range preset (scoped to the card).
    await card
      .getByRole("button", { name: "Last 12 months" })
      .first()
      .click();

    // The card must still render its donut after the range change (no crash).
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(card.getByText("Total", { exact: true }).first()).toBeVisible();
  });

  test("Breakdown toggle collapses and restores the table", async ({ page }) => {
    await navigateTo(page, "/");

    await expect(
      page.getByText("Income by source", { exact: true }).first(),
    ).toBeVisible({ timeout: 45_000 });

    const card = cardContainer(page);
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 15_000,
    });

    // Table starts expanded.
    await expect(card.locator("table").first()).toBeVisible();

    const toggle = card.getByRole("button", { name: "Breakdown" }).first();

    // Collapse: the table is removed but the donut stays.
    await toggle.click();
    await expect(card.locator("table")).toHaveCount(0);
    await expect(card.locator(".js-plotly-plot").first()).toBeVisible();

    // Expand again: the table comes back.
    await toggle.click();
    await expect(card.locator("table").first()).toBeVisible();
  });
});
