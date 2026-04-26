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

  test("loads the dashboard with KPI cards", async ({ page }) => {
    await page.goto("/");
    await expectPageTitle(page, /Dashboard/);

    // KPI cards should be visible
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible();
    await expect(page.getByText(/Bank Balance/i).first()).toBeVisible();
  });

  test("displays charts and visualizations", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Check for chart containers (Plotly renders into div.js-plotly-plot)
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("shows recent transactions feed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i)).toBeVisible();
  });

  test("shows budget progress section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Budget Progress/i)).toBeVisible();
  });

  test("inline tag editor stages edits and commits on Done", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/Recent Transactions/i)).toBeVisible({ timeout: 15_000 });

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
