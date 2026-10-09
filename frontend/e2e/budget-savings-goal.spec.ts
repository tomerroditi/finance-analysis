import { test, expect, type Page } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * `page.request` does not run the app's axios interceptor, so direct backend
 * reads must declare Demo Mode themselves to see the database the UI shows.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

interface Goal {
  id: number;
  name: string;
  utilization_category: string | null;
  utilization_tags: string | null;
  /** Money spent out of the goal by its spending rule or links. */
  spent: number;
  is_closed: boolean | number;
}

async function readGoals(page: Page): Promise<Goal[]> {
  return (
    await page.request.get(`${API_BASE}/savings-goals/`, { headers: DEMO_HEADERS })
  ).json();
}

/**
 * The first open demo goal, started far enough back that every seeded
 * purchase falls inside it — a rule only claims spending from the goal's
 * start month on.
 */
async function openGoalCoveringHistory(page: Page): Promise<Goal> {
  const goal = (await readGoals(page)).find((g) => !g.is_closed)!;
  expect(goal).toBeTruthy();
  const moved = await page.request.put(`${API_BASE}/savings-goals/${goal.id}`, {
    headers: DEMO_HEADERS,
    data: { start_month: "2000-01" },
  });
  expect(moved.ok()).toBeTruthy();
  return (await readGoals(page)).find((g) => g.id === goal.id)!;
}

