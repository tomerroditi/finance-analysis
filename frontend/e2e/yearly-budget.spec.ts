import { test, expect, type Page } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Toggle Demo Mode through the frontend dev-server proxy rather than the
 * shared ``enableDemoMode``/``disableDemoMode`` helpers, which post to a
 * hardcoded ``http://localhost:8000``. Driving it through ``page.request``
 * (relative ``/api``) makes the toggle follow Playwright's ``baseURL`` and
 * the Vite proxy to whichever backend is actually serving this run — which
 * keeps the spec correct under worktree port isolation, where the backend
 * may not be on the canonical 8000.
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

/**
 * Locate a yearly-rule row card by its (unique, generated) name. The row is
 * the ``rounded-xl`` card rendered by ``BudgetProgressBar`` for each rule.
 */
function ruleRow(page: Page, name: string) {
  return page.locator("div.rounded-xl", { hasText: name }).first();
}

test.describe("Yearly budget", () => {
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
    await page.getByRole("button", { name: /^Yearly$/i }).click();
  });

  test("navigates years; creates a yearly rule, blocks a conflicting tag inline, and deletes the rule", async ({
    page,
  }) => {
    const currentYear = new Date().getFullYear();

    // ---- 0. Year navigation changes the displayed year (and returns). ----
    const yearHeading = page.locator("h2").filter({ hasText: /^\d{4}$/ });
    await expect(yearHeading).toHaveText(String(currentYear));

    await page.getByRole("button", { name: /^Previous$/i }).click();
    await expect(yearHeading).toHaveText(String(currentYear - 1));

    await page.getByRole("button", { name: /^Next$/i }).click();
    await expect(yearHeading).toHaveText(String(currentYear));

    // ---- Discover live demo data so the scenario adapts to whatever the
    // seeded dataset actually contains, instead of hardcoding category/tag
    // names that could drift out of sync with the demo generator. ----
    const [rulesRes, categoriesRes] = await Promise.all([
      page.request.get("/api/budget/rules"),
      page.request.get("/api/tagging/categories"),
    ]);
    expect(rulesRes.ok()).toBeTruthy();
    expect(categoriesRes.ok()).toBeTruthy();
    const allRules: BudgetRuleRecord[] = await rulesRes.json();
    const categoriesMap: Record<string, string[]> = await categoriesRes.json();

    const monthlyRulesThisYear = allRules.filter(
      (r) => r.period_type === "monthly" && Number(r.year) === currentYear,
    );

    // A monthly rule with a real (non "all_tags") tag we can collide with.
    const conflictCandidate = monthlyRulesThisYear.find(
      (r) =>
        r.category !== "Total Budget" &&
        Array.isArray(r.tags) &&
        r.tags.length > 0 &&
        !r.tags.includes("all_tags"),
    );
    expect(
      conflictCandidate,
      "expected the demo dataset to seed at least one monthly rule with a real tag for the current year",
    ).toBeTruthy();
    const conflictCategory = conflictCandidate!.category;
    const conflictTag = conflictCandidate!.tags[0];

    // A category with zero monthly rules (of any kind, including
    // category-wide "all_tags" ones) for the current year — guaranteed not
    // to collide, used for the happy-path creation below.
    const monthlyUsedCategories = new Set(monthlyRulesThisYear.map((r) => r.category));
    const freeCategoryEntry = Object.entries(categoriesMap).find(
      ([name, tags]) => !monthlyUsedCategories.has(name) && tags.length > 0,
    );
    expect(
      freeCategoryEntry,
      "expected at least one category with no monthly rule for the current year",
    ).toBeTruthy();
    const [freeCategory, freeCategoryTags] = freeCategoryEntry!;
    const freeTag = freeCategoryTags[0];

    // ---- 1. Create a yearly rule and confirm it renders with a progress bar. ----
    const ruleName = `E2E Yearly ${Date.now()}`;

    await page.getByRole("button", { name: /add yearly rule/i }).click();
    const addDialog = page.getByRole("dialog", { name: /add yearly rule/i });
    await expect(addDialog).toBeVisible();

    await addDialog.getByPlaceholder(/vacations/i).fill(ruleName);

    await addDialog.getByRole("button", { name: /select a category/i }).click();
    await page
      .getByRole("option", { name: new RegExp(`^${escapeRegExp(freeCategory)}$`, "i") })
      .click();

    await addDialog.getByRole("button", { name: /select tags/i }).click();
    await page
      .getByRole("option", { name: new RegExp(`^${escapeRegExp(freeTag)}$`, "i") })
      .click();
    // Close the tags popover (it stays open to allow multiple picks).
    await addDialog.getByPlaceholder(/vacations/i).click();

    await addDialog.getByPlaceholder(/20,?000/i).fill("15000");
    await addDialog.getByRole("button", { name: /^save$/i }).click();
    await expect(addDialog).toBeHidden({ timeout: 10_000 });

    const createdRow = ruleRow(page, ruleName);
    await expect(createdRow).toBeVisible({ timeout: 10_000 });
    await expect(createdRow).toContainText(freeCategory);
    // The progress fill is an inline-styled div driven by percent spent.
    await expect(createdRow.locator("div[style*='width']").first()).toBeVisible();

    // ---- 2. Attempt a colliding yearly rule and assert the inline error. ----
    await page.getByRole("button", { name: /add yearly rule/i }).click();
    const conflictDialog = page.getByRole("dialog", { name: /add yearly rule/i });
    await expect(conflictDialog).toBeVisible();

    await conflictDialog.getByPlaceholder(/vacations/i).fill(`E2E Conflict ${Date.now()}`);

    await conflictDialog.getByRole("button", { name: /select a category/i }).click();
    await page
      .getByRole("option", { name: new RegExp(`^${escapeRegExp(conflictCategory)}$`, "i") })
      .click();

    await conflictDialog.getByRole("button", { name: /select tags/i }).click();
    await page
      .getByRole("option", { name: new RegExp(`^${escapeRegExp(conflictTag)}$`, "i") })
      .click();
    await conflictDialog.getByPlaceholder(/vacations/i).click();

    await conflictDialog.getByPlaceholder(/20,?000/i).fill("5000");
    await conflictDialog.getByRole("button", { name: /^save$/i }).click();

    // The 400 detail surfaces inline, directly under the Tags field, and
    // the modal stays open (no navigation/close on error).
    const inlineError = conflictDialog.getByText(/monthly budget/i);
    await expect(inlineError).toBeVisible({ timeout: 10_000 });
    await expect(inlineError).toContainText(conflictTag);
    await expect(conflictDialog).toBeVisible();

    await conflictDialog.getByRole("button", { name: /^cancel$/i }).click();
    await expect(conflictDialog).toBeHidden();

    // ---- 3. Delete the rule created in step 1 via the themed confirm dialog. ----
    const deleteButton = createdRow.getByRole("button", { name: /delete rule/i });
    await deleteButton.click();

    const confirmDialog = page.getByRole("alertdialog");
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog).toContainText(ruleName);
    await confirmDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(ruleRow(page, ruleName)).toHaveCount(0, { timeout: 10_000 });
  });
});
