import { test, expect, request } from "@playwright/test";
import { API_BASE, enableDemoMode, resetDemoData } from "./helpers";

/**
 * E2E coverage for the Israeli-finance-app feature additions:
 * the "This Month" cash-flow forecast hero, insight cards,
 * subscriptions/recurring panel, savings goals, and the spending heatmap.
 *
 * The forecast, insights and goals cards are beta and hidden by default,
 * so the test seeds a layout
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

  // Seed a current (v4, so no migration) layout with the beta forecast /
  // insights / goals sections visible so they render alongside recurring.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          v: 4,
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
          hidden: ["category"],
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

    // --- Income is what recurring streams still owe, not a recent average.
    // The demo household is paid two monthly salaries, so the forecast must
    // reach them by detection; an averaged baseline would carry the annual
    // bonus into every month it sat in the window.
    const forecast = await (
      await request.newContext()
    ).get(`${API_BASE}/analytics/cash-flow-forecast`, {
      headers: { "X-FAD-Demo": "1" },
    });
    expect(forecast.ok()).toBeTruthy();
    const data = await forecast.json();
    expect(data.income_basis).toBe("recurring");
    expect(data.expected_income).toBeCloseTo(
      data.actual_income + data.recurring_income_due,
      2,
    );
    // Late in the month every salary may already be paid, leaving nothing
    // due — so the streams and the caption are only asserted while one is.
    expect(data.recurring_income_items.length > 0).toBe(data.recurring_income_due > 0);
    // Every stream it leans on is due inside this month.
    for (const item of data.recurring_income_items) {
      expect(item.expected_date.slice(0, 7)).toBe(data.month);
    }
    // The card says where the number came from.
    if (data.recurring_income_due > 0) {
      await expect(page.getByTestId("forecast-income-due")).toBeVisible();
    }

    // The subscriptions / recurring panel. It sits below the four eager
    // cards, so it mounts as it scrolls near.
    await page.locator('[data-card-id="recurring"]').scrollIntoViewIfNeeded();
    await expect(
      page.getByText(/Subscriptions & Recurring/i).first(),
    ).toBeVisible({
      timeout: 45_000,
    });

    // The savings goals panel and spending calendar.
    await expect(page.getByText(/Savings Goals/i).first()).toBeVisible({
      timeout: 45_000,
    });
    await page.locator('[data-card-id="heatmap"]').scrollIntoViewIfNeeded();
    await expect(page.getByText(/Spending Calendar/i).first()).toBeVisible({ timeout: 45_000 });

    // Pressing a day shows that day's spend; pressing it again clears it.
    const heatmap = page.locator('[data-card-id="heatmap"]');
    const firstDay = heatmap.getByRole("button", { name: /^1: / }).last();
    await firstDay.click();
    await expect(firstDay).toHaveAttribute("aria-pressed", "true");
    const detail = heatmap.getByTestId("heatmap-day-detail");
    await expect(detail).toContainText(/charge/);
    await expect(detail).toContainText("₪");
    await firstDay.click();
    await expect(detail).toHaveCount(0);

    // The add-goal editor modal opens.
    await page
      .getByRole("button", { name: /Add goal/i })
      .first()
      .click();
    await expect(page.getByText(/New savings goal/i)).toBeVisible();
    await expect(page.getByPlaceholder(/Vacation/i)).toBeVisible();
  });

  // Its own test because it writes: confirming a candidate stores a verdict
  // in the backend, which would leak into the read-only journey above.
  test("a detected subscription only counts once it is confirmed", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });
    await page.locator('[data-card-id="recurring"]').scrollIntoViewIfNeeded();
    await expect(
      page.getByText(/Subscriptions & Recurring/i).first(),
    ).toBeVisible({ timeout: 45_000 });

    // Detection alone leaves every candidate in the review block — nothing is
    // treated as a recurring charge yet.
    const pending = page.getByTestId("recurring-pending-item");
    await expect(pending.first()).toBeVisible({ timeout: 45_000 });
    const pendingBefore = await pending.count();
    await expect(page.getByTestId("recurring-confirmed-item")).toHaveCount(0);
    await expect(page.getByText(/Needs review/i).first()).toBeVisible();

    // A charge that stopped billing is history, not a commitment: the demo
    // data's lapsed national-insurance run is detected but kept off the card
    // until it is asked for. The toggle names how many are waiting.
    const endedToggle = page.getByTestId("recurring-toggle-ended");
    await expect(endedToggle).toContainText("1");
    await expect(page.getByText(/BITUACH LEUMI/i)).toHaveCount(0);

    await endedToggle.click();
    await expect(page.getByText(/BITUACH LEUMI/i).first()).toBeVisible();
    await expect(pending).toHaveCount(pendingBefore + 1);

    await endedToggle.click();
    await expect(page.getByText(/BITUACH LEUMI/i)).toHaveCount(0);

    // Confirming the first one moves it into the list of real charges.
    // --- The refresh after a verdict reaches only what reads verdicts ---
    // The budget Overview is refetched; the transaction history, the
    // savings goals and the balances are not.
    await page.waitForLoadState("networkidle");
    const afterVerdict: string[] = [];
    const record = (req: { method(): string; url(): string }) => {
      if (req.method() === "GET" && req.url().includes("/api/")) afterVerdict.push(req.url());
    };
    page.on("request", record);
    const overviewRefetched = page.waitForRequest((req) =>
      req.url().includes("/api/budget/overview/"),
    );
    await pending
      .first()
      .getByRole("button", { name: /Confirm .* as recurring/i })
      .click();

    await expect(page.getByTestId("recurring-confirmed-item")).toHaveCount(1);
    await expect(pending).toHaveCount(pendingBefore - 1);
    await overviewRefetched;
    await page.waitForTimeout(1500);
    page.off("request", record);
    for (const path of ["/api/transactions/", "/api/savings-goals/", "/api/cash-balances/"]) {
      expect(afterVerdict.filter((url) => url.includes(path))).toEqual([]);
    }

    // Dismissing another one hides it behind the "show dismissed" toggle.
    await pending
      .first()
      .getByRole("button", { name: /Not a recurring charge/i })
      .click();

    await expect(pending).toHaveCount(pendingBefore - 2);
    await page.getByRole("button", { name: /Show dismissed/i }).click();
    const dismissedRows = page.getByTestId("recurring-dismissed-item");
    await expect(dismissedRows).toHaveCount(1);
    // The row carries the evidence, which is what says whether ruling the
    // charge out was a mistake — a bare merchant label would not.
    await expect(dismissedRows.first()).toContainText(/charges|bills/i);

    // A confirmed charge can be dropped outright rather than only sent back
    // to review — it joins the dismissed list, not the pending one.
    await page.getByTestId("recurring-remove").first().click();
    await expect(page.getByTestId("recurring-confirmed-item")).toHaveCount(0);
    await expect(dismissedRows).toHaveCount(2);
    await expect(pending).toHaveCount(pendingBefore - 2);

    // Nothing here is a dead end: a dismissal restores straight back to
    // review, which is the way out of having ruled one out by mistake.
    await dismissedRows
      .first()
      .getByRole("button", { name: /Restore/i })
      .click();
    await expect(dismissedRows).toHaveCount(1);
    await expect(pending).toHaveCount(pendingBefore - 1);

    // A confirmed row is two lines on a phone whatever its status: the demo
    // data's repriced arnona and home insurance carry an icon chip that names
    // the direction, not a worded badge that wrapped the next date away.
    await page.getByRole("button", { name: /Confirm all/i }).click();
    await expect(pending).toHaveCount(0);
    await page.setViewportSize({ width: 360, height: 800 });
    await expect(
      page.getByRole("img", { name: /Price went (up|down) by/ }).first(),
    ).toBeVisible();
    await expect(page.getByText("Price changed")).toHaveCount(0);
    const metaHeights = await page
      .getByTestId("recurring-item-meta")
      .evaluateAll((lines) =>
        lines.map((line) => line.getBoundingClientRect().height),
      );
    expect(metaHeights.length).toBeGreaterThan(0);
    for (const height of metaHeights) expect(height).toBeLessThan(24);
  });
});
