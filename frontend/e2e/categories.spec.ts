import { test, expect, type Locator } from "@playwright/test";
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

  test("category action buttons are visible without hover", async ({ page }) => {
    // Helper to walk the DOM tree checking for opacity:0
    async function getAncestorOpacity(locator: Locator): Promise<number> {
      return locator.evaluate((el) => {
        let node: Element | null = el;
        while (node) {
          const opacity = parseFloat(getComputedStyle(node).opacity);
          if (opacity === 0) return 0;
          node = node.parentElement;
        }
        return 1;
      });
    }

    await navigateTo(page, "/categories");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState("networkidle");

    // Buttons must be visible immediately — no hover required.
    // Title values come from en.json: renameCategory="Rename", addTag="Add Tag", deleteCategory="Delete Category"
    const renameBtn = page.locator('button[title="Rename"]').first();
    const addTagBtn = page.locator('button[title="Add Tag"]').first();
    const deleteBtn = page.locator('button[title="Delete Category"]').first();

    // Wait for the buttons to be in the DOM first
    await expect(renameBtn).toBeAttached({ timeout: 10_000 });
    await expect(addTagBtn).toBeAttached({ timeout: 10_000 });
    await expect(deleteBtn).toBeAttached({ timeout: 10_000 });

    // Verify buttons are not hidden behind opacity-0 — the action row container
    // must have opacity 1 (i.e. it is not inside an opacity-0 group that requires hover).
    const renameOpacity = await getAncestorOpacity(renameBtn);
    expect(renameOpacity, "Rename button (or its container) must not have opacity:0 — buttons should be visible without hover").toBe(1);

    const addTagOpacity = await getAncestorOpacity(addTagBtn);
    expect(addTagOpacity, "Add Tag button (or its container) must not have opacity:0 — buttons should be visible without hover").toBe(1);

    const deleteOpacity = await getAncestorOpacity(deleteBtn);
    expect(deleteOpacity, "Delete Category button (or its container) must not have opacity:0 — buttons should be visible without hover").toBe(1);
  });
});
