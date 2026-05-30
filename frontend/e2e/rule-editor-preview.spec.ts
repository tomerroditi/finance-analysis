import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

test.describe("Rule editor matching transactions preview", () => {
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

  test("matching transactions table is not capped at 50", async ({ page }) => {
    // Auto-tagging rules now live in a full-screen manager opened from the
    // Auto-Tagging Rules launcher on the Categories page.
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // Open the rules manager, then click "New Rule".
    await page.getByRole("button", { name: /Auto-Tagging Rules/i }).click();
    await page.getByRole("button", { name: /^New Rule$/ }).click();

    // Wait for the editor modal to render and pick the visible Value input
    // inside it (there can be a duplicate hidden one for the mobile layout).
    const modal = page.locator(".modal-overlay").last();
    await expect(modal).toBeVisible();
    const valueInput = modal.locator('input[placeholder="Value"]:visible').first();
    await expect(valueInput).toBeVisible();
    await valueInput.fill("WOLT");

    // Debounce in the modal is 300ms; wait for the preview query.
    await page.waitForResponse(
      (res) =>
        res.url().includes("/api/tagging-rules/rules/preview") &&
        res.request().method() === "POST",
    );

    // The matches count and the rendered row count should both exceed 50,
    // proving the previous 50-row cap is gone.
    const matchesLabel = modal.getByText(/\d+\s*matches/).first();
    await expect(matchesLabel).toBeVisible();
    const labelText = await matchesLabel.textContent();
    const matchCount = parseInt(labelText?.match(/(\d+)/)?.[1] ?? "0", 10);
    expect(matchCount).toBeGreaterThan(50);

    // The modal's preview table should render every match.
    const previewRows = modal.locator("table tbody tr");
    await expect(previewRows).toHaveCount(matchCount);
  });
});
