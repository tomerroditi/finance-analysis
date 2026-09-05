import { test, expect } from "@playwright/test";
import { enableDemoMode, resetDemoData } from "./helpers";

/**
 * E2E coverage for the Israeli-finance-app feature additions:
 * the "This Month" cash-flow forecast hero, insight cards,
 * subscriptions/recurring panel, savings goals, and the spending heatmap.
 *
 * These cards are beta and hidden by default, so the test seeds a layout
 * with every card visible before navigating. All checks are read-only
 * assertions (plus opening the add-goal modal) against one rendered
 * dashboard, so they share a single (expensive) dashboard load.
 */
test.describe("Dashboard — forecast, recurring, goals", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  // Seed a current (v3, so no migration) layout with the beta forecast /
  // insights / recurring / goals sections visible so they render.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          v: 3,
          order: [
            "forecast",
            "insights",
            "budget",
            "recent",
            "recurring",
            "goals",
            "heatmap",
            "income_expenses",
            "net_worth",
          ],
          hidden: ["cash_flow", "category"],
        }),
      );
    });
  });

  test("forecast hero, recurring panel, goals panel, calendar, and add-goal modal on one load", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // The "This Month" cash-flow forecast hero.
    await expect(page.getByText("This Month").first()).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByText(/Safe to spend/i).first()).toBeVisible();
    await expect(
      page.getByText(/Projected end balance/i).first(),
    ).toBeVisible();

    // The subscriptions / recurring panel.
    await expect(
      page.getByText(/Subscriptions & Recurring/i).first(),
    ).toBeVisible({
      timeout: 45_000,
    });

    // The savings goals panel and spending calendar.
    await expect(page.getByText(/Savings Goals/i).first()).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByText(/Spending Calendar/i).first()).toBeVisible();

    // The add-goal editor modal opens.
    await page
      .getByRole("button", { name: /Add goal/i })
      .first()
      .click();
    await expect(page.getByText(/New savings goal/i)).toBeVisible();
    await expect(page.getByPlaceholder(/Vacation/i)).toBeVisible();
  });
});
