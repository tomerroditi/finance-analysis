import {
  test,
  expect,
  request,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { enableDemoMode, API_BASE, resetDemoData } from "./helpers";

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
 * Scoped to the goal list: the card's history chart legends the same names,
 * so an unscoped text lookup matches twice.
 */
function goalRow(page: Page, name: string) {
  return goalName(page, name).locator(
    "xpath=ancestor::div[contains(@class,'group')][1]",
  );
}

/** The goal's name as the goal list renders it (never the chart legend). */
function goalName(page: Page, name: string) {
  return page.getByTestId("goals-list").getByText(name, { exact: true });
}

interface ApiGoal {
  id: number;
  name: string;
  available: number;
  added_this_month: number;
  suggested_this_month: number;
}

/**
 * End-to-end coverage for manual savings goals.
 *
 * Goals are seeded through the API (Demo Mode writes to the isolated demo DB)
 * with explicit order, then the dashboard card is driven the way a user
 * would: money added and taken out as undoable entries, this month's
 * suggestion funded, and a free-cash shortfall covered from the goals.
 */
test.describe("Savings goals", () => {
  let ctx: APIRequestContext;
  const created: number[] = [];

  /** Create a goal and remember its id for cleanup. */
  async function createGoal(body: Record<string, unknown>): Promise<ApiGoal> {
    const res = await ctx.post(`${API_BASE}/savings-goals/`, { data: body });
    expect(res.ok()).toBeTruthy();
    const goals: ApiGoal[] = await res.json();
    const goal = goals.find((g) => g.name === body.name)!;
    created.push(goal.id);
    return goal;
  }

  /** The goal as the backend has it now. */
  async function readGoal(name: string): Promise<ApiGoal | undefined> {
    const goals: ApiGoal[] = await (await ctx.get(`${API_BASE}/savings-goals/`)).json();
    return goals.find((g) => g.name === name);
  }

  test.beforeAll(async () => {
    await resetDemoData();
    // This bypasses the browser (Node-side `request` fixture), so it must
    // declare the demo header itself — Demo Mode is per-client, and a
    // header-less request would write to the real database instead.
    ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });

    // Demo data ships the Cohens' own goals. This spec asserts absolute
    // positions, so clear them first — otherwise the goals created below
    // land after them. The teardown restores the snapshot.
    const seeded = await (await ctx.get(`${API_BASE}/savings-goals/`)).json();
    for (const goal of seeded as { id: number }[]) {
      await ctx.delete(`${API_BASE}/savings-goals/${goal.id}`);
    }

    await createGoal({
      name: "E2E In Progress Goal",
      target_amount: 10000,
      initial_amount: 2500,
      start_month: monthsAgo(10),
    });
    await createGoal({
      name: "E2E Achieved Goal",
      target_amount: 5000,
      initial_amount: 5000,
      start_month: monthsAgo(10),
    });
    // Nothing in it yet, so its whole monthly amount is this month's
    // suggestion — what the "Fund" chip and "Fund all" act on.
    await createGoal({
      name: "E2E Monthly Goal",
      target_amount: 3000,
      monthly_amount: 300,
    });

    // Enough goals to take the list past its height cap, which is what the
    // journey test's scroll-region check needs to see. They sort below the
    // goals above, leaving the absolute positions asserted there intact.
    for (let i = 0; i < 4; i++) {
      await createGoal({
        name: `E2E Filler ${i}`,
        target_amount: 1000,
        initial_amount: 1000,
      });
    }
  });

  test.afterAll(async () => {
    for (const id of created) {
      await ctx.delete(`${API_BASE}/savings-goals/${id}`).catch(() => {});
    }
    await ctx.dispose();
  });

  // Demo Mode itself is per-page (localStorage), so it's seeded per-test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("renders goals, free cash and their history on one dashboard load", async ({
    page,
  }) => {
    await openDashboardWithGoals(page);

    const inProgressName = goalName(page, "E2E In Progress Goal");
    const achievedName = goalName(page, "E2E Achieved Goal");
    await expect(inProgressName).toBeVisible({ timeout: 30_000 });
    await expect(achievedName).toBeVisible();

    // --- priority order ------------------------------------------------
    const inProgressRow = goalRow(page, "E2E In Progress Goal");
    const achievedRow = goalRow(page, "E2E Achieved Goal");
    await expect(inProgressRow.getByText("#1")).toBeVisible();
    await expect(achievedRow.getByText("#2")).toBeVisible();
    await expect(inProgressRow.getByRole("button", { name: /move up/i })).toBeDisabled();
    await expect(achievedRow.getByRole("button", { name: /move down/i })).toBeEnabled();
    await expect(
      goalRow(page, "E2E Filler 3").getByRole("button", { name: /move down/i }),
    ).toBeDisabled();

    // --- what a goal holds ---------------------------------------------
    // The starting amount is the goal's first entry: it holds it now.
    await expect(inProgressRow.getByTestId("goal-balance")).toContainText("2,500");
    await expect(inProgressRow.getByTestId("goal-balance")).toContainText("10,000");
    await expect(
      inProgressRow.getByRole("button", { name: /^1 entry$/ }),
    ).toBeVisible();
    // Nothing reads "recalculating" any more: nothing is ever restated.
    await expect(page.getByText(/recalculating/i)).toHaveCount(0);

    // --- achieved state ------------------------------------------------
    await expect(achievedRow.locator("svg.lucide-check")).toHaveCount(1);
    await expect(inProgressRow.locator("svg.lucide-check")).toHaveCount(0);
    await expect(achievedRow.locator("span.text-emerald-400")).toBeVisible();

    // --- SQLite boolean guard ------------------------------------------
    // `is_achieved` comes back as a 0/1 integer. A bare `{0 && <Check/>}`
    // renders the literal string "0" before the goal name.
    const header = inProgressRow.locator("xpath=.//p[1]/..");
    await expect(header).toHaveText("#1E2E In Progress Goal");

    // --- this month's suggestion ---------------------------------------
    // Only the goal with a monthly amount and nothing in it offers funding,
    // and the header offers to fund every suggestion at once.
    const monthlyRow = goalRow(page, "E2E Monthly Goal");
    await expect(monthlyRow.getByRole("button", { name: /^Fund /i })).toContainText("300");
    await expect(inProgressRow.getByRole("button", { name: /^Fund /i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Fund all$/i })).toBeVisible();

    // --- free cash -----------------------------------------------------
    // Bank and cash less what the goals hold, outside any goal row. With
    // money to spare it is not red and offers nothing to cover.
    const pool = page.getByTestId("goals-free-cash");
    await expect(pool).toBeVisible();
    await expect(pool.locator("xpath=ancestor::div[contains(@class,'group')]")).toHaveCount(0);
    await expect(pool.getByTestId("goals-free-cash-amount")).not.toHaveClass(/text-red-400/);
    await expect(pool.getByRole("button", { name: /cover it/i })).toHaveCount(0);
    const reported = await (await ctx.get(`${API_BASE}/savings-goals/free-cash`)).json();
    expect(reported.has_goals).toBe(true);
    expect(reported.free_cash + reported.earmarked).toBeCloseTo(reported.liquid, 2);
    expect(reported.cover_plan).toEqual([]);

    // --- month-by-month history ----------------------------------------
    // It opens collapsed, so the standings stay the card's first screen.
    const history = page.getByTestId("goals-history-chart");
    await expect(history).toBeHidden();
    const historyToggle = page
      .getByTestId("goals-history")
      .getByRole("button", { name: /month by month/i });
    await expect(historyToggle).toHaveAttribute("aria-expanded", "false");
    await historyToggle.click();
    await expect(history).toBeVisible({ timeout: 30_000 });
    // Free cash stacks on the same bars as the goals.
    const poolSeries = history.getByRole("button", { name: "Free cash" });
    await expect(poolSeries).toBeVisible();
    await expect(poolSeries).toHaveAttribute("aria-pressed", "true");

    // --- focusing the chart from its legend -----------------------------
    // Free cash towers over the goals; hiding it refits the axis. Read off
    // the tick labels, since Recharts renders them outside the axis group.
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

    // A double-click narrows to one goal; the rest dim rather than vanish.
    const goalSeries = history.getByRole("button", { name: "E2E In Progress Goal" });
    await goalSeries.dblclick();
    await expect(goalSeries).toHaveAttribute("aria-pressed", "true");
    await expect(poolSeries).toHaveAttribute("aria-pressed", "false");
    // Double-clicking the series it narrowed to brings the rest back.
    await goalSeries.dblclick();
    await expect(poolSeries).toHaveAttribute("aria-pressed", "true");
    // Every goal that moved this month has a series — the achieved one too,
    // since its starting amount went in this month.
    await expect(history.getByRole("button", { name: "E2E Achieved Goal" })).toBeVisible();
    // A goal that never held anything earns no series.
    await expect(history.getByRole("button", { name: "E2E Monthly Goal" })).toHaveCount(0);

    // Narrowing the window re-renders the chart rather than emptying it.
    await page.getByTestId("goals-history").getByRole("button", { name: "6M" }).click();
    await expect(history).toBeVisible();

    // --- cumulative view ------------------------------------------------
    // Month-end balances, so a goal's last bar matches its card — read off
    // the same window, no whole-history fetch.
    const panel = page.getByTestId("goals-history");
    const monthly = panel.getByRole("button", { name: "Monthly" });
    const cumulative = panel.getByRole("button", { name: "Cumulative" });
    await expect(monthly).toHaveAttribute("aria-pressed", "true");
    await cumulative.click();
    await expect(cumulative).toHaveAttribute("aria-pressed", "true");
    await expect(history.getByRole("button", { name: "E2E Achieved Goal" })).toBeVisible();
    await expect(panel.getByText(/held at the end of each month/i)).toBeVisible();

    // --- on a phone ------------------------------------------------------
    // The view and window controls share one row, and a month's tooltip
    // stays inside the plot instead of over the legend.
    const desktop = page.viewportSize();
    await page.setViewportSize({ width: 390, height: 900 });
    const groupTops = await panel
      .getByTestId("goals-history-controls")
      .locator(":scope > div")
      .evaluateAll((groups) => groups.map((g) => g.getBoundingClientRect().top));
    expect(groupTops).toHaveLength(2);
    expect(Math.abs(groupTops[0] - groupTops[1])).toBeLessThan(2);
    await history.scrollIntoViewIfNeeded();
    const lastBar = await history.locator(".recharts-bar-rectangle").last().boundingBox();
    await page.mouse.move(lastBar!.x + lastBar!.width / 2, lastBar!.y + 2);
    const tooltipBox = history.locator(".recharts-tooltip-wrapper");
    await expect(tooltipBox.getByText(/:/).first()).toBeVisible();
    const tip = await tooltipBox.boundingBox();
    const legend = await history.locator(".recharts-legend-wrapper").boundingBox();
    expect(tip!.y + tip!.height).toBeLessThanOrEqual(legend!.y + 1);
    if (desktop) await page.setViewportSize(desktop);

    await monthly.click();
    await expect(monthly).toHaveAttribute("aria-pressed", "true");

    // The toggle closes what it opened, range chips and all.
    await historyToggle.click();
    await expect(history).toBeHidden();
    await expect(panel.getByRole("button", { name: "6M" })).toBeHidden();

    // --- the goal list is a capped scroll region -------------------------
    // Many goals must not push free cash and the history panel down the
    // page; the list scrolls inside the card instead.
    const list = page.getByTestId("goals-list");
    const geometry = await list.evaluate((el) => ({
      client: el.clientHeight,
      scroll: el.scrollHeight,
      overflowY: getComputedStyle(el).overflowY,
    }));
    expect(geometry.overflowY).toBe("auto");
    expect(geometry.scroll).toBeGreaterThan(geometry.client);
    expect(geometry.client).toBeLessThanOrEqual(26 * 16 + 2);

    // Scrolling the list moves the rows, not the card's chrome.
    const beforeScroll = await page.getByTestId("goals-history").boundingBox();
    await list.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    const afterScroll = await page.getByTestId("goals-history").boundingBox();
    expect(Math.abs((afterScroll?.y ?? 0) - (beforeScroll?.y ?? 0))).toBeLessThan(2);
  });

  test("money goes in and out as entries that can be undone", async ({ page }) => {
    await openDashboardWithGoals(page);
    const row = goalRow(page, "E2E In Progress Goal");
    await expect(row).toBeVisible({ timeout: 30_000 });
    const balance = row.getByTestId("goal-balance");
    await expect(balance).toContainText("2,500");

    // --- add money -------------------------------------------------------
    await row.getByRole("button", { name: /^Add money$/ }).click();
    await row.getByLabel("Amount to add to E2E In Progress Goal").fill("1000");
    await row.getByLabel("Note").fill("E2E bonus");
    await row.getByRole("button", { name: "Save", exact: true }).click();
    await expect(balance).toContainText("3,500", { timeout: 15_000 });
    await expect(row.getByTestId("goal-entry-form")).toHaveCount(0);
    await expect(row).toContainText(/added this month/);

    // --- the entry is listed, and undoing it takes the money back out ---
    await row.getByRole("button", { name: /^2 entries$/ }).click();
    const bonus = row.getByTestId("goal-entry").filter({ hasText: "E2E bonus" });
    await expect(bonus).toBeVisible();
    await bonus.getByRole("button", { name: /undo/i }).click();
    await expect(balance).toContainText("2,500", { timeout: 15_000 });
    await expect(bonus).toHaveCount(0);

    // --- take money out ---------------------------------------------------
    // More than the goal holds can't be taken out.
    await row.getByRole("button", { name: /^Take out$/ }).click();
    const takeAmount = row.getByLabel("Amount to take out of E2E In Progress Goal");
    await takeAmount.fill("9999");
    await expect(row.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
    await takeAmount.fill("500");
    await row.getByLabel("Note").fill("E2E withdrawal");
    await row.getByRole("button", { name: "Save", exact: true }).click();
    await expect(balance).toContainText("2,000", { timeout: 15_000 });
    const withdrawal = row.getByTestId("goal-entry").filter({ hasText: "E2E withdrawal" });
    await expect(withdrawal).toBeVisible();
    await withdrawal.getByRole("button", { name: /undo/i }).click();
    await expect(balance).toContainText("2,500", { timeout: 15_000 });

    // --- fund this month's suggestion -----------------------------------
    const monthlyRow = goalRow(page, "E2E Monthly Goal");
    await monthlyRow.getByRole("button", { name: /^Fund /i }).click();
    await expect(monthlyRow.getByTestId("goal-balance")).toContainText("300", {
      timeout: 15_000,
    });
    // Funded, so there is nothing left to suggest this month.
    await expect(monthlyRow.getByRole("button", { name: /^Fund /i })).toHaveCount(0);
    await expect.poll(async () => (await readGoal("E2E Monthly Goal"))?.added_this_month).toBe(300);

    // Undo it, and "Fund all" does the same from the header.
    await monthlyRow.getByRole("button", { name: /^1 entry$/ }).click();
    await monthlyRow.getByTestId("goal-entry").first().getByRole("button", { name: /undo/i }).click();
    await expect(monthlyRow.getByRole("button", { name: /^Fund /i })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: /^Fund all$/i }).click();
    await expect.poll(async () => (await readGoal("E2E Monthly Goal"))?.available).toBe(300);
    await expect(page.getByRole("button", { name: /^Fund all$/i })).toHaveCount(0);
  });

  test("reordering moves a goal up at once", async ({ page }) => {
    await openDashboardWithGoals(page);
    await expect(goalName(page, "E2E Achieved Goal")).toBeVisible({ timeout: 30_000 });

    // Hold the server so the in-between state can be seen: the rows move on
    // the click, not when the server answers.
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/savings-goals/reorder", async (route) => {
      await held;
      await route.continue();
    });

    await goalRow(page, "E2E Achieved Goal").getByRole("button", { name: /move up/i }).click();
    await expect(goalRow(page, "E2E Achieved Goal").getByText("#1")).toBeVisible();
    await expect(goalRow(page, "E2E In Progress Goal").getByText("#2")).toBeVisible();
    // A reorder restates nothing, so nothing waits on it.
    await expect(page.getByText(/recalculating/i)).toHaveCount(0);

    // The route stays: unrouting while the held handler is in flight
    // abandons the request. Once released, it passes later reorders on.
    release();
    await expect
      .poll(async () => {
        const goals: { name: string }[] = await (
          await ctx.get(`${API_BASE}/savings-goals/`)
        ).json();
        return goals[0]?.name;
      })
      .toBe("E2E Achieved Goal");

    // Restore the original order so the suite is order-independent.
    await goalRow(page, "E2E In Progress Goal").getByRole("button", { name: /move up/i }).click();
    await expect(goalRow(page, "E2E In Progress Goal").getByText("#1")).toBeVisible();
    await expect
      .poll(async () => {
        const goals: { name: string }[] = await (
          await ctx.get(`${API_BASE}/savings-goals/`)
        ).json();
        return goals[0]?.name;
      })
      .toBe("E2E In Progress Goal");
  });

  test("a shortfall in free cash is covered from the goals once confirmed", async ({
    page,
  }) => {
    // Set aside more than there is: a goal holding free cash and 5,000 more.
    const before = await (await ctx.get(`${API_BASE}/savings-goals/free-cash`)).json();
    const overdrawn = await createGoal({
      name: "E2E Overdrawn",
      target_amount: Math.ceil(Math.max(0, before.free_cash)) + 20000,
      initial_amount: Math.ceil(Math.max(0, before.free_cash)) + 5000,
    });
    try {
      await openDashboardWithGoals(page);
      const pool = page.getByTestId("goals-free-cash");
      await expect(pool).toBeVisible({ timeout: 30_000 });
      await expect(pool.getByTestId("goals-free-cash-amount")).toHaveClass(/text-red-400/);
      await expect(pool).toContainText(/more than you have/);

      // Nothing moves until the plan is confirmed.
      await pool.getByRole("button", { name: /cover it/i }).click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog).toContainText("E2E Overdrawn");
      await dialog.getByRole("button", { name: /cancel/i }).click();
      await expect(dialog).toHaveCount(0);
      expect((await readGoal("E2E Overdrawn"))?.available).toBeGreaterThan(5000);

      await pool.getByRole("button", { name: /cover it/i }).click();
      await page.getByRole("alertdialog").getByRole("button", { name: /^Cover it$/ }).click();
      await expect(pool.getByTestId("goals-free-cash-amount")).not.toHaveClass(/text-red-400/, {
        timeout: 15_000,
      });
      await expect(pool.getByRole("button", { name: /cover it/i })).toHaveCount(0);
      const after = await (await ctx.get(`${API_BASE}/savings-goals/free-cash`)).json();
      expect(after.free_cash).toBeGreaterThanOrEqual(-0.5);

      // The lowest-priority goal gave it back, as an entry it can see.
      const row = goalRow(page, "E2E Overdrawn");
      await row.getByRole("button", { name: /entries$/ }).click();
      await expect(
        row.getByTestId("goal-entry").filter({ hasText: /cover free cash/i }),
      ).toBeVisible();
    } finally {
      await ctx.delete(`${API_BASE}/savings-goals/${overdrawn.id}`);
    }
  });

  test("a goal added under an open history still stacks under free cash", async ({
    page,
  }) => {
    // Recharts 3 stacks bars in the order they first mounted, not the order
    // they render in. A series that appeared while the chart was open — a new
    // goal — mounted after free cash and was drawn on top of it.
    let addedId: number | undefined;
    try {
      await openDashboardWithGoals(page);
      await expect(goalName(page, "E2E In Progress Goal")).toBeVisible({ timeout: 30_000 });
      const history = page.getByTestId("goals-history");
      await history.getByRole("button", { name: /month by month/i }).click();
      const chart = page.getByTestId("goals-history-chart");
      await expect(chart.locator(".recharts-bar-rectangle").first()).toBeAttached({
        timeout: 30_000,
      });

      await page.getByRole("button", { name: /add goal/i }).click();
      const dialog = page.getByRole("dialog");
      await dialog.locator("#goal-name").fill("E2E Stack B");
      await dialog.locator("#goal-target").fill("50000");
      await dialog.locator("#goal-monthly").fill("1000");
      await dialog.locator("#goal-initial").fill("1500");
      await dialog.getByRole("button", { name: /^save$/i }).click();
      await expect(dialog).toHaveCount(0);
      await expect(goalName(page, "E2E Stack B")).toBeVisible({ timeout: 30_000 });
      await expect(goalRow(page, "E2E Stack B").getByTestId("goal-balance")).toContainText(
        "1,500",
      );

      addedId = (await readGoal("E2E Stack B"))?.id;
      const added = `url(#goal-fill-${addedId})`;
      await expect(chart.locator(`[fill="${added}"]`).first()).toBeAttached({
        timeout: 30_000,
      });

      // In every column holding both, free cash caps the new goal's segment.
      const misplaced = await chart.evaluate((root, fill) => {
        const columns = new Map<number, { goal?: number; free?: number }>();
        for (const rect of root.querySelectorAll(".recharts-bar-rectangle")) {
          const shape = rect.querySelector("path, rect") as SVGGraphicsElement | null;
          if (!shape) continue;
          const box = shape.getBBox();
          if (box.height <= 0) continue;
          const column = columns.get(Math.round(box.x)) ?? {};
          if (shape.getAttribute("fill") === fill) column.goal = box.y;
          if (shape.getAttribute("fill") === "url(#goal-fill-free)") column.free = box.y;
          columns.set(Math.round(box.x), column);
        }
        const shared = [...columns.values()].filter(
          (c) => c.goal !== undefined && c.free !== undefined,
        );
        return {
          shared: shared.length,
          bad: shared.filter((c) => (c.goal as number) < (c.free as number)).length,
        };
      }, added);
      expect(misplaced.shared).toBeGreaterThan(0);
      expect(misplaced.bad).toBe(0);
    } finally {
      if (addedId !== undefined) await ctx.delete(`${API_BASE}/savings-goals/${addedId}`);
    }
  });

  test("this year's savings can be given a target from the card", async ({
    page,
  }) => {
    // The card opens with what this year saved; setting a target turns it
    // into progress, a pace and what is still needed per month.
    const year = new Date().getFullYear();
    await ctx.put(`${API_BASE}/savings-goals/yearly/${year}/target`, {
      data: { target_amount: null },
    });
    try {
      await openDashboardWithGoals(page);
      const section = page.getByTestId("yearly-savings");
      await expect(section).toBeVisible({ timeout: 30_000 });
      await expect(section.getByText(`${year} savings`)).toBeVisible();
      await expect(section.getByText(/Expected by today/)).toHaveCount(0);

      await section.getByRole("button", { name: /set target/i }).click();
      await section.getByLabel(`Savings target for ${year}`).fill("50000");
      await section.getByRole("button", { name: /save/i }).click();

      await expect(section.getByTestId("yearly-saved")).toContainText("50,000");
      await expect(section.getByText(/Expected by today/)).toBeVisible();
      await expect(section.getByRole("button", { name: /edit target/i })).toBeVisible();
    } finally {
      await ctx.put(`${API_BASE}/savings-goals/yearly/${year}/target`, {
        data: { target_amount: null },
      });
    }
  });

  test("the budget month shows how each goal moved", async ({ page }) => {
    // The goals created above put their starting amounts in this month, but
    // ask the backend which recent month has movement rather than assume.
    let monthsBack = -1;
    let expected: { goals: { name: string }[] } | null = null;
    const now = new Date();
    for (let back = 0; back < 12; back += 1) {
      const d = new Date(now.getFullYear(), now.getMonth() - back, 1);
      const res = await ctx.get(
        `${API_BASE}/savings-goals/month/${d.getFullYear()}/${d.getMonth() + 1}`,
      );
      expect(res.ok()).toBeTruthy();
      const body = await res.json();
      if (body.goals.length > 0) {
        monthsBack = back;
        expected = body;
        break;
      }
    }
    expect(monthsBack, "a goal should have moved in one of the last 12 months").toBeGreaterThanOrEqual(0);

    await page.goto("/budget");
    await page.waitForLoadState("domcontentloaded");
    // Overview is the landing tab; only the monthly ledger renders the
    // per-goal breakdown this test reads.
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({ timeout: 30_000 });
    for (let i = 0; i < monthsBack; i += 1) {
      await page.getByRole("button", { name: /previous/i }).first().click();
    }

    const section = page.getByTestId("budget-goals-month");
    await expect(section).toBeVisible({ timeout: 30_000 });
    await expect(section.getByText("Savings goals this month", { exact: true })).toBeVisible();
    for (const goal of expected!.goals) {
      await expect(section.getByText(goal.name, { exact: true })).toBeVisible();
    }
    // The footer says what was put in by hand; the waterfall's surplus and
    // clawback lines are gone.
    await expect(section.getByText(/^Added by hand:/)).toBeVisible();
    await expect(page.getByText(/came back out of the goals/)).toHaveCount(0);
  });
});
