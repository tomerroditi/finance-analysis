import { test, expect, type Page } from "@playwright/test";
import { disableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * The budget data-freshness UX: a single "last synced" chip in the command
 * bar, driven by the *oldest* successful scrape across accounts (the weakest
 * link). Mild ages get a labelled chip ("Missing 1–5 Sep"); severe ages
 * (very stale / never synced) collapse to a bare warning triangle. Either way
 * the account detail lives in one hover/tap popover — there is no banner: it
 * repeated what the popover says and cost a full row above the budget.
 *
 * Freshness is suppressed in Demo Mode, so these run with Demo Mode OFF and
 * stub `/scraping/last-scrapes` to place the data at a chosen age.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const daysAgoIso = (days: number) =>
  new Date(Date.now() - days * DAY_MS).toISOString();

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

const badgeOf = (page: Page) => page.getByRole("button", { name: /Show sync details/i });

test.describe("Budget data freshness", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Freshness only renders outside Demo Mode. A fresh browser context
  // already starts with no stored flag (equivalent to OFF), but seeding it
  // explicitly per-test documents the requirement and stays correct if the
  // fixture setup ever changes.
  test.beforeEach(async ({ page }) => {
    await disableDemoMode(page);
  });

  test("very-stale collapses to a warning icon whose popover names every behind account", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      {
        provider: "hapoalim",
        account_name: "Checking",
        last_scrape_date: daysAgoIso(10),
      },
      {
        provider: "leumi",
        account_name: "Savings",
        last_scrape_date: daysAgoIso(12),
      },
    ]);
    await navigateTo(page, "/budget");

    // Icon only — the severe tier carries no inline label of its own.
    const badge = badgeOf(page);
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await expect(badge).toHaveText("");

    // Nothing is spelled out until the user asks for it. (The panel is in the
    // DOM — CSS `group-hover` needs it there — so this is a visibility check.)
    await expect(page.getByText(/Out-of-date sources/i)).not.toBeVisible();

    await badge.hover();
    await expect(page.getByText(/Out-of-date sources/i)).toBeVisible();
    await expect(page.getByText(/Checking/i).first()).toBeVisible();
    await expect(page.getByText(/Savings/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Sync now/i }).first()).toBeVisible();
  });

  test("mildly-stale shows a labelled chip with the same popover", async ({ page }) => {
    await mockLastScrapes(page, [
      {
        provider: "hapoalim",
        account_name: "Checking",
        last_scrape_date: daysAgoIso(5),
      },
    ]);
    await navigateTo(page, "/budget");

    // The chip names the un-scraped window rather than a vague "N ago".
    const badge = badgeOf(page);
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await expect(badge).toContainText(/Missing/i);

    await badge.hover();
    await expect(page.getByText(/Out-of-date sources/i)).toBeVisible();
    await expect(page.getByText(/Checking/i).first()).toBeVisible();
    const syncLink = page.getByRole("link", { name: /Sync now/i }).first();
    await expect(syncLink).toHaveAttribute("href", "/data-sources");
  });

  test("fresh sync shows an up-to-date chip", async ({ page }) => {
    await mockLastScrapes(page, [
      {
        provider: "hapoalim",
        account_name: "Checking",
        last_scrape_date: daysAgoIso(0),
      },
    ]);
    await navigateTo(page, "/budget");

    await expect(page.getByText(/Up to date/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Out-of-date sources/i)).toHaveCount(0);

  });

  test("accounts sharing a window collapse into one popover row", async ({ page }) => {
    // Three accounts with the same last scrape → identical missing window →
    // a single grouped row listing all three, not three repeated ranges.
    const sameDay = daysAgoIso(10);
    await mockLastScrapes(page, [
      { provider: "hapoalim", account_name: "Shir", last_scrape_date: sameDay },
      {
        provider: "one_zero",
        account_name: "Tomer",
        last_scrape_date: sameDay,
      },
      {
        provider: "isracard",
        account_name: "Joint",
        last_scrape_date: sameDay,
      },
    ]);
    await navigateTo(page, "/budget");

    const badge = badgeOf(page);
    await expect(badge).toBeVisible({ timeout: 30_000 });
    await badge.hover();

    const popover = page.locator("li").filter({ hasText: /Shir/ });
    await expect(popover).toHaveCount(1);
    await expect(popover).toContainText(/Tomer/);
    await expect(popover).toContainText(/Joint/);
  });

  test("the popover opens on hover and closes when the pointer leaves", async ({
    page,
  }) => {
    await mockLastScrapes(page, [
      {
        provider: "hapoalim",
        account_name: "Checking",
        last_scrape_date: null,
      },
    ]);
    await navigateTo(page, "/budget");

    const badge = badgeOf(page);
    await expect(badge).toBeVisible({ timeout: 30_000 });

    const details = page.getByText(/Out-of-date sources/i);
    await badge.hover();
    await expect(details).toBeVisible();

    // Hover is the whole interaction on a mouse — no click, no dismiss button.
    await page.mouse.move(0, 0);
    await expect(details).not.toBeVisible();

    // A tap (no hover precedes it on touch) pins it open until the backdrop
    // is dismissed.
    await badge.click();
    await expect(details).toBeVisible();
    // Click into the page body, not the corner: the sidebar sits above the
    // backdrop, so a top-left click never reaches it.
    await page.mouse.click(700, 400);
    await page.mouse.move(0, 0);
    await expect(details).not.toBeVisible();
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

    // Anchor on the command bar, not the budget band: these specs run with
    // Demo Mode OFF, so a CI database has no rules and therefore no band —
    // the tab strip is the only thing guaranteed to render.
    await expect(
      page.getByRole("button", { name: /Monthly Budget/i }).first(),
    ).toBeVisible({ timeout: 30_000 });
    await expect(badgeOf(page)).toHaveCount(0);
    await expect(page.getByText(/Up to date/i)).toHaveCount(0);
  });

  test("staleness shows on affected past months but not fully-settled ones", async ({
    page,
  }) => {
    // Sync at the first day of the previous month: the previous month (and the
    // current one) could still be missing transactions; two months ago cannot.
    const now = new Date();
    const prevMonthFirst = new Date(
      now.getFullYear(),
      now.getMonth() - 1,
      1,
      12,
    ).toISOString();
    const curMonthShort = now.toLocaleString("en-US", { month: "short" });
    const prevMonthShort = new Date(
      now.getFullYear(),
      now.getMonth() - 1,
      1,
    ).toLocaleString("en-US", { month: "short" });
    await mockLastScrapes(page, [
      {
        provider: "hapoalim",
        account_name: "Checking",
        last_scrape_date: prevMonthFirst,
      },
    ]);
    await navigateTo(page, "/budget");

    const badge = badgeOf(page);
    await expect(badge).toBeVisible({ timeout: 30_000 }); // current month
    await badge.hover();
    const window = page.locator("li").filter({ hasText: /Checking/ });
    // Current-month view clamps the missing window to the current month only.
    await expect(window).toContainText(curMonthShort);

    const prev = page.getByRole("button", { name: /Previous/i }).first();
    await prev.click();
    await expect(badge).toBeVisible(); // previous month — still affected
    await badge.hover();
    // The range is clamped to the previous month — it must not bleed into the
    // current month.
    await expect(window).toContainText(prevMonthShort);
    if (prevMonthShort !== curMonthShort) {
      await expect(window).not.toContainText(curMonthShort);
    }

    await prev.click();
    await expect(badgeOf(page)).toHaveCount(0); // settled
  });
});
