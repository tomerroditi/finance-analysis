import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/** Escape a string for safe use inside a RegExp constructor. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * `page.request` is Playwright's own HTTP client — it does not run the app's
 * JS, so the axios interceptor that attaches `X-FAD-Demo` from localStorage
 * never runs for it. Direct backend reads must declare the header themselves
 * to see the same database the UI (seeded via `enableDemoMode`) is showing.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

/** The month the Overview opens on, which is the one it reports envelopes for. */
function currentMonthPath(): string {
  const now = new Date();
  return `${now.getFullYear()}/${now.getMonth() + 1}`;
}

test.describe("Closing a project budget", () => {
  // Restore pristine demo data before this file runs. The `mutating` project
  // is serial and each file owns its DB state; the demo database is
  // process-global, so without this a predecessor's writes leak in.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("closes a project from its tab, drops it from the overview, and reopens it", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");

    // The Overview lists the seeded project as a long envelope to begin with.
    const overviewEnvelopes = page.getByTestId("budget-long-envelopes");
    await expect(overviewEnvelopes).toBeVisible({ timeout: 15_000 });

    const projectsRes = await page.request.get("/api/budget/projects", {
      headers: DEMO_HEADERS,
    });
    expect(projectsRes.ok()).toBeTruthy();
    const projects: string[] = await projectsRes.json();
    expect(projects.length).toBeGreaterThan(0);
    const target = projects[0];
    const targetPattern = new RegExp(escapeRegExp(target), "i");
    await expect(overviewEnvelopes).toContainText(targetPattern);

    // The demo project is over its budget, so it also holds a "needs
    // attention" row — the other section a closed project has to leave.
    const targetAttentionRow = page
      .getByTestId("overview-attention-row")
      .filter({ hasText: targetPattern });
    await expect(targetAttentionRow).toHaveCount(1);

    // Close it from the Projects tab. The view auto-selects the first project,
    // which is the same one the Overview listed above.
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();
    const toggle = page.getByTestId("project-closed-toggle");
    await expect(toggle).toHaveText(/close project/i, { timeout: 15_000 });
    await toggle.click();

    const dialog = page.locator("div.modal-overlay", {
      hasText: /stops appearing in the budget overview/i,
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Close project$/i }).click();

    // The project's own tab keeps it — with its history and a notice saying
    // why it left the Overview — and the button now offers to reopen it.
    await expect(page.getByTestId("project-closed-notice")).toBeVisible({
      timeout: 10_000,
    });
    await expect(toggle).toHaveText(/reopen project/i);
    // The seeded demo projects carry no `all_tags` anchor rule, so this tab
    // renders its ledger without a status band — the envelope rows are what
    // proves the history survived the close.
    await expect(page.getByTestId("ledger-figures").first()).toBeVisible({
      timeout: 10_000,
    });

    // Backend: closing is not a delete.
    const stillListed: string[] = await (
      await page.request.get("/api/budget/projects", { headers: DEMO_HEADERS })
    ).json();
    expect(stillListed).toContain(target);
    const overview = await (
      await page.request.get(`/api/budget/overview/${currentMonthPath()}`, {
        headers: DEMO_HEADERS,
      })
    ).json();
    expect(
      overview.long_envelopes.map((e: { name: string }) => e.name),
    ).not.toContain(target);

    // Overview: the envelope is gone, and with it the "needs attention" row.
    // Counting a filtered locator rather than asserting `not.toContainText`
    // on the rows: once the last row goes, that locator matches nothing at
    // all and the negative assertion fails on "element(s) not found".
    await page.getByRole("button", { name: /^Overview$/i }).click();
    await expect(targetAttentionRow).toHaveCount(0, { timeout: 15_000 });
    await expect(overviewEnvelopes).toBeVisible({ timeout: 15_000 });
    await expect(overviewEnvelopes).not.toContainText(targetPattern);

    // Reopening puts it back, with no confirmation step.
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();
    await expect(toggle).toHaveText(/reopen project/i, { timeout: 15_000 });
    await toggle.click();
    await expect(page.getByTestId("project-closed-notice")).toBeHidden({
      timeout: 10_000,
    });

    await page.getByRole("button", { name: /^Overview$/i }).click();
    await expect(overviewEnvelopes).toContainText(targetPattern, {
      timeout: 15_000,
    });
  });
});
