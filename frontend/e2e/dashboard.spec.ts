import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, expectPageTitle } from "./helpers";

test.describe("Dashboard", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
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
    await expect(page.getByText(/Recent Transactions/i)).toBeVisible({ timeout: 45_000 });

    // Budget progress section. The section's "Budget" header is too generic
    // to locate uniquely (the sidebar nav link has the same text). Assert on
    // the segmented control inside the section instead — those labels live
    // only in BudgetSection.
    await expect(page.getByText(/Monthly Budget/i).first()).toBeVisible();

    // --- Refunds card: KPIs + open requests render from demo data ---
    const refundsCard = page.locator('[data-card-id="refunds"]');
    await refundsCard.scrollIntoViewIfNeeded();
    await expect(refundsCard.getByText("Owed back")).toBeVisible({ timeout: 20_000 });
    await expect(refundsCard.getByText(/recovered/)).toBeVisible();
    // Demo data ships open (pending/partial) refunds, so the list renders,
    // with each remaining amount shown out of its expected total.
    await expect(refundsCard.getByText(/open requests/)).toBeVisible();
    await expect(
      refundsCard.getByTestId("card-refund-remaining").first(),
    ).toContainText("/");

    // --- Inline tag editor: stages edits, commits on Done ---
    const editButtons = page.getByRole("button", { name: /Edit category \/ tag/i });
    await editButtons.first().waitFor();
    const targetRow = editButtons.first().locator("xpath=ancestor::*[contains(@class,'cursor-pointer')][1]");
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
      await expect(targetRow).toContainText(new RegExp(`${newCategoryName} / ${tagName}`));
    }
  });
});
