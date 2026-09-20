import { test, expect, request } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData, API_BASE } from "./helpers";

// A throwaway account so the assertions target one unambiguous card rather
// than whichever demo source happens to sort first.
const ACCOUNT = "E2E Persistence Source";
const PROCESS_ID = 7001;

async function setBankCredential(create: boolean) {
  // Bypasses the browser (Node-side `request` fixture), so it declares the
  // demo header itself — Demo Mode is per-client, and a header-less request
  // would write this throwaway account into the real database.
  const ctx = await request.newContext({
    extraHTTPHeaders: { "X-FAD-Demo": "1" },
  });
  try {
    if (create) {
      await ctx.post(`${API_BASE}/credentials/`, {
        data: {
          service: "banks",
          provider: "onezero",
          account_name: ACCOUNT,
          credentials: {
            email: "e2e-persistence@example.com",
            password: "e2e-password",
            phoneNumber: "+972501234567",
          },
        },
      });
    } else {
      await ctx.delete(
        `${API_BASE}/credentials/banks/onezero/${encodeURIComponent(ACCOUNT)}`,
      );
    }
  } finally {
    await ctx.dispose();
  }
}

/**
 * Client-side navigation via the sidebar.
 *
 * `navigateTo` from helpers.ts does `page.goto`, i.e. a full document load —
 * that tears down the whole JS heap, so it exercises cold-load hydration
 * (already covered in scrape-all-dedupe.spec.ts), not the in-app navigation
 * these tests are about.
 */
async function navigateInApp(
  page: import("@playwright/test").Page,
  name: RegExp,
  urlPattern: RegExp,
) {
  await page.getByRole("link", { name }).first().click();
  await expect(page).toHaveURL(urlPattern);
}

const cardFor = (page: import("@playwright/test").Page) =>
  page
    .getByRole("heading", { name: ACCOUNT, exact: true })
    .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

test.describe("Scraping state survives navigation", () => {
  test.beforeAll(async () => {
    // Mutating spec: rebuild the shared demo DB before seeding, or a
    // predecessor's writes leak into these assertions.
    await resetDemoData();
    await setBankCredential(true);
  });

  test.afterAll(async () => {
    await setBankCredential(false);
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("a scrape keeps running, and stays answerable, while the user is on another page", async ({
    page,
  }) => {
    // Scraper state used to live in `useScraping`'s `useState`, so leaving
    // Data Sources unmounted it: the 2s poller stopped, and the `process_id`
    // a waiting 2FA prompt needs went with it. `GET /api/scraping/active`
    // made the running/waiting part recoverable ON REMOUNT, but that is a
    // different guarantee — nothing advanced while the user was away.
    //
    // `/active` is deliberately stubbed EMPTY throughout. Everything asserted
    // below therefore comes from the app-wide store + poller that
    // `ScrapingTracker` owns above the router, not from re-hydration.
    await page.route("**/api/scraping/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    // The demo dummy scrapers never park on 2FA by themselves, and a live
    // scrape would reach a real provider from a test — same reasoning as
    // onezero-resend.spec.ts.
    await page.route("**/api/scraping/start", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PROCESS_ID),
      });
    });

    let statusPolls = 0;
    await page.route("**/api/scraping/status*", async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("scraping_process_id") === String(PROCESS_ID)) {
        statusPolls += 1;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "waiting_for_2fa" }),
      });
    });

    await navigateTo(page, "/data-sources");
    const card = cardFor(page);
    await expect(card).toBeVisible();

    await card.getByTitle(/Scrape This Source|שלוף מקור זה/).click();
    await expect(card.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });

    // Navigate away in-app. The Data Sources page unmounts; the tracker,
    // which lives in Layout above the router, does not.
    await navigateInApp(page, /Transactions/i, /transactions/);
    const pollsOnLeaving = statusPolls;

    // Polling has to keep going off-page — this is what makes a scrape that
    // finishes elsewhere fire its cache invalidations instead of leaving
    // freshly scraped transactions invisible for the full staleTime.
    await expect
      .poll(() => statusPolls, { timeout: 10_000 })
      .toBeGreaterThan(pollsOnLeaving);

    // Back on the page, the card is still mid-2FA — with `/active` empty,
    // only retained state can produce this.
    await navigateInApp(page, /Data Sources/i, /data-sources/);
    await expect(cardFor(page).getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      cardFor(page).getByTitle(/Abort Scraping|הפסק שליפה/),
    ).toBeVisible();
  });

  test("a scrape that finishes while the user is away is still reported on return", async ({
    page,
  }) => {
    // `/active` only ever lists what is LIVE, so it structurally cannot
    // report a scrape that already finished. Before the store, a scrape that
    // completed off-page left no trace at all: coming back showed an idle
    // card, with no success or failure for the user to read.
    await page.route("**/api/scraping/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/scraping/start", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PROCESS_ID),
      });
    });

    let finished = false;
    await page.route("**/api/scraping/status*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: finished ? "failed" : "in_progress",
          error_type: finished ? "INVALID_PASSWORD" : undefined,
        }),
      });
    });

    await navigateTo(page, "/data-sources");
    await expect(cardFor(page)).toBeVisible();
    await cardFor(page).getByTitle(/Scrape This Source|שלוף מקור זה/).click();
    await expect(
      cardFor(page).getByTitle(/Abort Scraping|הפסק שליפה/),
    ).toBeVisible({ timeout: 10_000 });

    // Leave in-app, then let the scrape fail while the page is unmounted.
    await navigateInApp(page, /Transactions/i, /transactions/);
    finished = true;
    // Give the off-page poller at least one tick to observe the change. A
    // fixed wait rather than a web-first assertion: the thing being waited
    // on is a poll that happens with no page on screen to assert against.
    await page.waitForTimeout(3000);

    await navigateInApp(page, /Data Sources/i, /data-sources/);

    await expect(cardFor(page).getByText(/^Failed$|^נכשל$/)).toBeVisible({
      timeout: 10_000,
    });
  });
});