test.describe("Paying for a budget out of a savings goal", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("links a whole project to a goal in one click and detaches it", async ({
    page,
  }) => {
    const goal = await openGoalCoveringHistory(page);

    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();

    const action = page.getByTestId("budget-goal-link");
    await expect(action).toHaveText(/savings goal/i, { timeout: 15_000 });
    // The view auto-selects the first open project; read which one it is off
    // the picker so the backend check below names the same project.
    const project = (
      await page.getByTestId("project-picker").getByRole("button").innerText()
    ).trim();

    await action.click();
    const modal = page.getByTestId("budget-goal-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: goal.name }).click();

    // One click: the button now names the goal, and the goal pays for the
    // project's purchases out of what it holds.
    await expect(modal).toBeHidden();
    await expect(action).toHaveText(goal.name, { timeout: 10_000 });
    const linked = (await readGoals(page)).find((g) => g.id === goal.id)!;
    expect(linked.utilization_category).toBe(project);
    expect(linked.utilization_tags).toBeNull();
    expect(linked.spent).toBeGreaterThan(goal.spent);

    await action.click();
    await modal.getByRole("button", { name: /^Remove link$/i }).click();
    await expect(action).toHaveText(/savings goal/i, { timeout: 10_000 });
    const detached = (await readGoals(page)).find((g) => g.id === goal.id)!;
    expect(detached.utilization_category).toBeNull();
    expect(detached.spent).toBeCloseTo(goal.spent, 2);
  });

  test("links a yearly envelope with its category and tags", async ({ page }) => {
    const goal = await openGoalCoveringHistory(page);
    const year = new Date().getFullYear();
    const ruleName = `E2E Goal Envelope ${Date.now()}`;

    // An envelope over a category no rule claims, narrowed to one tag.
    const [rules, categories] = await Promise.all([
      page.request
        .get(`${API_BASE}/budget/rules`, { headers: DEMO_HEADERS })
        .then((r) => r.json() as Promise<{ category: string }[]>),
      page.request
        .get(`${API_BASE}/tagging/categories`, { headers: DEMO_HEADERS })
        .then((r) => r.json() as Promise<Record<string, string[]>>),
    ]);
    const claimed = new Set(rules.map((r) => r.category));
    const free = Object.entries(categories).find(
      ([name, tags]) => !claimed.has(name) && tags.length > 1,
    );
    expect(free, "expected a free category with at least two tags").toBeTruthy();
    const [category, tags] = free!;
    const created = await page.request.post(`${API_BASE}/budget/yearly/rules`, {
      headers: DEMO_HEADERS,
      data: { name: ruleName, amount: 5000, category, tags: [tags[0]], year },
    });
    expect(created.ok()).toBeTruthy();

    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Yearly$/i }).click();
    const row = page
      .locator("div.w-full.rounded-xl")
      .filter({ hasText: ruleName })
      .first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    // Row actions render twice (hover strip on desktop, a row on mobile);
    // hovering reveals the desktop one.
    await row.hover();
    const action = row.getByTestId("budget-goal-link").first();
    await action.click();

    const modal = page.getByTestId("budget-goal-modal");
    await expect(page.getByRole("dialog")).toContainText(ruleName);
    await modal.getByRole("button", { name: goal.name }).click();
    await expect(modal).toBeHidden();

    await expect
      .poll(async () => (await readGoals(page)).find((g) => g.id === goal.id))
      .toMatchObject({ utilization_category: category, utilization_tags: tags[0] });
    await row.hover();
    await expect(action).toHaveAttribute("aria-label", `Funded by ${goal.name}`);
  });

  test("the goal editor links a category to the goal directly", async ({ page }) => {
    const goal = (await readGoals(page)).find((g) => !g.is_closed)!;
    const categories: Record<string, string[]> = await (
      await page.request.get(`${API_BASE}/tagging/categories`, {
        headers: DEMO_HEADERS,
      })
    ).json();
    const category = Object.keys(categories).sort((a, b) => a.localeCompare(b))[0];

    await page.goto("about:blank");
    await page.goto("/");
    await page.evaluate(() => {
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
      localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({ v: 5, order: ["goals", "budget", "recent"], hidden: [] }),
      );
    });
    await page.goto("/");

    const row = page
      .getByTestId("goals-list")
      .getByText(goal.name, { exact: true })
      .locator("xpath=ancestor::div[contains(@class,'group')][1]");
    await row.getByRole("button", { name: /^Edit$/i }).click();

    // The editor is taller than a laptop screen. Scrolling over it must move
    // the form, never the dashboard behind it.
    await page.setViewportSize({ width: 1280, height: 600 });
    const dialog = page.getByRole("dialog");
    const body = dialog.locator(":scope > div").last();
    const box = (await dialog.boundingBox())!;
    const pageScroll = () =>
      page.evaluate(() => [window.scrollY, document.body.style.top].join("|"));
    const before = await pageScroll();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, 800);
    await expect.poll(() => body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    expect(await pageScroll()).toBe(before);

    const spend = page.getByTestId("goal-auto-link-spend");
    await spend.getByRole("button").first().click();
    await page.getByRole("option", { name: category, exact: true }).click();
    await page.getByRole("button", { name: /^Save$/i }).click();

    await expect
      .poll(async () => (await readGoals(page)).find((g) => g.id === goal.id))
      .toMatchObject({ utilization_category: category, utilization_tags: null });
  });

  test("a transaction is saved into a goal only when money comes in", async ({ page }) => {
    // Setting money aside is the goal's "Add money", never a link on a
    // transfer, so spending is offered "Paid from" alone; income gets both.
    await navigateTo(page, "/transactions");
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const linkButton = page.getByRole("button", { name: "Link to a savings goal" });
    const dialog = page.getByRole("dialog");

    const expense = rows.filter({ has: page.locator("td.text-red-500") }).filter({ has: linkButton }).first();
    await expense.hover();
    await expense.getByRole("button", { name: "Link to a savings goal" }).click();
    await expect(dialog.getByRole("button", { name: "Paid from" }).first()).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Saved into" })).toHaveCount(0);
    await dialog.getByRole("button", { name: /^Cancel$/ }).click();
    await expect(dialog).toHaveCount(0);

    const income = rows.filter({ has: page.locator("td.text-emerald-500") }).filter({ has: linkButton }).first();
    await income.hover();
    await income.getByRole("button", { name: "Link to a savings goal" }).click();
    await expect(dialog.getByRole("button", { name: "Saved into" }).first()).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Paid from" }).first()).toBeVisible();
  });

  test("the goal editor scrolls under a finger on a phone", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 700 },
      hasTouch: true,
      isMobile: true,
    });
    const page = await context.newPage();
    await enableDemoMode(page);
    await page.goto("/");
    await page.evaluate(() =>
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now())),
    );
    await page.goto("/");

    const edit = page
      .getByTestId("goals-list")
      .getByRole("button", { name: /^Edit$/i })
      .first();
    await edit.scrollIntoViewIfNeeded();
    await edit.click();
    const dialog = page.getByRole("dialog");
    const body = dialog.locator(":scope > div").last();
    await expect(body).toBeVisible();

    // A real touch drag: `Input.synthesizeScrollGesture` scrolls nothing in
    // headless Chromium, not even the bare page, so it would pass vacuously.
    const box = (await body.boundingBox())!;
    const x = box.x + box.width / 2;
    const y = box.y + box.height * 0.75;
    const cdp = await context.newCDPSession(page);
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x, y }],
    });
    for (let step = 1; step <= 15; step++) {
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x, y: y - step * 20 }],
      });
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });

    await expect.poll(() => body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

    // --- tag picker near the bottom of the dialog ------------------------
    // The tag panel is fixed to the viewport. Opened from the last field of a
    // scrolled dialog it used to drop straight down and run off the screen;
    // it must open toward the room it has and stay inside the viewport.
    const categories: Record<string, string[]> = await (
      await page.request.get(`${API_BASE}/tagging/categories`, {
        headers: DEMO_HEADERS,
      })
    ).json();
    const tagged = Object.entries(categories).find(([, tags]) => tags.length > 3);
    expect(tagged, "expected a category with several tags").toBeTruthy();
    const save = page.getByTestId("goal-auto-link-save");
    await body.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    await save.getByRole("button").first().click();
    await page.getByRole("option", { name: tagged![0], exact: true }).click();
    await body.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    await save.getByRole("button").nth(1).click();

    const panel = page.getByTestId("multiselect-panel");
    await expect(panel).toBeVisible();
    const panelBox = (await panel.boundingBox())!;
    expect(panelBox.y).toBeGreaterThanOrEqual(0);
    expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(700);
    await expect(panel.getByRole("option").first()).toBeInViewport();

    // --- the keyboard comes up ------------------------------------------
    // Tapping the panel's search box raises the on-screen keyboard, which
    // shrinks what is visible. Playwright cannot summon a keyboard, so the
    // viewport is shrunk the same way. The panel must stay on the side of the
    // trigger it opened on — flipping took the search box away from the
    // finger — and shrink to fit what is still visible.
    const trigger = save.getByRole("button").nth(1);
    const above = async () =>
      (await panel.boundingBox())!.y < (await trigger.boundingBox())!.y;
    const openedAbove = await above();
    await page.setViewportSize({ width: 390, height: 520 });
    await expect.poll(above).toBe(openedAbove);
    await expect
      .poll(async () => {
        const box = (await panel.boundingBox())!;
        return box.y >= 0 && box.y + box.height <= 520;
      })
      .toBe(true);
    await context.close();
  });
});
