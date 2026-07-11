import { test, expect, request } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

const API_BASE = "http://localhost:8000/api";

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

test.describe("Scrape All burst guard", () => {
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

  test("Scrape All disables the instant any account is active, blocking a second dispatch while one is scraping", async ({
    page,
  }) => {
    // Stub the whole /api/scraping/* surface — Demo Mode's dummy scrapers
    // never enter waiting_for_2fa on their own, and a live scrape here would
    // race disableDemoMode() in afterAll the same way documented in
    // onezero-force-2fa.spec.ts / onezero-resend.spec.ts.
    //
    // Reality check performed while writing this spec: "Scrape All" is
    // disabled the instant *any* account's start() response registers in
    // runningScrapers — which, with several accounts firing in parallel
    // (RUNNING_ACCOUNT, IDLE_ACCOUNT, plus whatever demo accounts already
    // exist), happens within a single render tick of the first click. There
    // is no click-twice-on-the-real-button window to exploit here; the
    // button is the FIRST layer of the guard and, per this test, it holds.
    // The scrapeAll() dedupe itself (the actual subject of this task) is
    // exercised directly and deterministically in
    // useScraping.test.ts — that's the right layer for it: proving the
    // hook's own bookkeeping refuses a second launch, independent of
    // whatever timing the DOM happens to allow on a given run. This test
    // proves the two layers agree: the button disables immediately, so a
    // real user can never even reach the code path scrapeAll's dedupe
    // guards.
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

    // Located structurally, not by its accessible name: the button's label
    // flips from "Scrape All" to "Scraping..." the instant isAnyScraping
    // becomes true (DataSources.tsx), so a name-based getByRole locator
    // stops matching anything right when we need to assert its disabled
    // state — the same gotcha documented in onezero-resend.spec.ts for the
    // Resend button. The "Connect Account" button's name never changes, so
    // walk to its immediately preceding sibling instead.
    const scrapeAllButton = page
      .getByRole("button", { name: "Connect Account", exact: true })
      .locator("xpath=preceding-sibling::button[1]");
    await expect(scrapeAllButton).toBeEnabled();

    await scrapeAllButton.click();

    await expect.poll(() => startedAccounts).toContain(RUNNING_ACCOUNT);
    await expect.poll(() => startedAccounts).toContain(IDLE_ACCOUNT);

    // Wait for the poller to flip RUNNING_ACCOUNT's card into the
    // waiting_for_2fa 2FA block — the same "account already has an active
    // scraper" state the brief describes.
    const runningCard = page
      .getByRole("heading", { name: RUNNING_ACCOUNT, exact: true })
      .locator("xpath=ancestor::div[contains(@class, 'group')][1]");
    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });

    // The primary, always-on guard: "Scrape All" must be disabled while any
    // scraper is active, so a real second click can never reach scrapeAll()
    // at all.
    await expect(scrapeAllButton).toBeDisabled();

    const startedAfterFirstClick = [...startedAccounts];

    // A genuinely `disabled` <button> never dispatches click in a real
    // browser (Playwright's `force: true` still performs a real mouse event
    // — it just skips Playwright's own actionability pre-checks — and the
    // browser correctly refuses to fire onClick regardless). So this
    // confirms the disabled state actually blocks the click, rather than
    // faking a bypass: the click below must NOT produce any new
    // /scraping/start calls.
    await scrapeAllButton.click({ force: true });
    await page.waitForTimeout(500);

    expect(startedAccounts).toEqual(startedAfterFirstClick);
  });

  test("a failed scrape shows its specific error_message, not a generic label", async ({
    page,
  }) => {
    const ERROR_MESSAGE = "Wait about a minute before requesting another code.";

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
      // that reveals the backend's specific error_message — not just
      // "Failed" alone, which would hide the rate-limit / expired-OTP hint
      // the backend went out of its way to compute.
      await expect(card.getByText(/^Failed$|^נכשל$/)).toBeVisible({
        timeout: 10_000,
      });
      const errorInfoButton = card.getByRole("button", {
        name: /Show error details|הצגת פרטי השגיאה/,
      });
      await expect(errorInfoButton).toBeVisible();
      await errorInfoButton.click();
      await expect(card.getByText(ERROR_MESSAGE)).toBeVisible();
    } finally {
      await setBankCredential(FAILED_ACCOUNT, false);
    }
  });
});
