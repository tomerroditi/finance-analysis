import { test, expect, request } from "@playwright/test";
import { enableDemoMode, navigateTo, API_BASE } from "./helpers";

// Two throwaway accounts seeded into the demo DB so there is more than one
// card to act on. RUNNING_ACCOUNT is scraped first and parked in
// waiting_for_2fa; IDLE_ACCOUNT is the neighbour that must still be
// startable while RUNNING_ACCOUNT is mid-scrape.
const RUNNING_ACCOUNT = "E2E ScrapeAll Running";
const IDLE_ACCOUNT = "E2E ScrapeAll Idle";
const FAILED_ACCOUNT = "E2E ScrapeAll Failed";
const RUNNING_PROCESS_ID = 5001;
const FAILED_PROCESS_ID = 5003;

// These credential writes bypass the browser (Node-side `request` fixture),
// so they must declare the demo header themselves — Demo Mode is per-client
// now, and a header-less request would land these throwaway accounts in the
// real database instead of the demo one.
async function setBankCredential(accountName: string, create: boolean) {
  const ctx = await request.newContext({
    extraHTTPHeaders: { "X-FAD-Demo": "1" },
  });
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
            phoneNumber: "+972501234567",
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

test.describe("Per-account scraping concurrency", () => {
  test.beforeAll(async () => {
    // Build the demo DB before writing the throwaway credentials into it —
    // these two calls don't go through a `page`, so they carry the demo
    // header themselves rather than relying on `enableDemoMode`'s
    // localStorage seeding (which needs a browser context).
    const ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });
    try {
      await ctx.post(`${API_BASE}/testing/demo/reset`);
    } finally {
      await ctx.dispose();
    }
    await setBankCredential(RUNNING_ACCOUNT, true);
    await setBankCredential(IDLE_ACCOUNT, true);
  });

  test.afterAll(async () => {
    await setBankCredential(RUNNING_ACCOUNT, false);
    await setBankCredential(IDLE_ACCOUNT, false);
  });

  // Demo Mode itself is per-page (localStorage), so it's seeded per-test
  // here rather than alongside the beforeAll credential setup above.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("a mid-scrape account never blocks its neighbours, and Scrape All skips the ones already running", async ({
    page,
  }) => {
    // Stub the whole /api/scraping/* surface — Demo Mode's dummy scrapers
    // never enter waiting_for_2fa on their own, and a live scrape here would
    // hit a real provider's site from a test, the same concern documented in
    // onezero-resend.spec.ts.
    //
    // The behaviour under test: concurrency is per-account, not global. The
    // backend has always allowed it (ScrapingService.start_scraping_single
    // is single-flight per account, keyed on service/provider/account), but
    // the UI used to gate every card's Play button on a global
    // `isAnyScraping`, so scraping one source froze all the others. Both
    // layers of the dedupe still hold: the card whose scraper is live swaps
    // Play for Abort, and scrapeAll() refuses to relaunch an active account.
    const startedAccounts: string[] = [];
    let nextProcessId = 6000;

    await page.route("**/api/scraping/start", async (route) => {
      const body = route.request().postDataJSON() as { account: string };
      startedAccounts.push(body.account);
      const processId =
        body.account === RUNNING_ACCOUNT ? RUNNING_PROCESS_ID : nextProcessId++;
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

    // Hapoalim "Main Account" already synced successfully today: Scrape All
    // must leave it alone rather than re-download the same data.
    const SCRAPED_TODAY = "Main Account";
    await page.route("**/api/scraping/last-scrapes", async (route) => {
      const response = await route.fetch();
      const rows = (await response.json()) as {
        account_name: string;
        last_scrape_date: string | null;
      }[];
      await route.fulfill({
        response,
        json: rows.map((row) =>
          row.account_name === SCRAPED_TODAY
            ? { ...row, last_scrape_date: new Date().toISOString() }
            : row,
        ),
      });
    });

    await navigateTo(page, "/data-sources");

    const cardFor = (name: string) =>
      page
        .getByRole("heading", { name, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");
    const runningCard = cardFor(RUNNING_ACCOUNT);
    const idleCard = cardFor(IDLE_ACCOUNT);
    const playButton = (card: ReturnType<typeof cardFor>) =>
      card.getByTitle(/Scrape This Source|שלוף מקור זה/);

    await expect(runningCard).toBeVisible();
    await expect(idleCard).toBeVisible();

    // Scrape ONE account, then wait for the poller to flip its card into the
    // waiting_for_2fa block — that card is now unambiguously mid-scrape.
    await playButton(runningCard).click();
    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });
    expect(startedAccounts).toEqual([RUNNING_ACCOUNT]);

    // The regression this test exists for: a neighbouring account's Play
    // button must still be live and must actually dispatch a scrape.
    await expect(playButton(idleCard)).toBeEnabled();
    await playButton(idleCard).click();
    await expect
      .poll(() => startedAccounts)
      .toEqual([RUNNING_ACCOUNT, IDLE_ACCOUNT]);

    // Located by test id rather than accessible name: the label tracks the
    // multi-select (it reads "Scrape (N)" once sources are picked), so a
    // name-based locator would break the moment a selection exists.
    const scrapeAllButton = page.getByTestId("scrape-launch");

    // Scrape All also stays usable mid-run: it is how the user launches the
    // accounts that are still idle. Its dedupe (useScraping.scrapeAll, unit
    // tested in useScraping.test.ts) is what keeps the two already-running
    // accounts from being relaunched.
    await expect(scrapeAllButton).toBeEnabled();
    await scrapeAllButton.click();

    // The pre-existing demo accounts get launched…
    await expect
      .poll(() => startedAccounts.length)
      .toBeGreaterThan(2);
    await page.waitForTimeout(500);
    // …while neither active account is dispatched a second time.
    expect(
      startedAccounts.filter((a) => a === RUNNING_ACCOUNT),
    ).toHaveLength(1);
    expect(startedAccounts.filter((a) => a === IDLE_ACCOUNT)).toHaveLength(1);
    // …and an account already synced today is skipped entirely.
    expect(startedAccounts).not.toContain(SCRAPED_TODAY);
  });

  test("a running scrape is still shown after navigating away and back", async ({
    page,
  }) => {
    // Cold-load hydration: this browser never clicked Scrape, so the store
    // starts empty and GET /api/scraping/active is the only thing that can
    // tell the card a scrape is in flight. (State surviving an in-app
    // navigation is a different guarantee, covered by
    // scraping-state-persistence.spec.ts, which stubs /active empty.)
    const ACTIVE = {
      process_id: RUNNING_PROCESS_ID,
      service: "banks",
      provider: "onezero",
      account_name: RUNNING_ACCOUNT,
      status: "waiting_for_2fa",
    };

    await page.route("**/api/scraping/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([ACTIVE]),
      });
    });
    await page.route("**/api/scraping/status*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "waiting_for_2fa" }),
      });
    });

    await navigateTo(page, "/data-sources");

    const runningCard = page
      .getByRole("heading", { name: RUNNING_ACCOUNT, exact: true })
      .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

    // Never clicked Scrape in this browser — the card is live purely because
    // the backend said the scrape is still in flight.
    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });

    // Leave the page (unmounting the hook) and come back.
    await navigateTo(page, "/transactions");
    await navigateTo(page, "/data-sources");

    await expect(runningCard.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });
    // Still mid-scrape, so the card offers Abort rather than Scrape.
    const abortButton = runningCard.getByTitle(/Abort Scraping|הפסק שליפה/);
    await expect(abortButton).toBeVisible();

    // Aborting is the user's own choice, not a failure: the card must read
    // "Aborted" with its own badge, never "Failed".
    await page.route("**/api/scraping/abort", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "aborted" }),
      });
    });
    await abortButton.click();
    await expect(runningCard.getByTestId("scrape-aborted-badge")).toBeVisible();
    await expect(runningCard.getByText(/^Aborted$|^בוטל$/)).toBeVisible();
    await expect(runningCard.getByText(/^Failed$|^נכשל$/)).toHaveCount(0);
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

      // The panel is portalled to <body>, so it is found by role, not inside
      // the card.
      const tooltip = page.getByRole("tooltip");
      // Friendly, translated explanation chosen by error_type…
      await expect(
        tooltip.getByText(/rejected the saved login|דחה את פרטי ההתחברות/),
      ).toBeVisible();
      // …with the provider's raw text still available underneath.
      await expect(tooltip.getByText(ERROR_MESSAGE)).toBeVisible();

      // Anchored inside the 12px icon, the panel used to shrink-wrap to one
      // word per line and poke out past the card and the viewport. It must be
      // a readable width and sit wholly on screen.
      const box = await tooltip.boundingBox();
      const viewport = page.viewportSize();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThan(200);
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
      expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
    } finally {
      await setBankCredential(FAILED_ACCOUNT, false);
    }
  });

  test("picking sources narrows the scrape, and the toolbar stays one row on a phone", async ({
    page,
  }) => {
    // Nothing picked must keep meaning "scrape everything" — the selection is
    // additive, not a new mandatory step. Stubbed like the test above so no
    // real provider is contacted.
    const startedAccounts: string[] = [];
    let nextProcessId = 7000;

    await page.route("**/api/scraping/start", async (route) => {
      const body = route.request().postDataJSON() as { account: string };
      startedAccounts.push(body.account);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(nextProcessId++),
      });
    });
    await page.route("**/api/scraping/status*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "in_progress" }),
      });
    });

    await page.setViewportSize({ width: 375, height: 800 });
    await navigateTo(page, "/data-sources");

    const scrapeButton = page.getByTestId("scrape-launch");
    const connectButton = page.getByRole("button", {
      name: "Connect Account",
      exact: true,
    });
    const periodSelect = page.locator("main select").first();
    await expect(scrapeButton).toBeVisible();

    // The three toolbar controls share one row at phone width: same vertical
    // band, and nothing pushed off the side of the viewport.
    const boxes = await Promise.all(
      [periodSelect, scrapeButton, connectButton].map((l) => l.boundingBox()),
    );
    for (const box of boxes) expect(box).not.toBeNull();
    const tops = boxes.map((b) => b!.y);
    expect(Math.max(...tops) - Math.min(...tops)).toBeLessThan(8);
    for (const box of boxes) {
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(375);
    }

    const cardFor = (name: string) =>
      page
        .getByRole("heading", { name, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

    // Tick one source: the button stops offering "everything" and names the
    // count instead.
    await expect(scrapeButton).toHaveText(/Scrape All|שלוף הכל/);
    await cardFor(IDLE_ACCOUNT).getByTestId("select-source").check();
    await expect(page.getByTestId("selection-bar")).toContainText(
      /1 source selected|נבחר מקור אחד/,
    );
    await expect(scrapeButton).toHaveText(/\(1\)/);

    await scrapeButton.click();
    await expect.poll(() => startedAccounts).toEqual([IDLE_ACCOUNT]);
    // Give any stray dispatch a chance to land before asserting the negative.
    await page.waitForTimeout(500);
    expect(startedAccounts).toEqual([IDLE_ACCOUNT]);

    // Clearing hands the button back its scrape-everything default.
    await page.getByTestId("selection-bar").getByRole("button").last().click();
    await expect(page.getByTestId("selection-bar")).toHaveCount(0);
    await expect(scrapeButton).toHaveText(/Scrape All|שלוף הכל/);
    await scrapeButton.click();
    await expect.poll(() => startedAccounts.length).toBeGreaterThan(2);
  });
});
