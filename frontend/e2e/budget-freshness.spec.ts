import { test, expect, type Page } from "@playwright/test";
import { disableDemoMode, navigateTo } from "./helpers";

/**
 * The budget data-freshness UX: an in-header "last synced" chip for mildly
 * aging data, a stale-KPI treatment, and a banner (listing every behind
 * account) for very-stale / never-synced data. Driven by the *oldest*
 * successful scrape across accounts (the weakest link).
 *
 * Freshness is suppressed in Demo Mode, so these run with Demo Mode OFF and
 * stub `/scraping/last-scrapes` to place the data at a chosen age. The chip
 * and the banner are mutually exclusive — mild ages get the chip, severe ages
 * get the banner, never both.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const daysAgoIso = (days: number) => new Date(Date.now() - days * DAY_MS).toISOString();

async function mockLastScrapes(
  page: Page,
  accounts: {
    provider: string;
    account_name: string;
    last_scrape_date: string | null;
    service?: string;
  }[],
) {
  await page.route("**/scraping/last-scrapes", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        accounts.map((a) => ({
          service: a.service ?? "banks",
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

  test("very-stale shows the banner with every behind account and no chip", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(10) },
      { provider: "leumi", account_name: "Savings", last_scrape_date: daysAgoIso(12) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    // Banner lists ALL out-of-sync accounts and offers a single Sync now CTA.
    await expect(page.getByText(/Budget may be incomplete/i)).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/Checking/i)).toBeVisible();
    await expect(page.getByText(/Savings/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /Sync now/i }).first()).toBeVisible();

    // No redundant chip alongside the banner.
    await expect(page.getByRole("button", { name: /Show sync details/i })).toHaveCount(0);
  });

  test("mildly-stale shows an in-header chip with a details popover, no banner", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(5) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    // The chip is the only freshness element for mild staleness, and it names
    // the un-scraped window rather than a vague "N ago".
    const badge = page.getByRole("button", { name: /Show sync details/i });
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await expect(badge).toContainText(/Missing/i);
    await expect(page.getByText(/Budget may be incomplete/i)).toHaveCount(0);

    // Popover names the account and links to Data Sources.
    await badge.click();
    await expect(page.getByText(/Out-of-date sources/i)).toBeVisible();
    await expect(page.getByText(/Checking/i).first()).toBeVisible();
    const syncLink = page.getByRole("link", { name: /Sync now/i }).first();
    await expect(syncLink).toHaveAttribute("href", "/data-sources");
  });

  test("fresh sync shows an up-to-date chip and no banner", async ({ page }) => {
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: daysAgoIso(0) },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/Up to date/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Budget may be incomplete/i)).toHaveCount(0);
  });

  test("accounts sharing a window collapse into one row", async ({ page }) => {
    // Three accounts with the same last scrape → identical missing window →
    // a single grouped row listing all three, not three repeated ranges.
    const sameDay = daysAgoIso(10);
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Shir", last_scrape_date: sameDay },
      { provider: "one_zero", account_name: "Tomer", last_scrape_date: sameDay },
      { provider: "isracard", account_name: "Joint", last_scrape_date: sameDay },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const banner = page.locator("div", { hasText: /Budget may be incomplete/i }).last();
    await expect(banner).toBeVisible({ timeout: 30_000 });

    // One window row, all three accounts named within it.
    await expect(banner.locator("li")).toHaveCount(1);
    await expect(banner.locator("li")).toContainText(/Shir/);
    await expect(banner.locator("li")).toContainText(/Tomer/);
    await expect(banner.locator("li")).toContainText(/Joint/);
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

  test("a stale insurance sync does not flag the budget", async ({ page }) => {
    // Insurance is scraped but unrelated to budget transactions — even a
    // never-synced insurance account must not raise a freshness warning.
    await mockLastScrapes(page, [
      {
        provider: "menora",
        account_name: "Pension",
        last_scrape_date: daysAgoIso(40),
        service: "insurances",
      },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/Budget may be incomplete/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Show sync details/i })).toHaveCount(0);
    await expect(page.getByText(/Up to date/i)).toHaveCount(0);
  });

  test("staleness shows on affected past months but not fully-settled ones", async ({
    page,
  }) => {
    // Sync at the first day of the previous month: the previous month (and the
    // current one) could still be missing transactions; two months ago cannot.
    const now = new Date();
    const prevMonthFirst = new Date(now.getFullYear(), now.getMonth() - 1, 1, 12).toISOString();
    const curMonthShort = now.toLocaleString("en-US", { month: "short" });
    const prevMonthShort = new Date(now.getFullYear(), now.getMonth() - 1, 1).toLocaleString(
      "en-US",
      { month: "short" },
    );
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Checking", last_scrape_date: prevMonthFirst },
    ]);
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const banner = page.locator("div", { hasText: /Budget may be incomplete/i }).last();
    await expect(banner).toBeVisible({ timeout: 30_000 }); // current month
    // Current-month view clamps to the current month only.
    await expect(banner).toContainText(curMonthShort);

    const prev = page.getByRole("button", { name: /Previous/i }).first();
    await prev.click();
    await page.waitForLoadState("networkidle");
    await expect(banner).toBeVisible(); // previous month — still affected
    // The range is clamped to the previous month — it must not bleed into the
    // current month.
    await expect(banner).toContainText(prevMonthShort);
    if (prevMonthShort !== curMonthShort) {
      await expect(banner).not.toContainText(curMonthShort);
    }

    await prev.click();
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/Budget may be incomplete/i)).toHaveCount(0); // settled
  });
});
