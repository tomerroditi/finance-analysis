import { test, expect, type Page } from "@playwright/test";

/**
 * Empty-database smoke test.
 *
 * Verifies that every Layout-mounted route renders without throwing when
 * the backend is booted against a fresh, empty SQLite database — the
 * exact state every user sees on first install. This is the regression
 * test for the class of bug fixed by `guard analytics and budget
 * services against empty database`, where pages assumed seed data.
 *
 * The spec is **opt-in** — set `E2E_EMPTY_DB=1` to run it. Otherwise
 * the regular `npx playwright test` run skips it, because the rest of
 * the e2e suite relies on Demo Mode and shared state.
 *
 * To run it:
 *
 *   FAD_USER_DIR=$(mktemp -d) python .claude/scripts/with_server.py -- \
 *     bash -c "cd frontend && E2E_EMPTY_DB=1 npx playwright test e2e/empty-state.spec.ts"
 *
 * The first thing the spec does is hit /api/onboarding/status; if the
 * backend reports any seeded data (i.e. you forgot to set
 * `FAD_USER_DIR`), it skips with a clear message rather than failing
 * destructively against your real database.
 */

const SHOULD_RUN = process.env.E2E_EMPTY_DB === "1";

test.describe("Empty database smoke", () => {
  test.skip(
    !SHOULD_RUN,
    "Set E2E_EMPTY_DB=1 (and point the backend at an empty FAD_USER_DIR) to run.",
  );

  test.beforeAll(async ({ request }) => {
    const res = await request.get("http://localhost:8000/api/onboarding/status");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    if (!body.is_first_run) {
      test.skip(
        true,
        "Backend reports existing data — refusing to run empty-DB smoke against a populated DB. Re-run with FAD_USER_DIR pointed at an empty dir.",
      );
    }
  });

  test("onboarding wizard renders for fresh users", async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto("/onboarding");
    await page.waitForLoadState("networkidle");

    await expect(
      page.getByRole("heading", { level: 1 }).first(),
    ).toBeVisible();
    // English language button is always present, regardless of the user's
    // browser default — this is the canonical first step.
    await expect(
      page.getByRole("button", { name: /English/ }),
    ).toBeVisible();

    expect(errors, errors.join("\n")).toHaveLength(0);
  });

  test("dashboard auto-redirects fresh users to /onboarding", async ({
    page,
  }) => {
    const errors = collectPageErrors(page);
    await page.goto("/");
    await page.waitForURL(/\/onboarding/, { timeout: 5_000 });
    expect(page.url()).toContain("/onboarding");
    expect(errors, errors.join("\n")).toHaveLength(0);
  });

  // Visiting each Layout-mounted route directly bypasses the
  // OnboardingGate (it only redirects from "/"). This confirms every
  // page handles the "no data" case without throwing.
  for (const route of [
    "/transactions",
    "/budget",
    "/categories",
    "/investments",
    "/liabilities",
    "/insurances",
    "/early-retirement",
    "/data-sources",
    "/data-flow",
  ]) {
    test(`${route} renders against an empty database without errors`, async ({
      page,
    }) => {
      const errors = collectPageErrors(page);
      await page.goto(route);
      await page.waitForLoadState("networkidle");

      // The h1 heading should mount — proves React got past the
      // top-level page component without throwing.
      await expect(
        page.getByRole("heading", { level: 1 }).first(),
      ).toBeVisible({ timeout: 10_000 });

      expect(errors, errors.join("\n")).toHaveLength(0);
    });
  }
});

/** Capture every uncaught browser-side error for the duration of a test. */
function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore the noisy axios interceptor log — those are expected
      // when the user hits a route that lazy-fetches an empty
      // collection. We only care about uncaught/runtime errors.
      if (text.startsWith("API Error:")) return;
      errors.push(`console.error: ${text}`);
    }
  });
  return errors;
}
