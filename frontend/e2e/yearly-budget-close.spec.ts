import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/** Escape a string for safe use inside a RegExp constructor. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * `page.request` is Playwright's own HTTP client — it does not run the app's
 * JS, so the axios interceptor that attaches `X-FAD-Demo` from localStorage
 * never runs for it. Direct backend reads must declare the header themselves
 * to see the same database the UI (seeded via `enableDemoMode`) is showing.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

interface BudgetRuleRecord {
  name: string;
  category: string;
}

/** The month the Overview opens on, which is the one it reports rules for. */
function currentMonthPath(): string {
  const now = new Date();
  return `${now.getFullYear()}/${now.getMonth() + 1}`;
}

test.describe("Closing a yearly budget rule", () => {
  // Restore pristine demo data before this file runs. The `mutating` project
  // is serial and each file owns its DB state; the demo database is
  // process-global, so without this a predecessor's writes leak in.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("closes a yearly rule, drops it from the overview, and reopens it", async ({
    page,
  }) => {
    const year = new Date().getFullYear();
    const ruleName = `E2E Close ${Date.now()}`;

    // A category claimed by no rule at all is guaranteed not to collide with
    // the demo data's monthly/yearly/project budgets.
    const [rulesRes, categoriesRes] = await Promise.all([
      page.request.get(`${API_BASE}/budget/rules`, { headers: DEMO_HEADERS }),
      page.request.get(`${API_BASE}/tagging/categories`, {
        headers: DEMO_HEADERS,
      }),
    ]);
    expect(rulesRes.ok()).toBeTruthy();
    expect(categoriesRes.ok()).toBeTruthy();
    const allRules: BudgetRuleRecord[] = await rulesRes.json();
    const categoriesMap: Record<string, string[]> = await categoriesRes.json();
    const claimed = new Set(allRules.map((r) => r.category));
    const freeCategory = Object.entries(categoriesMap).find(
      ([name, tags]) => !claimed.has(name) && tags.length > 0,
    );
    expect(
      freeCategory,
      "expected at least one category with no budget rule of any kind",
    ).toBeTruthy();

    const created = await page.request.post(`${API_BASE}/budget/yearly/rules`, {
      headers: DEMO_HEADERS,
      data: {
        name: ruleName,
        amount: 15000,
        category: freeCategory![0],
        tags: freeCategory![1],
        year,
      },
    });
    expect(created.ok()).toBeTruthy();

    const analysisUrl = `${API_BASE}/budget/yearly/${year}/analysis`;
    const analysis: {
      rules: { rule: { id: number; name: string }; closed: boolean }[];
    } = await (
      await page.request.get(analysisUrl, { headers: DEMO_HEADERS })
    ).json();
    const entry = analysis.rules.find((r) => r.rule.name === ruleName);
    expect(entry, "the created rule is missing from the analysis").toBeTruthy();
    expect(entry!.closed).toBe(false);
    const ruleId = entry!.rule.id;
    const namePattern = new RegExp(escapeRegExp(ruleName), "i");

    // The Overview lists the fresh rule to begin with.
    await navigateTo(page, "/budget");
    const overviewRules = page.getByTestId("budget-long-rules");
    await expect(overviewRules).toBeVisible({ timeout: 30_000 });
    await expect(overviewRules).toContainText(namePattern);

    // Close it from the Yearly tab.
    await page.getByRole("button", { name: /^Yearly$/i }).click();
    const toggle = page.getByTestId(`yearly-close-toggle-${ruleId}`).first();
    await expect(toggle).toHaveAttribute("aria-label", /close rule/i, {
      timeout: 15_000,
    });
    await toggle.click();

    const confirmDialog = page.getByRole("alertdialog");
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog).toContainText(ruleName);
    await confirmDialog
      .getByRole("button", { name: /^Close rule$/i })
      .click();

    // The year's own tab keeps the rule, now marked, and the action
    // turns into a reopen.
    await expect(page.getByTestId("yearly-closed-badge").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(toggle).toHaveAttribute("aria-label", /reopen rule/i);
    // Its figures survive — closing is not a delete or a zeroing.
    const row = page
      .locator("div.w-full.rounded-xl")
      .filter({ hasText: namePattern })
      .first();
    await expect(row.getByTestId("ledger-figures").first()).toContainText(
      "15,000",
    );

    // Backend: the rule is still there, and still owns its allocation.
    const afterClose: {
      rules: { rule: { id: number; amount: number }; closed: boolean }[];
    } = await (
      await page.request.get(analysisUrl, { headers: DEMO_HEADERS })
    ).json();
    const closedEntry = afterClose.rules.find((r) => r.rule.id === ruleId);
    expect(closedEntry).toBeTruthy();
    expect(closedEntry!.closed).toBe(true);
    expect(closedEntry!.rule.amount).toBe(15000);

    const overview = await (
      await page.request.get(
        `${API_BASE}/budget/overview/${currentMonthPath()}`,
        { headers: DEMO_HEADERS },
      )
    ).json();
    expect(
      overview.long_envelopes.map((e: { name: string }) => e.name),
    ).not.toContain(ruleName);

    // Overview: the rule is gone from the list the month is measured
    // against.
    await page.getByRole("button", { name: /^Overview$/i }).click();
    await expect(overviewRules).toBeVisible({ timeout: 15_000 });
    await expect(overviewRules).not.toContainText(namePattern);

    // Reopening puts it back, with no confirmation step.
    await page.getByRole("button", { name: /^Yearly$/i }).click();
    await expect(toggle).toHaveAttribute("aria-label", /reopen rule/i, {
      timeout: 15_000,
    });
    await toggle.click();
    await expect(page.getByTestId("yearly-closed-badge")).toHaveCount(0, {
      timeout: 10_000,
    });

    await page.getByRole("button", { name: /^Overview$/i }).click();
    await expect(overviewRules).toContainText(namePattern, {
      timeout: 15_000,
    });
  });
});
