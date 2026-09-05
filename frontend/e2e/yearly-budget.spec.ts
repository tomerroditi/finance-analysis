import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Escape a string for safe use inside a RegExp constructor.
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * `page.request` is Playwright's own HTTP client for the page's context —
 * it does not run the app's JS, so the axios interceptor that attaches
 * `X-FAD-Demo` from localStorage never runs for it. Every direct backend
 * check below must therefore declare the header itself to read the same
 * database the UI (seeded via `enableDemoMode(page)`) is showing.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

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
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
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
    const [rulesRes, categoriesRes, spendRes] = await Promise.all([
      page.request.get("/api/budget/rules", { headers: DEMO_HEADERS }),
      page.request.get("/api/tagging/categories", { headers: DEMO_HEADERS }),
      page.request.get("/api/analytics/expenses-by-category-over-time", {
        headers: DEMO_HEADERS,
      }),
    ]);
    expect(rulesRes.ok()).toBeTruthy();
    expect(categoriesRes.ok()).toBeTruthy();
    expect(spendRes.ok()).toBeTruthy();
    const allRules: BudgetRuleRecord[] = await rulesRes.json();
    const categoriesMap: Record<string, string[]> = await categoriesRes.json();

    // Spend-positive totals per category for the viewed year. The happy-path
    // rule below is deliberately created over a category that HAS spend: a
    // zero-spend envelope renders "0 ₪" and 0% whichever sign the view
    // applies, so it cannot catch a flipped `current_amount` (which is how a
    // double negation shipped — every yearly row read as a net refund).
    const spendByMonth: {
      month: string;
      categories: Record<string, number>;
    }[] = await spendRes.json();
    const spendThisYear = new Map<string, number>();
    for (const row of spendByMonth) {
      if (!row.month.startsWith(String(currentYear))) continue;
      for (const [category, amount] of Object.entries(row.categories)) {
        spendThisYear.set(
          category,
          (spendThisYear.get(category) ?? 0) + amount,
        );
      }
    }

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

    // A category claimed by no rule at all (monthly, yearly or project) —
    // guaranteed not to collide — and among those, the one with the most
    // spend this year, so the created envelope shows a real figure.
    const claimedCategories = new Set(allRules.map((r) => r.category));
    const freeCategoryEntry = Object.entries(categoriesMap)
      .filter(([name, tags]) => !claimedCategories.has(name) && tags.length > 0)
      .sort(
        ([a], [b]) => (spendThisYear.get(b) ?? 0) - (spendThisYear.get(a) ?? 0),
      )[0];
    expect(
      freeCategoryEntry,
      "expected at least one category with no budget rule of any kind",
    ).toBeTruthy();
    const [freeCategory, freeCategoryTags] = freeCategoryEntry!;

    // ---- 1. Create a yearly rule and confirm it renders with a progress bar. ----
    const ruleName = `E2E Yearly ${Date.now()}`;

    await page.getByRole("button", { name: /add yearly rule/i }).click();
    const addDialog = page.getByRole("dialog", { name: /add yearly rule/i });
    await expect(addDialog).toBeVisible();

    await addDialog.getByPlaceholder(/vacations/i).fill(ruleName);

    await addDialog.getByRole("button", { name: /select a category/i }).click();
    await page
      .getByRole("option", {
        name: new RegExp(`^${escapeRegExp(freeCategory)}$`, "i"),
      })
      .click();

    // Take every tag in the category so the envelope covers the whole of that
    // category's spend, which was checked to be non-zero above.
    await addDialog.getByRole("button", { name: /select tags/i }).click();
    for (const tag of freeCategoryTags) {
      await page
        .getByRole("option", {
          name: new RegExp(`^${escapeRegExp(tag)}$`, "i"),
        })
        .click();
    }
    // Close the tags popover (it stays open to allow multiple picks).
    await addDialog.getByPlaceholder(/vacations/i).click();

    await addDialog.getByPlaceholder(/20,?000/i).fill("15000");
    await addDialog.getByRole("button", { name: /^save$/i }).click();
    await expect(addDialog).toBeHidden({ timeout: 10_000 });

    const createdRow = ruleRow(page, ruleName);
    await expect(createdRow).toBeVisible({ timeout: 10_000 });
    await expect(createdRow).toContainText(freeCategory);
    // The progress fill is an inline-styled element driven by percent spent.
    // It is a <span> now: the ledger row's clickable area is a <button>, and
    // a <div> inside a button is not valid phrasing content.
    await expect(
      createdRow.locator("[style*='width']").first(),
    ).toHaveAttribute("style", /width:/);

    // ---- 1b. The row must render the API's spend with the API's sign. ----
    // `current_amount` is spend-positive (get_yearly_budget_view already
    // negates the transaction sum), and BudgetLedgerRow reads a negative
    // `current` as a net refund: it clamps the bar to 0% and paints the whole
    // envelope as remaining. Negating on the way in therefore blanked every
    // yearly row's progress while the header above it showed the real total.
    const analysisRes = await page.request.get(
      `/api/budget/yearly/${currentYear}/analysis`,
      { headers: DEMO_HEADERS },
    );
    expect(analysisRes.ok()).toBeTruthy();
    const analysis: {
      rules: { rule: { name: string }; current_amount: number }[];
    } = await analysisRes.json();
    const createdEntry = analysis.rules.find((r) => r.rule.name === ruleName);
    expect(
      createdEntry,
      "the created rule is missing from the analysis",
    ).toBeTruthy();
    expect(
      createdEntry!.current_amount,
      `expected demo spend in ${freeCategory} for ${currentYear} — without it this ` +
        "assertion cannot tell a flipped sign from a correct one",
    ).toBeGreaterThan(0);

    const figures = createdRow.getByTestId("ledger-figures").first();
    await expect(figures).not.toContainText("-");
    await expect(figures).toContainText(
      Math.round(createdEntry!.current_amount).toLocaleString("en-US"),
    );
    // A refund-shaped row reports 0%; a real one does not.
    await expect(createdRow).not.toContainText(/\bnet refund\b/i);
    await expect(
      createdRow.locator("[style*='width']").first(),
    ).not.toHaveAttribute("style", /width:\s*0%/);

    // ---- 2. Attempt a colliding yearly rule and assert the inline error. ----
    await page.getByRole("button", { name: /add yearly rule/i }).click();
    const conflictDialog = page.getByRole("dialog", {
      name: /add yearly rule/i,
    });
    await expect(conflictDialog).toBeVisible();

    await conflictDialog
      .getByPlaceholder(/vacations/i)
      .fill(`E2E Conflict ${Date.now()}`);

    await conflictDialog
      .getByRole("button", { name: /select a category/i })
      .click();
    await page
      .getByRole("option", {
        name: new RegExp(`^${escapeRegExp(conflictCategory)}$`, "i"),
      })
      .click();

    await conflictDialog.getByRole("button", { name: /select tags/i }).click();
    await page
      .getByRole("option", {
        name: new RegExp(`^${escapeRegExp(conflictTag)}$`, "i"),
      })
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
    const deleteButton = createdRow.getByRole("button", {
      name: /delete rule/i,
    });
    await deleteButton.click();

    const confirmDialog = page.getByRole("alertdialog");
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog).toContainText(ruleName);
    await confirmDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(ruleRow(page, ruleName)).toHaveCount(0, { timeout: 10_000 });
  });
});
