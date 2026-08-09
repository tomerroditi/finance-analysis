import { test, expect, request } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, API_BASE } from "./helpers";

// Two throwaway accounts seeded into the demo DB so "Scrape All" has more
// than one card to act on. One (RUNNING_ACCOUNT) is driven into
// waiting_for_2fa before "Scrape All" fires a second time; the other
// (IDLE_ACCOUNT) stays idle and must still be launched.
const RUNNING_ACCOUNT = "E2E ScrapeAll Running";
const IDLE_ACCOUNT = "E2E ScrapeAll Idle";
const FAILED_ACCOUNT = "E2E ScrapeAll Failed";
const RUNNING_PROCESS_ID = 5001;
const FAILED_PROCESS_ID = 5003;

async function setBankCredential(accountName: string, create: boolean) {
  const ctx = await request.newContext();
  try {
    if (create) {
      await ctx.post(`${API_BASE}/credentials/`, {
        data: {
          service: "banks",
          provider: "onezero",
          account_name: accountName,
          credentials: {
            email: `${accountName.replace(/\s+/g, "-").toLowerCase()}@example.com`,
            password: "e2e-password",
            phoneNumber: "+15551234567",
          },
        },
      });
    } else {
      await ctx.delete(
        `${API_BASE}/credentials/banks/onezero/${encodeURIComponent(accountName)}`,
      );
    }
  } finally {
    await ctx.dispose();
  }
}

