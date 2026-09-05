import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

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

test.describe("Project-category exclusion", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();
    await page.waitForLoadState("networkidle");
  });

  test("hides the conflict banner in clean demo data and excludes monthly-rule categories from the new-project picker", async ({
    page,
  }) => {
    // ---- The demo seed ships a "Home Renovation" project — the Projects tab
    // renders it (formerly flows/project-budget-create.spec.ts). ----
    await expect(page.getByText(/home renovation/i).first()).toBeVisible({
      timeout: 10_000,
    });

    // ---- Clean demo data has no project / monthly-yearly overlaps, so the
    // conflict banner must stay hidden. ----
    const conflictsRes = await page.request.get(
      "/api/budget/category-conflicts",
      { headers: DEMO_HEADERS },
    );
    expect(conflictsRes.ok()).toBeTruthy();
    const conflictsBody = await conflictsRes.json();
    expect(conflictsBody.conflicts).toEqual([]);
    await expect(
      page.getByText(/resolve to avoid double-tracking/i),
    ).toHaveCount(0);

    // ---- Discover a category the demo dataset seeds a monthly rule for, so
    // the scenario adapts to whatever the demo generator currently ships. ----
    const rulesRes = await page.request.get("/api/budget/rules", {
      headers: DEMO_HEADERS,
    });
    expect(rulesRes.ok()).toBeTruthy();
    const allRules: BudgetRuleRecord[] = await rulesRes.json();
    const monthlyRuleCategory = allRules.find(
      (r) => r.period_type === "monthly" && r.category !== "Total Budget",
    )?.category;
    expect(
      monthlyRuleCategory,
      "expected the demo dataset to seed at least one monthly rule",
    ).toBeTruthy();

    // ---- Open the new-project modal and assert its category picker does
    // NOT offer the category already claimed by a monthly rule. ----
    await page.getByRole("button", { name: /^New Project$/i }).click();
    const modal = page.getByRole("dialog", { name: /new project/i });
    await expect(modal).toBeVisible();

    // The category SelectDropdown trigger is the first button inside the
    // form (the header's Close button lives outside <form>).
    await modal.locator("form").getByRole("button").first().click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    await expect(
      listbox.getByRole("option", {
        name: new RegExp(`^${escapeRegExp(monthlyRuleCategory!)}$`, "i"),
      }),
    ).toHaveCount(0);

    // Close the dropdown (Escape is handled by the dropdown itself) then the
    // modal, without creating a project.
    await page.keyboard.press("Escape");
    await modal.getByRole("button", { name: /^cancel$/i }).click();
    await expect(modal).toBeHidden();
  });
});
