import { test, expect, request, type APIRequestContext, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, API_BASE } from "./helpers";

/**
 * The Goals card is a "beta" dashboard widget, hidden by default
 * (useDashboardLayout.ts). Make it visible by seeding the layout in
 * localStorage (key "fa.dashboard.layout", version 2 to skip the
 * beta-hide migration) before the dashboard renders, then reload.
 */
async function openDashboardWithGoals(page: Page) {
  await page.goto("about:blank");
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
    localStorage.setItem(
      "fa.dashboard.layout",
      JSON.stringify({ v: 2, order: ["goals", "budget", "recent"], hidden: [] }),
    );
  });
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
}

/**
 * Regression coverage for GoalsSection.tsx.
 *
 * `is_achieved` comes back from the backend as a SQLite-style truthy value.
 * The fix guards the achieved check icon with `!!goal.is_achieved` so a falsy
 * `0` can never leak into the JSX as the literal string "0" next to a goal.
 * The test seeds goals (Demo Mode writes to the isolated demo DB) — one
 * achieved, one in-progress — and asserts the rendered list on one dashboard
 * load (both scenarios read the same rendered card).
 */
test.describe("Savings goal achieved checkmark", () => {
  let ctx: APIRequestContext;
  const created: number[] = [];

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();

    ctx = await request.newContext();

    // In-progress goal: current < target → is_achieved falsy.
    const inProgress = await ctx.post(`${API_BASE}/savings-goals/`, {
      data: { name: "E2E In Progress Goal", target_amount: 10000, current_amount: 2500 },
    });
    created.push((await inProgress.json()).id);

    // Achieved goal: current >= target → is_achieved truthy.
    const achieved = await ctx.post(`${API_BASE}/savings-goals/`, {
      data: { name: "E2E Achieved Goal", target_amount: 5000, current_amount: 5000 },
    });
    created.push((await achieved.json()).id);
  });

  test.afterAll(async ({ browser }) => {
    for (const id of created) {
      await ctx.delete(`${API_BASE}/savings-goals/${id}`).catch(() => {});
    }
    await ctx.dispose();

    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test("renders both goals without a stray '0'; check icon only on the achieved goal", async ({ page }) => {
    await openDashboardWithGoals(page);

    const inProgressName = page.getByText("E2E In Progress Goal");
    const achievedName = page.getByText("E2E Achieved Goal");
    await expect(inProgressName).toBeVisible({ timeout: 30_000 });
    await expect(achievedName).toBeVisible();

    // The bug rendered the SQLite boolean `0` as a text node directly before
    // the goal name (`{0 && <Check/>}` → "0"). Walk up to each goal's row
    // header and assert no bare "0" character sits next to the name.
    const inProgressRow = inProgressName.locator(
      "xpath=ancestor::*[contains(@class,'group')][1]",
    );
    const headerText = (await inProgressRow.locator("xpath=.//p[1]/..").first().textContent()) ?? "";
    // The name itself must be present, and there must be no standalone "0"
    // immediately adjacent to it (e.g. "0E2E In Progress Goal").
    expect(headerText).toContain("E2E In Progress Goal");
    expect(headerText).not.toMatch(/(^|\s)0E2E In Progress Goal/);
    expect(headerText.replace("E2E In Progress Goal", "").trim()).not.toBe("0");

    // The achieved goal's row header contains the lucide check icon; the
    // in-progress one does not. The check lives in the same flex container
    // as the goal name (GoalsSection: `{!!goal.is_achieved && <Check .../>}`).
    const achievedHeader = achievedName.locator("xpath=ancestor::div[1]");
    const inProgressHeader = inProgressName.locator("xpath=ancestor::div[1]");

    await expect(achievedHeader.locator("svg.lucide-check")).toHaveCount(1);
    await expect(inProgressHeader.locator("svg.lucide-check")).toHaveCount(0);

    // And the achieved goal surfaces the "Achieved" status copy (the emerald
    // status span, not the goal name which happens to contain "Achieved").
    await expect(
      achievedName
        .locator("xpath=ancestor::div[contains(@class,'group')][1]")
        .locator("span.text-emerald-400"),
    ).toBeVisible();
  });
});