test.describe("Parallel scraping + Scrape All burst guard", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
    await setBankCredential(RUNNING_ACCOUNT, true);
    await setBankCredential(IDLE_ACCOUNT, true);
  });

  test.afterAll(async () => {
    await setBankCredential(RUNNING_ACCOUNT, false);
    await setBankCredential(IDLE_ACCOUNT, false);
    await disableDemoMode();
  });

  test("one account scraping never blocks starting another, and Scrape All skips the ones already running", async ({
    page,
  }) => {
    // Stub the whole /api/scraping/* surface — Demo Mode's dummy scrapers
    // never enter waiting_for_2fa on their own, and a live scrape here would
    // race disableDemoMode() in afterAll the same way documented in
    // onezero-resend.spec.ts.
    //
    // Scraping is per-account and parallel: a source that is mid-scrape (or
    // parked on a 2FA prompt) must not disable every other source's scrape
    // button, which is exactly what the old global `isAnyScraping` gate did —
    // the user could only ever run one account at a time. The dedupe that used
    // to be enforced by disabling "Scrape All" now has to hold on its own, in
    // `scrapeAll`'s per-account check, because the button stays clickable.
    const startedAccounts: string[] = [];
    let nextProcessId = 6000;

    await page.route("**/api/scraping/start", async (route) => {
      const body = route.request().postDataJSON() as { account: string };
      startedAccounts.push(body.account);
      const processId =
        body.account === RUNNING_ACCOUNT
          ? RUNNING_PROCESS_ID
          : nextProcessId++;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(processId),
      });
    });

    await page.route("**/api/scraping/status*", async (route) => {
      const url = new URL(route.request().url());
      const polledId = url.searchParams.get("scraping_process_id");
      // RUNNING_ACCOUNT's process reports waiting_for_2fa and stays there —
      // it must look "already scraping" for the whole test. Every other
      // account (including IDLE_ACCOUNT and the pre-existing demo accounts)
      // reports in_progress so their cards don't confuse the assertions.
      const status =
        polledId === String(RUNNING_PROCESS_ID)
          ? "waiting_for_2fa"
          : "in_progress";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status }),
      });
    });

    await navigateTo(page, "/data-sources");

    await expect(page.getByText(RUNNING_ACCOUNT, { exact: false })).toBeVisible();
    await expect(page.getByText(IDLE_ACCOUNT, { exact: false })).toBeVisible();

    const cardFor = (accountName: string) =>
      page
        .getByRole("heading", { name: accountName, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");
    const runningCard = cardFor(RUNNING_ACCOUNT);
    const idleCard = cardFor(IDLE_ACCOUNT);

    // Drive ONE account into waiting_for_2fa from its own card, leaving every
    // other account idle.
    await runningCard.getByTitle(/Scrape This Source|שלוף מקור זה/).click();
    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });

    // The core of this change: another account's scrape button is still live.
    const idleScrapeButton = idleCard.getByTitle(
      /Scrape This Source|שלוף מקור זה/,
    );
    await expect(idleScrapeButton).toBeEnabled();
    await idleScrapeButton.click();
    await expect.poll(() => startedAccounts).toContain(IDLE_ACCOUNT);
    // Both are now running side by side.
    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible();
    await expect(idleCard.getByTitle(/Abort Scraping|הפסק שליפה/)).toBeVisible({
      timeout: 10_000,
    });

    // "Scrape All" stays available while scrapes run — it is how the user
    // picks up the sources that are still idle. Located structurally, not by
    // its accessible name: the label gains a running count while any scraper
    // is active (DataSources.tsx), so a name-based locator stops matching
    // right when we need it — the same gotcha documented in
    // onezero-resend.spec.ts for the Resend button. The "Connect Account"
    // button's name never changes, so walk to its preceding sibling instead.
    const scrapeAllButton = page
      .getByRole("button", { name: "Connect Account", exact: true })
      .locator("xpath=preceding-sibling::button[1]");
    await expect(scrapeAllButton).toBeEnabled();

    const startedBeforeScrapeAll = [...startedAccounts];
    await scrapeAllButton.click();
    // It must launch the remaining demo accounts…
    await expect
      .poll(() => startedAccounts.length)
      .toBeGreaterThan(startedBeforeScrapeAll.length);
    // …and must NOT re-dispatch either already-active account. A second start
    // for an account mid-2FA would fire a second OTP SMS, superseding the code
    // the user is already looking at.
    await page.waitForTimeout(500);
    const startedAfterScrapeAll = startedAccounts.slice(
      startedBeforeScrapeAll.length,
    );
    expect(startedAfterScrapeAll).not.toContain(RUNNING_ACCOUNT);
    expect(startedAfterScrapeAll).not.toContain(IDLE_ACCOUNT);

    // With every account now active there is nothing left to launch, so the
    // button retires itself.
    await expect(scrapeAllButton).toBeDisabled();
  });

  test("a failed scrape explains itself and still exposes the provider's text", async ({
    page,
  }) => {
    // The backend records the failure as two fields: `error_type` (the
    // category) and `error_message` (the provider's own text). The card must
    // use the first for a readable explanation and still surface the second —
    // before that split, one string had to be both, and a scrape got logged as
    // the contentless "Login failed with result: unknown_error".
    const ERROR_MESSAGE =
      "login invalid_password: detected on https://bank.test/login; " +
      "page showing: Wrong password";

    await setBankCredential(FAILED_ACCOUNT, true);
    try {
      await page.route("**/api/scraping/start", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(FAILED_PROCESS_ID),
        });
      });
      await page.route("**/api/scraping/status*", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "failed",
            error_message: ERROR_MESSAGE,
            error_type: "INVALID_PASSWORD",
          }),
        });
      });

      await navigateTo(page, "/data-sources");

      const card = page
        .getByRole("heading", { name: FAILED_ACCOUNT, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

      const scrapeButton = card.getByTitle(/Scrape This Source|שלוף מקור זה/);
      await expect(scrapeButton).toBeVisible();
      await scrapeButton.click();

      // The card must show the generic "Failed" label AND an info affordance
      // that reveals the failure detail — not just "Failed" alone, which would
      // hide everything the backend went out of its way to compute.
      await expect(card.getByText(/^Failed$|^נכשל$/)).toBeVisible({
        timeout: 10_000,
      });
      const errorInfoButton = card.getByRole("button", {
        name: /Show error details|הצגת פרטי השגיאה/,
      });
      await expect(errorInfoButton).toBeVisible();
      await errorInfoButton.click();

      // Friendly, translated explanation chosen by error_type…
      await expect(
        card.getByText(/rejected the saved login|דחה את פרטי ההתחברות/),
      ).toBeVisible();
      // …with the provider's raw text still available underneath.
      await expect(card.getByText(ERROR_MESSAGE)).toBeVisible();
    } finally {
      await setBankCredential(FAILED_ACCOUNT, false);
    }
  });
});
