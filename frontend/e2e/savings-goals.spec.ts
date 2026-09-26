import {
  test,
  expect,
  request,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { enableDemoMode, API_BASE } from "./helpers";

/**
 * The Goals card is default-visible since layout v5, but this spec asserts on
 * a card near the top of the page, so the layout is still seeded explicitly:
 * it pins the card first and keeps the rest of the dashboard out of the way,
 * which is what keeps the assertions below independent of the default order.
 */
async function openDashboardWithGoals(page: Page) {
  await page.goto("about:blank");
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
    localStorage.setItem(
      "fa.dashboard.layout",
      JSON.stringify({
        v: 5,
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

/**
 * The goal row container, found by walking up from the goal's name.
 *
 * Scoped to the waterfall list: the card's history chart legends the same
 * names, so an unscoped text lookup matches twice.
 */
function goalRow(page: Page, name: string) {
  return goalName(page, name).locator(
    "xpath=ancestor::div[contains(@class,'group')][1]",
  );
}

/** The goal's name as the waterfall list renders it (never the chart legend). */
function goalName(page: Page, name: string) {
  return page.getByTestId("goals-list").getByText(name, { exact: true });
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
    await ctx.post(`${API_BASE}/testing/demo/reset`);

    // Demo data now ships the Cohens' own three goals. This spec asserts
    // absolute waterfall positions, so clear them first — otherwise the
    // goals created below land at #4 and #5. The teardown restores the
    // snapshot, so the demo's goals come back for the next run.
    const seeded = await (await ctx.get(`${API_BASE}/savings-goals/`)).json();
    for (const goal of seeded as { id: number }[]) {
      await ctx.delete(`${API_BASE}/savings-goals/${goal.id}`);
    }

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

    // Enough goals to take the waterfall past its height cap, which is what
    // the journey test's scroll-region check needs to see. They open already
    // at their target, so they draw nothing from any month's surplus and
    // change no other reading — and they sort below the two above, leaving
    // the absolute positions asserted there intact.
    for (let i = 0; i < 4; i++) {
      await createGoal({
        name: `E2E Filler ${i}`,
        target_amount: 1000,
        opening_balance: 1000,
        monthly_cap: 1,
      });
    }
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

    const inProgressName = goalName(page, "E2E In Progress Goal");
    const achievedName = goalName(page, "E2E Achieved Goal");
    await expect(inProgressName).toBeVisible({ timeout: 30_000 });
    await expect(achievedName).toBeVisible();

    // --- funding order -------------------------------------------------
    // Goals render in priority order, each labelled with its position.
    const inProgressRow = goalRow(page, "E2E In Progress Goal");
    const achievedRow = goalRow(page, "E2E Achieved Goal");
    await expect(inProgressRow.getByText("#1")).toBeVisible();
    await expect(achievedRow.getByText("#2")).toBeVisible();

    // The top goal can't move up and the bottom one can't move down. The
    // bottom is the last filler, which sorts below the two goals asserted
    // above.
    await expect(
      inProgressRow.getByRole("button", { name: /move up/i }),
    ).toBeDisabled();
    await expect(
      achievedRow.getByRole("button", { name: /move down/i }),
    ).toBeEnabled();
    await expect(
      goalRow(page, "E2E Filler 3").getByRole("button", { name: /move down/i }),
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

    // --- month-by-month history ----------------------------------------
    // The card carries the ledger over time, not just today's standing: a
    // stacked bar per month for the goals and a separate panel for the pool
    // (a monthly flow and a standing balance must not share one y-scale).
    // It opens collapsed, so the standings stay the card's first screen.
    const history = page.getByTestId("goals-history-chart");
    await expect(history).toBeHidden();
    const historyToggle = page
      .getByTestId("goals-history")
      .getByRole("button", { name: /month by month/i });
    await expect(historyToggle).toHaveAttribute("aria-expanded", "false");
    await historyToggle.click();
    await expect(history).toBeVisible();
    // The unearmarked pool stacks on the same bars as the goals.
    const poolSeries = history.getByRole("button", { name: "Free cash" });
    await expect(poolSeries).toBeVisible();
    await expect(poolSeries).toHaveAttribute("aria-pressed", "true");

    // --- focusing the chart from its legend -----------------------------
    // The pool is a standing balance and the allocations are monthly flows,
    // so the pool towers over them. A click hides it and the axis refits to
    // what is left, which is the whole point of the legend being clickable.
    // The largest number any axis tick carries — the value axis's top, since
    // the month labels ("11.25") are orders of magnitude smaller. Read this
    // way because Recharts renders tick text outside the axis group, so a
    // `.yAxis text` lookup finds nothing.
    const axisTop = async () => {
      const ticks = await history
        .locator(".recharts-cartesian-axis-tick-value")
        .allTextContents();
      const values = ticks.map((text) => {
        const digits = Number(text.replace(/[^\d.-]/g, ""));
        if (Number.isNaN(digits)) return 0;
        if (/M/i.test(text)) return digits * 1_000_000;
        return /K/i.test(text) ? digits * 1_000 : digits;
      });
      return Math.max(...values);
    };
    const withPool = await axisTop();
    await poolSeries.click();
    await expect(poolSeries).toHaveAttribute("aria-pressed", "false");
    await expect
      .poll(async () => await axisTop(), { timeout: 10_000 })
      .toBeLessThan(withPool);

    // A double-click narrows to one goal; the rest dim rather than vanish, so
    // the way back is where the way out was.
    const goalSeries = history.getByRole("button", {
      name: "E2E In Progress Goal",
    });
    await goalSeries.dblclick();
    await expect(goalSeries).toHaveAttribute("aria-pressed", "true");
    // The pool stays hidden rather than springing back: the double-click
    // narrowed to the goal, it did not undo the click before it.
    await expect(poolSeries).toHaveAttribute("aria-pressed", "false");

    // Double-clicking the series it narrowed to brings the rest back.
    await goalSeries.dblclick();
    await expect(poolSeries).toHaveAttribute("aria-pressed", "true");
    // A goal that took money in the window is legended by name; the achieved
    // one never drew on the waterfall (it opened already full), so it earns
    // no series — a legend entry with no mark names nothing.
    await expect(
      history.getByRole("button", { name: "E2E In Progress Goal" }),
    ).toBeVisible();
    await expect(
      history.getByRole("button", { name: "E2E Achieved Goal" }),
    ).toHaveCount(0);

    // Narrowing the window re-renders the chart rather than emptying it.
    // Scoped to the panel: other cards carry range chips of their own.
    await page
      .getByTestId("goals-history")
      .getByRole("button", { name: "6M" })
      .click();
    await expect(history).toBeVisible();

    // The toggle closes what it opened, range chips and all.
    await historyToggle.click();
    await expect(history).toBeHidden();
    await expect(
      page.getByTestId("goals-history").getByRole("button", { name: "6M" }),
    ).toBeHidden();

    // --- free-cash pool ------------------------------------------------
    // The unearmarked remainder renders below the waterfall and outside any
    // goal row — it is the buffer a deficit month drains before the engine
    // reaches back into the goals themselves.
    // Found by its own handle: the chart legend carries the same words.
    const pool = page.getByTestId("goals-free-cash");
    await expect(pool).toBeVisible();
    await expect(
      pool.locator("xpath=ancestor::div[contains(@class,'group')]"),
    ).toHaveCount(0);

    // What it reports must reconcile: pool + earmarked = liquid.
    const reported = await (
      await ctx.get(`${API_BASE}/savings-goals/free-cash`)
    ).json();
    expect(reported.has_goals).toBe(true);
    expect(reported.free_cash + reported.earmarked).toBeCloseTo(
      reported.liquid,
      2,
    );

    // --- the waterfall is a capped scroll region ------------------------
    // A household that keeps many goals must not push the free-cash row and
    // the history panel down the page — the list scrolls inside the card
    // instead. The seeded fillers take it well past the cap, which is what
    // turns the list into a scroll region at all: one that would scroll by
    // only a hair stays a plain block, so a drag on it still scrolls the page.
    const list = page.getByTestId("goals-list");
    const geometry = await list.evaluate((el) => ({
      client: el.clientHeight,
      scroll: el.scrollHeight,
      overflowY: getComputedStyle(el).overflowY,
    }));
    // The list is taller than the window it shows, and that window is the cap
    // rather than whatever the rows happen to add up to.
    expect(geometry.overflowY).toBe("auto");
    expect(geometry.scroll).toBeGreaterThan(geometry.client);
    expect(geometry.client).toBeLessThanOrEqual(26 * 16 + 2);

    // Scrolling the list moves the rows, not the card's chrome: the free-cash
    // row and the history panel below it stay put.
    const beforeScroll = await page.getByTestId("goals-history").boundingBox();
    await list.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    const afterScroll = await page.getByTestId("goals-history").boundingBox();
    expect(
      Math.abs((afterScroll?.y ?? 0) - (beforeScroll?.y ?? 0)),
    ).toBeLessThan(2);
  });

  test("reordering moves a goal up the waterfall", async ({ page }) => {
    await openDashboardWithGoals(page);
    await expect(goalName(page, "E2E Achieved Goal")).toBeVisible({
      timeout: 30_000,
    });

    // Reordering restates history itself; there is no manual action left.
    await expect(page.getByRole("button", { name: /redistribute/i })).toHaveCount(0);

    // Hold the rebuild so the in-between state can be seen: the rows must
    // move on the click, not when the server answers.
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/savings-goals/reorder", async (route) => {
      await held;
      await route.continue();
    });

    await goalRow(page, "E2E Achieved Goal")
      .getByRole("button", { name: /move up/i })
      .click();

    // The promoted goal takes position 1 and the demoted one drops to 2 —
    // while the rebuild is still out.
    await expect(
      goalRow(page, "E2E Achieved Goal").getByText("#1"),
    ).toBeVisible();
    await expect(
      goalRow(page, "E2E In Progress Goal").getByText("#2"),
    ).toBeVisible();
    const status = page.getByRole("status").filter({ hasText: /recalculating/i });
    await expect(status).toBeVisible();
    await expect(
      goalRow(page, "E2E Achieved Goal").getByTestId("goal-figures"),
    ).toHaveAttribute("aria-busy", "true");

    // The route stays: unrouting while the held handler is still in flight
    // abandons the request ("Route is already handled"), and the rebuild then
    // never lands. Once released, it passes every later reorder straight on.
    release();
    await expect(status).toHaveCount(0, { timeout: 30_000 });
    // The server's answer agrees with the order already on screen.
    await expect(
      goalRow(page, "E2E Achieved Goal").getByText("#1"),
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
    // Overview is the landing tab, and it captions one of its tiles with the
    // same "Into savings goals" string. Only the monthly ledger renders the
    // per-goal breakdown this test reads, so switch to it before asserting.
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });
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

    // The month's footer names what the goals left behind as well as what
    // they took, so a deficit month can explain itself.
    await expect(page.getByText(/^Free cash:/)).toBeVisible();
  });

  test("a goal can take over the free cash that predates it", async ({
    page,
  }) => {
    const start = monthsAgo(3);
    const goal = await createGoal({
      name: "E2E Claim Goal",
      target_amount: 5_000_000,
      monthly_cap: 1,
      start_month: start,
    });
    const claim = await (
      await ctx.get(`${API_BASE}/savings-goals/free-cash/before`, {
        params: { month: start, goal_id: goal.id },
      })
    ).json();
    expect(
      claim.free_cash,
      "demo data should leave free cash before the goal starts",
    ).toBeGreaterThan(0);

    const openingBalance = async () =>
      (await (await ctx.get(`${API_BASE}/savings-goals/`)).json()).find(
        (g: { id: number }) => g.id === goal.id,
      ).opening_balance;

    await openDashboardWithGoals(page);
    const row = goalRow(page, "E2E Claim Goal");
    await expect(row).toBeVisible({ timeout: 30_000 });
    const claimButton = row.getByRole("button", {
      name: /earmark the free cash from before/i,
    });

    // From the card: a confirm names the amount, then applies it.
    await claimButton.click();
    const confirmDialog = page.getByRole("alertdialog");
    await expect(confirmDialog.getByText(/opening balance to/i)).toBeVisible();
    await confirmDialog.getByRole("button", { name: "Earmark", exact: true }).click();
    await expect(confirmDialog).toHaveCount(0);
    await expect.poll(openingBalance).toBeCloseTo(claim.free_cash, 2);

    // Asking again straight away changes nothing and says so — even before
    // the post-write refetch has repainted the row.
    await claimButton.click();
    await expect(page.getByText(/already holds all the free cash/i)).toBeVisible();

    // From the editor: the same amount, one click away from a cleared field.
    await row.getByRole("button", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Already saved").fill("0");
    // Moving the opening balance restates history, and the editor says so.
    await expect(dialog.getByText(/recalculates goal allocations/i)).toBeVisible();
    await dialog.getByTestId("goal-opening-use-free-cash").click();
    await expect(dialog.getByLabel("Already saved")).toHaveValue(
      String(claim.free_cash),
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(await openingBalance()).toBeCloseTo(claim.free_cash, 2);
  });

  test("an investment goal is filled by transfers, not by the waterfall", async ({
    page,
  }) => {
    // A cash goal's editor offers the cash-only settings; choosing "Invest"
    // takes them away and asks for the transfers instead.
    await openDashboardWithGoals(page);
    await page.getByRole("button", { name: /add goal/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Monthly cap")).toBeVisible();
    await dialog.getByRole("radio", { name: /invest/i }).click();
    await expect(dialog.getByLabel("Monthly cap")).toHaveCount(0);
    await expect(dialog.getByLabel("Already saved")).toHaveCount(0);
    await expect(dialog.getByTestId("goal-invest-rule")).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();

    const goal = await createGoal({
      name: "E2E Invest Goal",
      target_amount: 100000,
      kind: "investment",
      contribution_category: "Investments",
      start_month: monthsAgo(12),
    });
    expect(goal.kind).toBe("investment");
    expect(goal.allocated).toBe(0);

    await page.reload();
    const row = goalRow(page, "E2E Invest Goal");
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row.getByLabel("Invest")).toBeVisible();
    // No free-cash claim on an investment goal.
    await expect(row.getByRole("button", { name: /free cash/i })).toHaveCount(0);
  });
});
