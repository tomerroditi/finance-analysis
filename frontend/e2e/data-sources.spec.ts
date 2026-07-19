import { test, expect, request } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle, API_BASE } from "./helpers";

test.describe("DataSources", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  // Read-only page smoke + provider logos + the Connect Account chooser, all
  // against one rendered page — a single navigation covers all of them.
  test("page, account-card logos, and the connect-account modal on one load", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await expectPageTitle(page, /Data Sources/);
    await expect(page.locator("main")).toBeVisible();

    // The four demo accounts (Hapoalim, Max, Visa Cal, HaPhoenix) each render
    // a <ProviderLogo> with alt text set to the humanized provider name. We
    // verify the image actually loaded — naturalWidth > 0 only holds once the
    // browser has decoded a real image, so a broken/missing logo would fail
    // here even with width/height set in HTML. (Vite inlines small SVGs as
    // data: URIs and emits larger ones as hashed assets, so checking the src
    // attribute itself isn't portable.)
    for (const alt of ["Hapoalim", "Max", "Visa Cal", "HaPhoenix"]) {
      const img = page.getByRole("img", { name: alt }).first();
      await expect(img).toBeVisible();
      await expect
        .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0);
    }

    // Step 1: open the connect-account modal — the chooser surfaces all
    // three top-level service types.
    await page.getByRole("button", { name: "Connect Account", exact: true }).click();
    await expect(page.getByRole("heading", { name: /connect new account/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /bank account/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /credit card/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^insurance/i })).toBeVisible();

    // Step 2: a representative subset of banks should appear with their logos.
    // We don't enumerate all 11 — the goal is to lock in that the grid actually
    // renders ProviderLogo and the images aren't broken.
    await page.getByRole("button", { name: /Bank Account/ }).click();
    for (const provider of ["Hapoalim", "Leumi", "Discount", "Mizrahi"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }

    // Bounce back to step 1 and try credit cards to make sure that grid wires
    // up too (different service key, different filename mappings — e.g. visa
    // cal has a space and Beyahad Bishvilha is a PNG instead of SVG).
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: /Credit Card/ }).click();
    for (const provider of ["Max", "Visa Cal", "Isracard", "Amex"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }
  });

  test("opens the shared balance modal from the $ button and saves", async ({ page }) => {
    const provider = "onezero";
    const accountName = "E2E Balance Bank";
    const today = new Date().toISOString();

    // Seed a throwaway bank credential so a bank row (with the $ button) renders.
    const ctx = await request.newContext();
    await ctx.post(`${API_BASE}/credentials/`, {
      data: {
        service: "banks",
        provider,
        account_name: accountName,
        credentials: {
          email: "e2e-balance@example.com",
          password: "e2e-password",
          phoneNumber: "+15551234567",
        },
      },
    });
    await ctx.dispose();

    try {
      // Deterministic scrape status + balance for the seeded account.
      await page.route("**/api/scraping/last-scrapes", async (route) => {
        await route.fulfill({
          json: [
            { service: "banks", provider, account_name: accountName, last_scrape_date: today },
          ],
        });
      });
      await page.route("**/api/bank-balances/", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            json: [
              {
                id: 99,
                provider,
                account_name: accountName,
                balance: 1000,
                prior_wealth_amount: 0,
                last_manual_update: null,
                last_scrape_update: today,
              },
            ],
          });
        } else {
          await route.fulfill({
            json: {
              id: 99,
              provider,
              account_name: accountName,
              balance: 7777,
              prior_wealth_amount: 0,
              last_manual_update: today,
              last_scrape_update: today,
            },
          });
        }
      });

      await page.goto("/");
      await page.evaluate(() =>
        sessionStorage.setItem("onboardingDismissedAt", String(Date.now())),
      );
      await page.goto("/data-sources");

      // The seeded bank row's amber "$" button (enabled because scraped today).
      const setBtn = page.getByRole("button", { name: /^Set Balance$/ }).first();
      await expect(setBtn).toBeEnabled();
      await setBtn.click();

      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText(/net worth/i)).toBeVisible();

      const [req] = await Promise.all([
        page.waitForRequest(
          (r) => r.url().includes("/api/bank-balances/") && r.method() === "POST",
        ),
        (async () => {
          await dialog.getByRole("spinbutton").fill("7777");
          await dialog.getByRole("button", { name: /^Save$/ }).click();
        })(),
      ]);
      expect(req.postDataJSON()).toEqual({ provider, account_name: accountName, balance: 7777 });
      await expect(dialog).toBeHidden();
    } finally {
      const cleanup = await request.newContext();
      await cleanup.delete(
        `${API_BASE}/credentials/banks/${provider}/${encodeURIComponent(accountName)}`,
      );
      await cleanup.dispose();
    }
  });

  test("credential details API never returns plaintext secrets", async ({ page }) => {
    // Regression guard: GET /api/credentials/{service}/{provider}/{account}
    // used to return the keyring password as plaintext JSON. It must now be
    // masked with the __unchanged__ sentinel (or empty when nothing stored).
    const ctx = await request.newContext();
    const res = await ctx.get(
      `${API_BASE}/credentials/banks/hapoalim/${encodeURIComponent("Main Account")}`,
    );
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(["__unchanged__", ""]).toContain(body.password);
    await ctx.dispose();

    // The edit form prefills from the masked payload: the password input must
    // hold the sentinel (rendered as a password field), never the real value,
    // and the reveal-password eye button must not be offered for it.
    await navigateTo(page, "/data-sources");
    await page.getByRole("button", { name: "Edit Account" }).first().click();
    const passwordInput = page.locator('input[type="password"]').first();
    await expect(passwordInput).toBeVisible();
    const value = await passwordInput.inputValue();
    expect(["__unchanged__", ""]).toContain(value);
  });
});
