import { test, expect, type Page } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Toggle Demo Mode through the frontend dev-server proxy rather than the
 * shared ``enableDemoMode``/``disableDemoMode`` helpers, which post to a
 * hardcoded ``http://localhost:8000``. Driving it through ``page.request``
 * (relative ``/api``) makes the toggle follow Playwright's ``baseURL`` and
 * the Vite proxy to whichever backend is actually serving this run — which
 * keeps the spec correct under worktree port isolation, where the backend
 * may not be on the canonical 8000. Mirrors ``yearly-budget.spec.ts``.
 */
async function setDemoMode(page: Page, enabled: boolean) {
  const res = await page.request.post("/api/testing/toggle_demo_mode", {
    data: { enabled },
  });
  expect(res.ok()).toBeTruthy();
}

/**
 * Escape a string for safe use inside a RegExp constructor.
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface BudgetRuleRecord {
  id: number;
  name: string;
  category: string;
  tags: string[];
  year: number | null;
  month: number | null;
  period_type: string | null;
}

test.describe("Project-category exclusion", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, true);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, false);
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();
    await page.waitForLoadState("networkidle");
  });

  test("hides the conflict banner in clean demo data and excludes monthly-rule categories from the new-project picker", async ({
    page,
  }) => {
    // ---- Clean demo data has no project / monthly-yearly overlaps, so the
    // conflict banner must stay hidden. ----
    const conflictsRes = await page.request.get("/api/budget/category-conflicts");
    expect(conflictsRes.ok()).toBeTruthy();
    const conflictsBody = await conflictsRes.json();
    expect(conflictsBody.conflicts).toEqual([]);
    await expect(page.getByText(/resolve to avoid double-tracking/i)).toHaveCount(0);

    // ---- Discover a category the demo dataset seeds a monthly rule for, so
    // the scenario adapts to whatever the demo generator currently ships. ----
    const rulesRes = await page.request.get("/api/budget/rules");
    expect(rulesRes.ok()).toBeTruthy();
    const allRules: BudgetRuleRecord[] = await rulesRes.json();
    const monthlyRuleCategory = allRules.find(
      (r) => r.period_type === "monthly" && r.category !== "Total Budget",
    )?.category;
    expect(
      monthlyRuleCategory,
      "expected the demo dataset to seed at least one monthly rule",
    ).toBeTruthy();

    // ---- Open the new-project modal and assert its category picker does
    // NOT offer the category already claimed by a monthly rule. ----
    await page.getByRole("button", { name: /^New Project$/i }).click();
    const modal = page.getByRole("dialog", { name: /new project/i });
    await expect(modal).toBeVisible();

    // The category SelectDropdown trigger is the first button inside the
    // form (the header's Close button lives outside <form>).
    await modal.locator("form").getByRole("button").first().click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    await expect(
      listbox.getByRole("option", {
        name: new RegExp(`^${escapeRegExp(monthlyRuleCategory!)}$`, "i"),
      }),
    ).toHaveCount(0);

    // Close the dropdown (Escape is handled by the dropdown itself) then the
    // modal, without creating a project.
    await page.keyboard.press("Escape");
    await modal.getByRole("button", { name: /^cancel$/i }).click();
    await expect(modal).toBeHidden();
  });
});
