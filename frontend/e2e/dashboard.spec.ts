import { test, expect } from "@playwright/test";
import { enableDemoMode, expectPageTitle, resetDemoData } from "./helpers";

test.describe("Dashboard", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  // The cold dashboard boot is the expensive step (~30 s of queued React
  // Query requests), so the page smoke and the inline tag-editor flow share
  // one navigation instead of paying it twice.
  test("KPIs, charts, budget section render; inline tag editor stages edits and commits on Done", async ({
    page,
  }) => {
    await page.goto("/");
    await expectPageTitle(page, /Dashboard/);

    // KPI cards should be visible
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible();
    await expect(page.getByText(/Bank Balance/i).first()).toBeVisible();

    // Chart containers render (Recharts renders into div.recharts-wrapper)
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 10_000,
    });

    // Recent transactions feed. Cold-cache navigation queues ~30 React Query
    // requests behind the browser's HTTP/1.1 connection limit; the slowest
    // queries can take ~30 s to resolve. 45 s keeps the assertion robust.
    await expect(page.getByText(/Recent Transactions/i)).toBeVisible({
      timeout: 45_000,
    });

    // --- Budget card: three tabs, each rendering its own period view ---
    // The section's "Budget" header is too generic to locate uniquely (the
    // sidebar nav link has the same text), so anchor on the tab labels, which
    // live only in BudgetSection.
    const budgetCard = page.locator('[data-card-id="budget"]');
    await budgetCard.scrollIntoViewIfNeeded();
    const monthlyTab = budgetCard.getByRole("button", { name: /Monthly Budget/i });
    const yearlyTab = budgetCard.getByRole("button", { name: /^Yearly$/i });
    const projectsTab = budgetCard.getByRole("button", { name: /Project Budgets/i });
    await expect(monthlyTab).toBeVisible();
    await expect(yearlyTab).toBeVisible();
    await expect(projectsTab).toBeVisible();

    // Monthly is the default and shows the compact total bar, not a gauge.
    await expect(monthlyTab).toHaveAttribute("aria-pressed", "true");
    await expect(budgetCard.getByTestId("budget-total-bar")).toBeVisible({
      timeout: 20_000,
    });

    // The demo DB ships no yearly rules, so this tab renders its empty state:
    // assert on the year nav, which is present either way, rather than on the
    // rule grid, which only exists once rules do.
    await yearlyTab.click();
    await expect(yearlyTab).toHaveAttribute("aria-pressed", "true");
    await expect(
      budgetCard.getByText(String(new Date().getFullYear()), { exact: true }),
    ).toBeVisible({ timeout: 20_000 });

    await projectsTab.click();
    await expect(projectsTab).toHaveAttribute("aria-pressed", "true");

    // Back to monthly so the rest of the journey sees the default view.
    await monthlyTab.click();
    await expect(budgetCard.getByTestId("budget-total-bar")).toBeVisible();

    // --- Refunds card: KPIs + open requests render from demo data ---
    const refundsCard = page.locator('[data-card-id="refunds"]');
    await refundsCard.scrollIntoViewIfNeeded();
    await expect(refundsCard.getByText("Owed back")).toBeVisible({
      timeout: 20_000,
    });
    await expect(refundsCard.getByText(/recovered/)).toBeVisible();
    // Demo data ships open (pending/partial) refunds, so the list renders,
    // with each remaining amount shown out of its expected total.
    await expect(refundsCard.getByText(/open requests/)).toBeVisible();
    await expect(
      refundsCard.getByTestId("card-refund-remaining").first(),
    ).toContainText("/");

    // --- Inline tag editor: stages edits, commits on Done ---
    const editButtons = page.getByRole("button", {
      name: /Edit category \/ tag/i,
    });
    await editButtons.first().waitFor();
    const targetRow = editButtons
      .first()
      .locator("xpath=ancestor::*[contains(@class,'cursor-pointer')][1]");
    const rowTextBefore = (await targetRow.textContent())?.trim() ?? "";
    await editButtons.first().click();

    const panel = page.locator("text=CATEGORY").locator("..").locator("..");
    await expect(panel).toBeVisible();

    const categorySelect = panel.getByRole("button").nth(0);
    const tagSelect = panel.getByRole("button").nth(1);
    const doneBtn = panel.getByRole("button", { name: /done/i });
    const initialCategory = (await categorySelect.textContent())?.trim() ?? "";

    // Pick a different category — staged, NOT committed yet.
    await categorySelect.click();
    const newCategory = page
      .getByRole("option")
      .filter({ hasNotText: new RegExp(`^${initialCategory}$`) })
      .first();
    const newCategoryName = (await newCategory.textContent())?.trim() ?? "";
    await newCategory.click();

    // Editor reflects the staged value, but the row underneath has not changed.
    await expect(panel).toBeVisible();
    await expect(categorySelect).toHaveText(new RegExp(newCategoryName));
    expect((await targetRow.textContent())?.trim()).toBe(rowTextBefore);

    // Pick a tag (also staged).
    await tagSelect.click();
    const tagOption = page.getByRole("option").first();
    const tagName = (await tagOption.textContent())?.trim() ?? "";
    if (tagName) await tagOption.click();

    // Done commits and closes the editor; row label now reflects the new
    // category/tag and the panel is gone.
    await doneBtn.click();
    await expect(panel).toBeHidden();
    if (tagName) {
      await expect(targetRow).toContainText(
        new RegExp(`${newCategoryName} / ${tagName}`),
      );
    }
  });
});
