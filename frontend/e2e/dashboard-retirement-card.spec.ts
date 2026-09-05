import { test, expect } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Early Retirement dashboard card — an opt-in (hidden by default) full-width
 * card that surfaces the FIRE readiness, headline KPIs and projection charts
 * from the saved retirement plan, without exposing any plan settings.
 *
 * One dashboard load covers the default-hidden policy, the Settings opt-in
 * flow, and the rendered card content — the cold dashboard boot is the
 * expensive step. The demo DB ships with a saved retirement goal, so the card
 * renders the projections path (not the setup CTA).
 */
test.describe("Dashboard early-retirement card", () => {
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test.beforeEach(async ({ page }) => {
    // Start from a clean (default) layout.
    await page.addInitScript(() =>
      window.localStorage.removeItem("fa.dashboard.layout"),
    );
  });

  test("hidden by default, opt-in via Settings shows KPIs and projection chart", async ({
    page,
  }) => {
    await page.goto("/");

    // Not rendered on the default dashboard.
    await expect(page.locator('[data-card-id="net_worth"]')).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.locator('[data-card-id="retirement"]')).toHaveCount(0);

    await page
      .getByRole("button", { name: /^Settings$/ })
      .first()
      .click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Early Retirement sits under Hidden cards, with no Beta pill (opt-in,
    // not experimental). Scope the lookup to the Hidden-cards section — the
    // sidebar behind the popup carries the same "Early Retirement" label.
    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();
    const hiddenSection = page
      .getByText("Hidden cards", { exact: true })
      .locator("xpath=..");
    const retirementRow = hiddenSection
      .getByText("Early Retirement", { exact: true })
      .locator("xpath=..");
    await expect(retirementRow).toBeVisible();
    await expect(retirementRow.getByText(/^Beta$/i)).toHaveCount(0);

    // Opting in shows it on the dashboard.
    await retirementRow.getByRole("button", { name: /Show card/i }).click();
    await page.keyboard.press("Escape");

    const card = page.locator('[data-card-id="retirement"]');
    await expect(card).toBeVisible({ timeout: 30_000 });
    // The newly enabled card is appended below the fold, where cards defer
    // their mount until scrolled near.
    await card.scrollIntoViewIfNeeded();

    // Insight KPIs render from the demo plan (readiness + FIRE number).
    await expect(card.getByText("Readiness", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(card.getByText("FIRE Number", { exact: true })).toBeVisible();
    // The demo plan is deliberately tuned to be on track (see
    // create_retirement_goal in scripts/generate_demo_data.py) — guard it.
    await expect(card.getByText("On Track", { exact: true })).toBeVisible();

    // The net worth projection chart renders an actual Recharts SVG.
    await expect(
      card
        .locator(
          '[data-testid="retirement-projection-chart"] .recharts-wrapper svg',
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    // No plan settings are exposed on the card — the goal form (with its
    // Save/Calculate controls) lives only on the retirement page.
    await expect(
      card.getByRole("button", { name: /Save Plan|Calculate/i }),
    ).toHaveCount(0);
  });
});
