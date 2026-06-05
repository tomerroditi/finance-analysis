import { test, expect, type Page } from "@playwright/test";
import { disableDemoMode, navigateTo } from "./helpers";

/**
 * The budget data-freshness UX: a "last synced" badge, a stale-KPI
 * treatment, and a very-stale sync banner, all driven by the *oldest*
 * successful scrape across accounts (the weakest link).
 *
 * Freshness is intentionally suppressed in Demo Mode (scrape recency is
 * meaningless there), so these tests run with Demo Mode OFF and stub the
 * `/scraping/last-scrapes` endpoint to place the data at a chosen age.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const daysAgoIso = (days: number) => new Date(Date.now() - days * DAY_MS).toISOString();

async function mockLastScrapes(
  page: Page,
  accounts: { provider: string; account_name: string; last_scrape_date: string | null }[],
) {
  await page.route("**/scraping/last-scrapes", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        accounts.map((a) => ({
          service: "banks",
          provider: a.provider,
          account_name: a.account_name,
          last_scrape_date: a.last_scrape_date,
        })),
      ),
    });
  });
}

test.describe("Budget data freshness", () => {
  test.beforeAll(async () => {
    // Freshness only renders outside Demo Mode.
    await disableDemoMode();
  });

  test("very-stale sync shows the badge and the incomplete-budget banner", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(10) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    // Badge surfaces a relative "Updated …" label.
    const badge = page.getByRole("button", { name: /Show sync details/i });
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await expect(badge).toContainText(/Updated/i);

    // Very-stale escalates to the amber banner with a Sync now CTA.
    await expect(page.getByText(/Budget may be incomplete/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /Sync now/i }).first()).toBeVisible();
  });

  test("badge popover names the stale account and links to Data Sources", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(8) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const badge = page.getByRole("button", { name: /Show sync details/i });
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await badge.click();

    // Popover lists the offending account and offers a sync link.
    await expect(page.getByText(/Out-of-date sources/i)).toBeVisible();
    await expect(page.getByText(/Checking/i).first()).toBeVisible();
    const syncLink = page.getByRole("link", { name: /Sync now/i }).first();
    await expect(syncLink).toHaveAttribute("href", "/data-sources");
  });

  test("fresh sync shows an up-to-date badge and no banner", async ({ page }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(0) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/Up to date/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Budget may be incomplete/i)).toHaveCount(0);
  });

  test("the banner can be dismissed", async ({ page }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: null },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const banner = page.getByText(/Budget may be incomplete/i);
    await expect(banner).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: /Dismiss/i }).first().click();
    await expect(banner).toHaveCount(0);
  });
});
