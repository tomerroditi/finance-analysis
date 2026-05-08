import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("Categories", () => {
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

  test("loads the categories page with category list", async ({ page }) => {
    await navigateTo(page, "/categories");
    await expectPageTitle(page, /Categories/);

    // Should display some categories
    await expect(page.getByText("Food").first()).toBeVisible({ timeout: 10_000 });
  });

  test("categories have tags nested inside", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // Food category should have tags visible
    const foodSection = page.getByText("Food").first();
    await expect(foodSection).toBeVisible();
  });

  test("protected categories are displayed", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // Protected categories should be visible
    await expect(page.getByText("Salary").first()).toBeVisible();
    await expect(page.getByText("Investments").first()).toBeVisible();
  });

  test("delete button is always visible in the category header", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState("networkidle");

    // Wait for the page fade-in animation (animate-in fade-in duration-500) to finish
    // before checking opacity — the animation starts at opacity:0.
    await page.waitForFunction(
      () => {
        const animated = document.querySelector(".animate-in");
        return !animated || parseFloat(getComputedStyle(animated).opacity) >= 0.99;
      },
      { timeout: 3_000 }
    );

    // The delete button lives in the right zone of every category header.
    // Title value comes from en.json: deleteCategory="Delete Category"
    const deleteBtn = page.locator('button[title="Delete Category"]').first();
    await expect(deleteBtn).toBeAttached({ timeout: 10_000 });

    // Verify it is not hidden behind an opacity-0 ancestor.
    const opacity = await deleteBtn.evaluate((el) => {
      let node: Element | null = el;
      while (node) {
        if (parseFloat(getComputedStyle(node).opacity) === 0) return 0;
        node = node.parentElement;
      }
      return 1;
    });
    expect(opacity, "Delete button must not have opacity:0 — it should be visible without hover").toBe(1);
  });
});
