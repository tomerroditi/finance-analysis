import {
  test,
  expect,
  request,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { enableDemoMode, API_BASE } from "./helpers";

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
      JSON.stringify({
        v: 2,
        order: ["goals", "budget", "recent"],
        hidden: [],
      }),
    );
  });
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
}

/** `YYYY-MM` for the month `count` months before now. */
function monthsAgo(count: number): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - count, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** The goal row container, found by walking up from the goal's name. */
function goalRow(page: Page, name: string) {
  return page
    .getByText(name, { exact: true })
    .locator("xpath=ancestor::div[contains(@class,'group')][1]");
}

/**
 * End-to-end coverage for the savings-goal waterfall.
 *
 * Goals are seeded through the API (Demo Mode writes to the isolated demo DB)
 * with explicit priorities, then the rendered dashboard card is checked in one
 * page load: funding order, the achieved/closed states, and the SQLite-boolean
 * guard that once leaked a literal "0" beside a goal's name.
 */
test.describe("Savings goals", () => {
  let ctx: APIRequestContext;
  const created: number[] = [];

  /** Create a goal and remember its id for cleanup. */
  async function createGoal(body: Record<string, unknown>) {
    const res = await ctx.post(`${API_BASE}/savings-goals/`, { data: body });
    expect(res.ok()).toBeTruthy();
    const goals = await res.json();
    const goal = goals.find((g: { name: string }) => g.name === body.name);
    created.push(goal.id);
    return goal;
  }

  test.beforeAll(async () => {
    // This bypasses the browser (Node-side `request` fixture), so it must
    // declare the demo header itself — Demo Mode is per-client now, and a
    // header-less request would create these throwaway goals in the real
    // database instead of the demo one each test's own page browses.
    ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });
    await ctx.post(`${API_BASE}/testing/demo/prepare`);

    // Both goals start far enough back to have accrued real allocations, so
    // the budget-page assertion below has something to find. The 1-per-month
    // cap keeps `funded` dominated by `opening_balance`, which is what makes
    // the achieved / in-progress split deterministic against demo data whose
    // monthly surplus we do not control.
    await createGoal({
      name: "E2E In Progress Goal",
      target_amount: 10000,
      opening_balance: 2500,
      monthly_cap: 1,
      start_month: monthsAgo(10),
    });
    await createGoal({
      name: "E2E Achieved Goal",
      target_amount: 5000,
      opening_balance: 5000,
      monthly_cap: 1,
      start_month: monthsAgo(10),
    });
  });

  test.afterAll(async () => {
    for (const id of created) {
      await ctx.delete(`${API_BASE}/savings-goals/${id}`).catch(() => {});
    }
    await ctx.dispose();
  });

  // Demo Mode itself is per-page (localStorage), so it's seeded per-test
  // here rather than alongside the beforeAll goal seeding above.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("renders the waterfall with per-goal state on one dashboard load", async ({
    page,
  }) => {
    await openDashboardWithGoals(page);

    const inProgressName = page.getByText("E2E In Progress Goal", {
      exact: true,
    });
    const achievedName = page.getByText("E2E Achieved Goal", { exact: true });
    await expect(inProgressName).toBeVisible({ timeout: 30_000 });
    await expect(achievedName).toBeVisible();

    // --- funding order -------------------------------------------------
    // Goals render in priority order, each labelled with its position.
    const inProgressRow = goalRow(page, "E2E In Progress Goal");
    const achievedRow = goalRow(page, "E2E Achieved Goal");
    await expect(inProgressRow.getByText("#1")).toBeVisible();
    await expect(achievedRow.getByText("#2")).toBeVisible();

    // The top goal can't move up and the bottom one can't move down.
    await expect(
      inProgressRow.getByRole("button", { name: /move up/i }),
    ).toBeDisabled();
    await expect(
      achievedRow.getByRole("button", { name: /move down/i }),
    ).toBeDisabled();

    // --- achieved state ------------------------------------------------
    // The check icon marks only the achieved goal, and it carries the
    // "Achieved" status copy in its own emerald span.
    await expect(achievedRow.locator("svg.lucide-check")).toHaveCount(1);
    await expect(inProgressRow.locator("svg.lucide-check")).toHaveCount(0);
    await expect(achievedRow.locator("span.text-emerald-400")).toBeVisible();

    // --- SQLite boolean guard ------------------------------------------
    // `is_achieved` comes back as a 0/1 integer. A bare `{0 && <Check/>}`
    // renders the literal string "0" directly before the goal name, so the
    // in-progress row's header must read exactly rank + name.
    const header = inProgressRow.locator("xpath=.//p[1]/..");
    await expect(header).toHaveText("#1E2E In Progress Goal");
  });

  test("reordering moves a goal up the waterfall", async ({ page }) => {
    await openDashboardWithGoals(page);
    await expect(
      page.getByText("E2E Achieved Goal", { exact: true }),
    ).toBeVisible({
      timeout: 30_000,
    });

    await goalRow(page, "E2E Achieved Goal")
      .getByRole("button", { name: /move up/i })
      .click();

    // The promoted goal takes position 1 and the demoted one drops to 2.
    await expect(
      goalRow(page, "E2E Achieved Goal").getByText("#1"),
    ).toBeVisible();
    await expect(
      goalRow(page, "E2E In Progress Goal").getByText("#2"),
    ).toBeVisible();

    // Restore the original order so the suite is order-independent.
    await goalRow(page, "E2E In Progress Goal")
      .getByRole("button", { name: /move up/i })
      .click();
    await expect(
      goalRow(page, "E2E In Progress Goal").getByText("#1"),
    ).toBeVisible();
  });

  test("the budget month shows what was directed into goals", async ({
    page,
  }) => {
    // The current month is usually mid-flight and often nets negative, so the
    // section legitimately has nothing to show there. Ask the backend which
    // recent month actually funded a goal and drive the page to that one.
    let monthsBack = -1;
    let expected: { goals: { name: string }[] } | null = null;
    const now = new Date();
    for (let back = 0; back < 12; back += 1) {
      const d = new Date(now.getFullYear(), now.getMonth() - back, 1);
      const res = await ctx.get(
        `${API_BASE}/savings-goals/allocations/${d.getFullYear()}/${d.getMonth() + 1}`,
      );
      const body = await res.json();
      if (body.goals.length > 0) {
        monthsBack = back;
        expected = body;
        break;
      }
    }
    expect(
      monthsBack,
      "demo data should fund a goal in at least one of the last 12 months",
    ).toBeGreaterThanOrEqual(0);

    await page.goto("/budget");
    await page.waitForLoadState("domcontentloaded");
    for (let i = 0; i < monthsBack; i += 1) {
      await page
        .getByRole("button", { name: /previous/i })
        .first()
        .click();
    }

    await expect(
      page.getByText("Into savings goals", { exact: true }),
    ).toBeVisible({ timeout: 30_000 });
    for (const goal of expected!.goals) {
      await expect(
        page.getByText(goal.name, { exact: true }).first(),
      ).toBeVisible();
    }
  });
});
