import { test, expect, type Page } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Toggle Demo Mode through the frontend dev-server proxy (relative ``/api``)
 * so the toggle follows Playwright's ``baseURL`` and the Vite proxy to
 * whichever backend serves this run. Mirrors ``project-category-exclusion``.
 */
async function setDemoMode(page: Page, enabled: boolean) {
  const res = await page.request.post("/api/testing/toggle_demo_mode", {
    data: { enabled },
  });
  expect(res.ok()).toBeTruthy();
}

/** Escape a string for safe use inside a RegExp constructor. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test.describe("Project deletion frees its category", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, true);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, false);
    await page.close();
  });

  test("deleting a project removes it from the list and returns its category to the new-project picker", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Project Budgets$/i }).click();

    // Discover the seeded project. Its category must start out claimed (absent
    // from the available-categories picker).
    const projectsRes = await page.request.get("/api/budget/projects");
    expect(projectsRes.ok()).toBeTruthy();
    const projects: string[] = await projectsRes.json();
    expect(projects.length).toBeGreaterThan(0);
    const target = projects[0];

    const availBefore = await (
      await page.request.get("/api/budget/projects/available")
    ).json();
    expect(availBefore).not.toContain(target);

    // The view auto-selects the first project, so its Delete button is present.
    await expect(
      page.getByText(new RegExp(escapeRegExp(target), "i")).first(),
    ).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /^Delete$/i }).first().click();

    // Confirm in the destructive dialog.
    const dialog = page.locator("div.modal-overlay", {
      hasText: /delete this project/i,
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Delete$/i }).click();

    // Backend: the project is gone from the list...
    await expect(async () => {
      const listRes = await page.request.get("/api/budget/projects");
      expect(await listRes.json()).not.toContain(target);
    }).toPass({ timeout: 10_000 });

    // ...and its detail view now 404s instead of resurrecting its rules from
    // the transactions still categorized under it (the original bug).
    const detailRes = await page.request.get(
      `/api/budget/projects/${encodeURIComponent(target)}`,
    );
    expect(detailRes.status()).toBe(404);

    // The category is available for a new project again.
    const availAfter = await (
      await page.request.get("/api/budget/projects/available")
    ).json();
    expect(availAfter).toContain(target);

    // UI: the new-project picker now offers the freed category.
    await page.getByRole("button", { name: /^New Project$/i }).click();
    const modal = page.getByRole("dialog", { name: /new project/i });
    await expect(modal).toBeVisible();
    await modal.locator("form").getByRole("button").first().click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    await expect(
      listbox.getByRole("option", {
        name: new RegExp(`^${escapeRegExp(target)}$`, "i"),
      }),
    ).toBeVisible();
  });
});
