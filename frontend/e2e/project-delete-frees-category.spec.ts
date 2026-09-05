import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/** Escape a string for safe use inside a RegExp constructor. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * `page.request` is Playwright's own HTTP client for the page's context —
 * it does not run the app's JS, so the axios interceptor that attaches
 * `X-FAD-Demo` from localStorage never runs for it. Every direct backend
 * check below must therefore declare the header itself to read/write the
 * same database the UI (seeded via `enableDemoMode(page)`) is showing.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

test.describe("Project deletion frees its category", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("renders a project's envelopes, then deletes it, frees its category and renders the project recreated from it", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();

    // Discover the seeded project. Its category must start out claimed (absent
    // from the available-categories picker).
    const projectsRes = await page.request.get("/api/budget/projects", {
      headers: DEMO_HEADERS,
    });
    expect(projectsRes.ok()).toBeTruthy();
    const projects: string[] = await projectsRes.json();
    expect(projects.length).toBeGreaterThan(0);
    const target = projects[0];

    const availBefore = await (
      await page.request.get("/api/budget/projects/available", {
        headers: DEMO_HEADERS,
      })
    ).json();
    expect(availBefore).not.toContain(target);

    // The view auto-selects the first project, so its Delete button is present.
    await expect(
      page.getByText(new RegExp(escapeRegExp(target), "i")).first(),
    ).toBeVisible({ timeout: 10_000 });

    // The selected project's envelopes must actually render. The seeded demo
    // projects carry no `all_tags` anchor rule, and the view used to gate its
    // entire body — band, ledger and rail — on finding one, so picking such a
    // project showed the command bar over an empty page with no explanation.
    // The project name in the picker is not evidence the body rendered.
    await expect(page.getByTestId("ledger-figures").first()).toBeVisible({
      timeout: 10_000,
    });

    await page
      .getByRole("button", { name: /^Delete$/i })
      .first()
      .click();

    // Confirm in the destructive dialog.
    const dialog = page.locator("div.modal-overlay", {
      hasText: /delete this project/i,
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Delete$/i }).click();

    // Backend: the project is gone from the list...
    await expect(async () => {
      const listRes = await page.request.get("/api/budget/projects", {
        headers: DEMO_HEADERS,
      });
      expect(await listRes.json()).not.toContain(target);
    }).toPass({ timeout: 10_000 });

    // ...and its detail view now 404s instead of resurrecting its rules from
    // the transactions still categorized under it (the original bug).
    const detailRes = await page.request.get(
      `/api/budget/projects/${encodeURIComponent(target)}`,
      { headers: DEMO_HEADERS },
    );
    expect(detailRes.status()).toBe(404);

    // The category is available for a new project again.
    const availAfter = await (
      await page.request.get("/api/budget/projects/available", {
        headers: DEMO_HEADERS,
      })
    ).json();
    expect(availAfter).toContain(target);

    // UI: the new-project picker now offers the freed category.
    await page.getByRole("button", { name: /^New Project$/i }).click();
    const modal = page.getByRole("dialog", { name: /new project/i });
    await expect(modal).toBeVisible();
    await modal.locator("form").getByRole("button").first().click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    const freedOption = listbox.getByRole("option", {
      name: new RegExp(`^${escapeRegExp(target)}$`, "i"),
    });
    await expect(freedOption).toBeVisible();

    // Recreate it. `create_project` writes the category-wide anchor rule
    // tagged with the backend's lowercase `all_tags` constant; the view finds
    // that rule to render its status band. Matching it against the uppercase
    // literal instead made the match fail for every project and blanked the
    // whole tab, so assert the band — not just the row — comes back.
    await freedOption.click();
    await modal.getByRole("spinbutton").fill("5000");
    await modal.getByRole("button", { name: /^create$/i }).click();
    await expect(modal).toBeHidden({ timeout: 10_000 });

    const statusBand = page.getByTestId("budget-status-band");
    await expect(statusBand).toBeVisible({ timeout: 10_000 });
    await expect(statusBand).toContainText(
      new RegExp(escapeRegExp(target), "i"),
    );
    await expect(statusBand).toContainText("5,000");
  });
});
