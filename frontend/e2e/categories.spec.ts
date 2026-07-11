import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";
test.describe("Categories", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("loads the categories page with category list", async ({ page }) => {
    await navigateTo(page, "/categories");
    await expectPageTitle(page, /Categories/);

    // Should display some categories
    await expect(page.getByText("Food").first()).toBeVisible({ timeout: 10_000 });
  });

  test("categories have tags nested inside", async ({ page }) => {
    await navigateTo(page, "/categories");

    // Food category should have tags visible
    const foodSection = page.getByText("Food").first();
    await expect(foodSection).toBeVisible();
  });

  test("protected categories are displayed", async ({ page }) => {
    await navigateTo(page, "/categories");

    // Protected categories should be visible
    await expect(page.getByText("Salary").first()).toBeVisible();
    await expect(page.getByText("Investments").first()).toBeVisible();
  });

  test("auto-tagging rules sit above the search row, with add-category beside the search box", async ({
    page,
  }) => {
    await navigateTo(page, "/categories");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState("networkidle");

    const rulesCard = page.getByRole("button", { name: /Auto-Tagging Rules/i });
    const searchBox = page.getByPlaceholder(/Search categories and tags/i);
    const addButton = page.getByRole("button", { name: /New Category/i });

    await expect(rulesCard).toBeVisible({ timeout: 10_000 });
    await expect(searchBox).toBeVisible();
    await expect(addButton).toBeVisible();

    const rulesBox = await rulesCard.boundingBox();
    const searchBoxBox = await searchBox.boundingBox();
    const addBox = await addButton.boundingBox();
    expect(rulesBox && searchBoxBox && addBox).toBeTruthy();

    // The auto-tagging rules card is at the top — above the search row.
    expect(rulesBox!.y + rulesBox!.height).toBeLessThanOrEqual(searchBoxBox!.y + 1);

    // The search box and the add-category button share the same row (vertically aligned).
    const searchCenter = searchBoxBox!.y + searchBoxBox!.height / 2;
    const addCenter = addBox!.y + addBox!.height / 2;
    expect(Math.abs(searchCenter - addCenter)).toBeLessThan(searchBoxBox!.height);
  });

  test("delete button is visible inside the category detail panel", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState("networkidle");

    // Click the Food card (non-protected) to open the detail panel.
    const foodCard = page.locator('[data-testid="category-card-Food"]');
    await expect(foodCard).toBeVisible({ timeout: 10_000 });
    await foodCard.click();

    const panel = page.locator('[data-testid="category-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // The delete button lives in the panel's danger zone, always visible (no hover needed).
    // Label comes from en.json: deleteCategory="Delete Category"
    const deleteBtn = panel.getByRole("button", { name: /delete category/i });
    await expect(deleteBtn).toBeVisible({ timeout: 5_000 });

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

    // Close the panel.
    await panel.getByRole("button", { name: /^close$/i }).click();
    await expect(panel).toBeHidden({ timeout: 3_000 });
  });

  test("protected category shows a disabled delete button with a reason on hover", async ({
    page,
  }) => {
    await navigateTo(page, "/categories");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState("networkidle");

    // Investments is a protected category — it cannot be deleted.
    const protectedCard = page.locator('[data-testid="category-card-Investments"]');
    await expect(protectedCard).toBeVisible({ timeout: 10_000 });
    await protectedCard.click();

    const panel = page.locator('[data-testid="category-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // The delete button is rendered but disabled (not hidden).
    const deleteBtn = panel.getByRole("button", { name: /delete category/i });
    await expect(deleteBtn).toBeVisible({ timeout: 5_000 });
    await expect(deleteBtn).toBeDisabled();

    // Hovering reveals the reason tooltip.
    const reason = panel.getByText(/cannot be deleted/i);
    const hiddenOpacity = await reason.evaluate((el) => getComputedStyle(el.parentElement!).opacity);
    expect(Number(hiddenOpacity)).toBe(0);

    await deleteBtn.hover();
    await expect
      .poll(async () => reason.evaluate((el) => getComputedStyle(el.parentElement!).opacity))
      .toBe("1");

    await panel.getByRole("button", { name: /^close$/i }).click();
    await expect(panel).toBeHidden({ timeout: 3_000 });
  });
});
