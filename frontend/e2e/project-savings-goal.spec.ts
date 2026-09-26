import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * `page.request` does not run the app's axios interceptor, so direct backend
 * reads must declare Demo Mode themselves to see the database the UI shows.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

interface Goal {
  id: number;
  name: string;
  funding_project: string | null;
  utilized: number;
  start_month: string | null;
  is_closed: boolean | number;
}

test.describe("Funding a project budget from a savings goal", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("links a whole project to a goal in one click and detaches it", async ({
    page,
  }) => {
    const readGoals = async (): Promise<Goal[]> =>
      (
        await page.request.get(`${API_BASE}/savings-goals/`, {
          headers: DEMO_HEADERS,
        })
      ).json();

    // Every project purchase counts from the goal's start month on, so move
    // the goal's start far enough back to cover the seeded project history.
    const goal = (await readGoals()).find((g) => !g.is_closed)!;
    expect(goal).toBeTruthy();
    const moved = await page.request.put(`${API_BASE}/savings-goals/${goal.id}`, {
      headers: DEMO_HEADERS,
      data: { start_month: "2000-01" },
    });
    expect(moved.ok()).toBeTruthy();
    const utilizedBefore = (await readGoals()).find((g) => g.id === goal.id)!
      .utilized;

    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();

    const action = page.getByTestId("project-goal-link");
    await expect(action).toHaveText(/savings goal/i, { timeout: 15_000 });
    // The view auto-selects the first open project; read which one it is off
    // the picker so the backend check below names the same project.
    const project = (
      await page.getByTestId("project-picker").getByRole("button").innerText()
    ).trim();

    await action.click();
    const modal = page.getByTestId("project-goal-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: goal.name }).click();

    // One click: the button now names the goal, and the goal pays for every
    // purchase in the project.
    await expect(modal).toBeHidden();
    await expect(action).toHaveText(goal.name, { timeout: 10_000 });
    const linked = (await readGoals()).find((g) => g.id === goal.id)!;
    expect(linked.funding_project).toBe(project);
    expect(linked.utilized).toBeGreaterThan(utilizedBefore);

    // Detaching restores it.
    await action.click();
    await modal.getByRole("button", { name: /^Remove link$/i }).click();
    await expect(action).toHaveText(/savings goal/i, { timeout: 10_000 });
    const detached = (await readGoals()).find((g) => g.id === goal.id)!;
    expect(detached.funding_project).toBeNull();
    expect(detached.utilized).toBe(utilizedBefore);
  });
});
