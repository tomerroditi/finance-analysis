import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * A liability (like an investment) is identified by the (category, tag) its
 * payments carry, so tag operations on the Categories page must keep it
 * linked: deleting its tag is refused with a toast, renaming it carries the
 * liability along.
 *
 * `page.request` does not run the app's axios interceptor, so the direct
 * backend read declares the demo header itself.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

test.describe("Tags that track a holding", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("deleting a liability's tag is refused; renaming it moves the liability", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await navigateTo(page, "/categories");

    await page.locator('[data-testid="category-card-Liabilities"]').click();
    const panel = page.locator('[data-testid="category-panel"]');
    await expect(panel).toBeVisible();

    const tagRow = panel.locator("div.group\\/tag", { hasText: /^Car Loan$/ });
    await expect(tagRow).toBeVisible();

    // --- Delete is refused: toast, and the tag stays ---
    await tagRow.hover();
    await tagRow.getByTitle("Delete Tag").click();
    await page.getByRole("button", { name: /^Delete$/ }).last().click();
    await expect(
      page.getByText(/Couldn't change this tag/i).first(),
    ).toBeVisible();
    await expect(tagRow).toBeVisible();

    // --- Rename carries the liability to the new tag ---
    await tagRow.getByText("Car Loan", { exact: true }).click();
    // The row's text becomes an input, so tagRow no longer matches it.
    const input = panel.locator('input[type="text"]');
    await input.fill("Car Finance");
    await input.press("Enter");
    await expect(
      panel.getByText("Car Finance", { exact: true }),
    ).toBeVisible();

    const res = await page.request.get(`${API_BASE}/liabilities/`, {
      headers: DEMO_HEADERS,
    });
    expect(res.ok()).toBeTruthy();
    const tags = ((await res.json()) as { tag: string }[]).map((l) => l.tag);
    expect(tags).toContain("Car Finance");
    expect(tags).not.toContain("Car Loan");
  });
});
