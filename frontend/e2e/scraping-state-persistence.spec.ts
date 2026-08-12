import { test, expect, request } from "@playwright/test";
import type { Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, API_BASE } from "./helpers";

// A throwaway OneZero account to drive a 2FA-waiting scrape against.
const ACCOUNT = "E2E Persist 2FA";
const PROCESS_ID = 7100;

async function setBankCredential(create: boolean) {
  const ctx = await request.newContext();
  try {
    if (create) {
      await ctx.post(`${API_BASE}/credentials/`, {
        data: {
          service: "banks",
          provider: "onezero",
          account_name: ACCOUNT,
          credentials: {
            email: "e2e-persist@example.com",
            password: "e2e-password",
            phoneNumber: "+15551234567",
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

test.describe("Scraping state survives leaving the page", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
    await setBankCredential(true);
  });

  test.afterAll(async () => {
    await setBankCredential(false);
    await disableDemoMode();
  });

  /**
   * Stub the whole /api/scraping/* surface. Demo Mode's dummy scrapers never
   * enter waiting_for_2fa on their own, and a live scrape here would race
   * afterAll's disableDemoMode() — see the long note in onezero-resend.spec.ts
   * for the data leak that caused. `activeScrapes` lets each test decide what
   * a cold load discovers.
   */
  async function stubScrapingApi(
    page: Page,
    activeScrapes: () => unknown[],
  ) {
    const polledProcessIds: number[] = [];

    await page.route("**/api/scraping/start", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PROCESS_ID),
      });
    });
    await page.route("**/api/scraping/status*", async (route) => {
      const url = new URL(route.request().url());
      polledProcessIds.push(
        Number(url.searchParams.get("scraping_process_id")),
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "waiting_for_2fa" }),
      });
    });
    await page.route("**/api/scraping/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(activeScrapes()),
      });
    });

    return polledProcessIds;
  }

  const cardFor = (page: Page) =>
    page
      .getByRole("heading", { name: ACCOUNT, exact: true })
      .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

  test("a 2FA prompt and its half-typed code survive navigating away and back", async ({
    page,
  }) => {
    // The scrape state used to live in the Data Sources page's own component
    // state, so any in-app navigation unmounted it and wiped everything: the
    // user came back to an idle card while the backend was still parked on the
    // 2FA prompt, with no way to answer it (submitting a code needs the
    // process id, which only existed in the discarded state).
    const polledProcessIds = await stubScrapingApi(page, () => []);

    await navigateTo(page, "/data-sources");
    const card = cardFor(page);
    await card.getByTitle(/Scrape This Source|שלוף מקור זה/).click();

    const codeInput = card.getByPlaceholder(/Code|קוד/);
    await expect(codeInput).toBeVisible({ timeout: 10_000 });
    await codeInput.fill("123");

    // Leave via the sidebar (a real in-app navigation, not a reload).
    await page.getByRole("link", { name: /Categories|קטגוריות/ }).first().click();
    await expect(page).toHaveURL(/\/categories$/);

    // Polling continues while the page is gone — the poller lives in Layout,
    // above the router.
    const polledWhileAway = polledProcessIds.length;
    await expect.poll(() => polledProcessIds.length).toBeGreaterThan(
      polledWhileAway,
    );
    expect(new Set(polledProcessIds)).toEqual(new Set([PROCESS_ID]));

    // Come back: the 2FA block is still there, still holding the typed digits,
    // and no second scrape had to be started to get it back. Returning via
    // history is a same-document pop (React Router pushed the entry), so this
    // stays an in-app navigation — and the recovered *typed code* is what pins
    // that: it exists only in the in-memory store, never in any API response,
    // so a reload could not possibly bring it back. Its survival is proof this
    // is in-memory persistence and not the cold-load /scraping/active path
    // covered by the next test.
    await page.goBack();
    await expect(page).toHaveURL(/\/data-sources$/);

    const codeInputAfter = cardFor(page).getByPlaceholder(/Code|קוד/);
    await expect(codeInputAfter).toBeVisible();
    await expect(codeInputAfter).toHaveValue("123");
    await expect(
      cardFor(page).getByRole("button", { name: /^Verify$|^אמת$/ }),
    ).toBeVisible();
  });

  test("a cold load re-adopts a scrape the backend is still running", async ({
    page,
  }) => {
    // A real reload loses every process id, so /scraping/active is the only way
    // back to an answerable 2FA prompt.
    await stubScrapingApi(page, () => [
      {
        process_id: PROCESS_ID,
        service: "banks",
        provider: "onezero",
        account_name: ACCOUNT,
        status: "waiting_for_2fa",
      },
    ]);

    await navigateTo(page, "/data-sources");

    const card = cardFor(page);
    // Nothing was started from this page — the card comes up already waiting.
    await expect(card.getByPlaceholder(/Code|קוד/)).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      card.getByRole("button", { name: /^Verify$|^אמת$/ }),
    ).toBeVisible();
    await expect(card.getByTitle(/Abort Scraping|הפסק שליפה/)).toBeVisible();
  });
});
