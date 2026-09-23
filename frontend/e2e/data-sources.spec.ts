import { test, expect, request } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle, API_BASE, resetDemoData } from "./helpers";

// Every `request.newContext()` below declares the demo header itself: the
// `request` fixture/module is Playwright's own HTTP client, which does not
// run the app's JS, so the axios interceptor that attaches `X-FAD-Demo` from
// localStorage never runs for it. Without it, these direct backend calls
// would read/write the real database instead of the demo one each test's
// own page (seeded via `enableDemoMode(page)`) is showing.
test.describe("DataSources", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  // Read-only page smoke + provider logos + the Connect Account chooser, all
  // against one rendered page — a single navigation covers all of them.
  test("page, account-card logos, and the connect-account modal on one load", async ({
    page,
  }) => {
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
    await page
      .getByRole("button", { name: "Connect Account", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /connect new account/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /bank account/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /credit card/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^insurance/i }),
    ).toBeVisible();

    // Step 2: a representative subset of banks should appear with their logos.
    // We don't enumerate all 11 — the goal is to lock in that the grid actually
    // renders ProviderLogo and the images aren't broken.
    await page.getByRole("button", { name: /Bank Account/ }).click();
    for (const provider of ["Hapoalim", "Leumi", "Discount", "Mizrahi"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }

    // OneZero's OTP API only accepts +9725XXXXXXXX: the phone field carries a
    // fixed +972 prefix, folds a typed local 05X number into it, and blocks
    // saving anything that is not a full Israeli mobile number. Nothing is
    // submitted — Back leaves the form untouched.
    await page.getByRole("img", { name: "One Zero" }).last().click();
    const phoneInput = page.locator("#credential-phone");
    await expect(phoneInput).toBeVisible();
    await expect(page.getByText("+972", { exact: true })).toBeVisible();
    await page.getByPlaceholder(/My Investment Account/).fill("E2E OneZero");
    const finishButton = page.getByRole("button", { name: "Finish Setup" });
    await phoneInput.fill("050123");
    await phoneInput.blur();
    await expect(phoneInput).toHaveValue("50123");
    await expect(page.getByText(/Enter an Israeli mobile number/)).toBeVisible();
    await expect(finishButton).toBeDisabled();
    await phoneInput.fill("050-1234567");
    await expect(phoneInput).toHaveValue("501234567");
    await expect(page.getByText(/Enter an Israeli mobile number/)).toHaveCount(0);
    await expect(finishButton).toBeEnabled();
    await page.getByRole("button", { name: "Back" }).click();

    // Bounce back to step 1 and try credit cards to make sure that grid wires
    // up too (different service key, different filename mappings — e.g. visa
    // cal has a space and Beyahad Bishvilha is a PNG instead of SVG).
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: /Credit Card/ }).click();
    for (const provider of ["Max", "Visa Cal", "Isracard", "Amex"]) {
      const img = page.getByRole("img", { name: provider }).last();
      await expect(img).toBeVisible();
    }

    // Insurance offers the Pension Clearing House, and no longer HaPhoenix —
    // it is deprecated for new accounts. The demo's existing HaPhoenix card
    // behind the modal keeps working and still shows its logo, so the check is
    // on the chooser's provider buttons, which no account card button names.
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: /^insurance/i }).click();
    const clearingHouse = page.getByRole("button", { name: /Pension Clearing House/ });
    await expect(clearingHouse).toBeVisible();
    await expect(
      clearingHouse.getByRole("img", { name: "Pension Clearing House" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /HaPhoenix/ })).toHaveCount(0);
  });

  // An account whose stored details are unreadable on this machine (a data
  // dir moved from another device) must still be listed, carry a badge, and
  // open straight into the edit form with an explanation. Stubbed so no
  // backend write is needed to fake a broken keyring. Runs at phone size,
  // where the edit form is taller than the screen.
  test("flags an account needing re-entry and opens its edit form from the badge", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 480 });
    await page.route("**/api/credentials/accounts", async (route) => {
      const response = await route.fetch();
      const accounts: { provider: string; needs_reentry: boolean }[] =
        await response.json();
      await route.fulfill({
        response,
        json: accounts.map((a) => ({
          ...a,
          needs_reentry: a.provider === "hapoalim",
        })),
      });
    });

    await navigateTo(page, "/data-sources");

    const badge = page.getByTestId("needs-reentry-badge");
    await expect(badge).toHaveCount(1);
    await expect(badge).toHaveText("Re-enter details");

    await badge.click();
    await expect(
      page.getByRole("heading", { name: /edit connection/i }),
    ).toBeVisible();
    await expect(page.getByRole("status")).toContainText(
      "can't be read on this machine",
    );

    // On a short phone screen the edit form is taller than the viewport and
    // the page behind is scroll-locked, so the card itself must scroll —
    // it used to overflow off-screen, leaving the save button unreachable.
    const card = page
      .getByRole("heading", { name: /edit connection/i })
      .locator("xpath=ancestor::div[contains(@class, 'rounded-3xl')][1]");
    const box = await card.boundingBox();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(480);
    const save = page.getByRole("button", { name: "Save Changes" });
    await save.scrollIntoViewIfNeeded();
    await expect(save).toBeInViewport();
  });

  test("opens the shared balance modal from the $ button and saves", async ({
    page,
  }) => {
    const provider = "onezero";
    const accountName = "E2E Balance Bank";
    const today = new Date().toISOString();

    // Seed a throwaway bank credential so a bank row (with the $ button) renders.
    const ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });
    await ctx.post(`${API_BASE}/credentials/`, {
      data: {
        service: "banks",
        provider,
        account_name: accountName,
        credentials: {
          email: "e2e-balance@example.com",
          password: "e2e-password",
          phoneNumber: "+972501234567",
        },
      },
    });
    await ctx.dispose();

    try {
      // Deterministic scrape status + balance for the seeded account.
      await page.route("**/api/scraping/last-scrapes", async (route) => {
        await route.fulfill({
          json: [
            {
              service: "banks",
              provider,
              account_name: accountName,
              last_scrape_date: today,
            },
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
      const setBtn = page
        .getByRole("button", { name: /^Set Balance$/ })
        .first();
      await expect(setBtn).toBeEnabled();
      await setBtn.click();

      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText(/net worth/i)).toBeVisible();

      const [req] = await Promise.all([
        page.waitForRequest(
          (r) =>
            r.url().includes("/api/bank-balances/") && r.method() === "POST",
        ),
        (async () => {
          await dialog.getByRole("spinbutton").fill("7777");
          await dialog.getByRole("button", { name: /^Save$/ }).click();
        })(),
      ]);
      expect(req.postDataJSON()).toEqual({
        provider,
        account_name: accountName,
        balance: 7777,
      });
      await expect(dialog).toBeHidden();
    } finally {
      const cleanup = await request.newContext({
        extraHTTPHeaders: { "X-FAD-Demo": "1" },
      });
      await cleanup.delete(
        `${API_BASE}/credentials/banks/${provider}/${encodeURIComponent(accountName)}`,
      );
      await cleanup.dispose();
    }
  });

  test("disconnecting an account forces an explicit keep-or-delete data choice", async ({
    page,
  }) => {
    // Two throwaway accounts so each branch gets a fresh card — confirming
    // consumes the account it was opened for.
    const provider = "onezero";
    const keepAccount = "E2E Disconnect Keep";
    const wipeAccount = "E2E Disconnect Wipe";

    const seed = async (accountName: string) => {
      const ctx = await request.newContext({
        extraHTTPHeaders: { "X-FAD-Demo": "1" },
      });
      await ctx.post(`${API_BASE}/credentials/`, {
        data: {
          service: "banks",
          provider,
          account_name: accountName,
          credentials: {
            email: `${accountName.replace(/\s+/g, "-")}@example.com`,
            password: "e2e-password",
            phoneNumber: "+972501234567",
          },
        },
      });
      await ctx.dispose();
    };
    await seed(keepAccount);
    await seed(wipeAccount);

    // Each card's outermost wrapper carries the "group" class; walk up from the
    // account-name heading so locators can't match a sibling card's controls.
    const cardFor = (accountName: string) =>
      page
        .getByRole("heading", { name: accountName, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

    try {
      await navigateTo(page, "/data-sources");

      // ---- Branch 1: the default must be non-destructive ----
      await cardFor(keepAccount)
        .getByRole("button", { name: "Disconnect Account" })
        .click();

      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      const keepRadio = dialog.getByRole("radio", { name: /Keep my data/ });
      const wipeRadio = dialog.getByRole("radio", {
        name: /Delete everything/,
      });
      await expect(keepRadio).toBeChecked();
      await expect(wipeRadio).not.toBeChecked();
      // The irreversible-action warning belongs to the destructive branch only.
      await expect(dialog.getByRole("alert")).toHaveCount(0);

      const [keepReq] = await Promise.all([
        page.waitForRequest(
          (r) =>
            r.url().includes("/api/credentials/banks/") &&
            r.method() === "DELETE",
        ),
        dialog.getByRole("button", { name: "Disconnect, keep data" }).click(),
      ]);
      expect(new URL(keepReq.url()).searchParams.get("delete_data")).toBe(
        "false",
      );
      await expect(dialog).toBeHidden();

      // ---- Branch 2: opting in flips the copy and the wire contract ----
      // Driven at phone height on purpose: the warning is revealed *below* the
      // scroll container's fold there, and used to stay clipped in half with
      // nothing prompting the user to scroll.
      await page.setViewportSize({ width: 375, height: 700 });
      await cardFor(wipeAccount)
        .getByRole("button", { name: "Disconnect Account" })
        .click();
      await expect(dialog).toBeVisible();
      // A fresh open must not remember the previous session's choice.
      await expect(
        dialog.getByRole("radio", { name: /Keep my data/ }),
      ).toBeChecked();

      await dialog.getByRole("radio", { name: /Delete everything/ }).check();
      const warning = dialog.getByRole("alert");
      await expect(warning).toContainText(/cannot be undone/i);
      // 0.99, not 1: `scrollIntoView({ block: "nearest" })` aligns the element
      // flush with the container edge, and subpixel rounding leaves ~0.25px
      // out. Before the fix the ratio here was ~0.65 (clipped mid-sentence).
      await expect(warning).toBeInViewport({ ratio: 0.99 });

      const [wipeReq] = await Promise.all([
        page.waitForRequest(
          (r) =>
            r.url().includes("/api/credentials/banks/") &&
            r.method() === "DELETE",
        ),
        dialog
          .getByRole("button", { name: "Disconnect and delete data" })
          .click(),
      ]);
      expect(new URL(wipeReq.url()).searchParams.get("delete_data")).toBe(
        "true",
      );
      await expect(dialog).toBeHidden();

      // Both cards are gone from the list.
      await expect(
        page.getByRole("heading", { name: keepAccount }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("heading", { name: wipeAccount }),
      ).toHaveCount(0);
    } finally {
      const cleanup = await request.newContext({
        extraHTTPHeaders: { "X-FAD-Demo": "1" },
      });
      for (const accountName of [keepAccount, wipeAccount]) {
        await cleanup.delete(
          `${API_BASE}/credentials/banks/${provider}/${encodeURIComponent(accountName)}`,
        );
      }
      await cleanup.dispose();
    }
  });

  test("credential details API never returns plaintext secrets", async ({
    page,
  }) => {
    // Regression guard: GET /api/credentials/{service}/{provider}/{account}
    // used to return the keyring password as plaintext JSON. It must now be
    // masked with the __unchanged__ sentinel (or empty when nothing stored).
    const ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });
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

  // Card anatomy at phone width. Every service must read the same way: an
  // identity row, then a metadata line, then the action buttons. Credit-card
  // and insurance cards used to let the last-scrape chip ride along beside
  // the buttons, because only bank cards had a balance filling that line.
  test("every card stacks metadata above its buttons, and the balance says what it is", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await navigateTo(page, "/data-sources");

    const cardFor = (name: string) =>
      page
        .getByRole("heading", { name, exact: true })
        .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

    // The bank balance is a bare number without a word for what it counts.
    const bankCard = cardFor("Main Account");
    await expect(bankCard).toBeVisible();
    await expect(bankCard.getByText(/^Balance$|^יתרה$/)).toBeVisible();

    // One card per service: a bank (has a balance), a credit card and an
    // insurance account (both have none, which is what used to change the
    // layout).
    for (const name of ["Main Account", "Family Card", "The Cohens"]) {
      const card = cardFor(name);
      await expect(card).toBeVisible();

      const status = card
        .getByText(/Yesterday|Never synced|אתמול|לא סונכרן/)
        .first();
      const actions = card.getByTitle(/Scrape This Source|שלוף מקור זה/);
      await expect(status).toBeVisible();
      await expect(actions).toBeVisible();

      const statusBox = await status.boundingBox();
      const actionsBox = await actions.boundingBox();
      expect(statusBox, `${name}: status box`).not.toBeNull();
      expect(actionsBox, `${name}: actions box`).not.toBeNull();
      // Separate rows: the status chip ends before the buttons begin.
      expect(
        statusBox!.y + statusBox!.height,
        `${name}: status must sit above the action buttons`,
      ).toBeLessThanOrEqual(actionsBox!.y);
    }

    // The select-source checkbox sits after the provider logo, not in a
    // column of its own ahead of it.
    const checkbox = bankCard.getByTestId("select-source");
    const logo = bankCard.getByRole("img").first();
    const checkboxBox = await checkbox.boundingBox();
    const logoBox = await logo.boundingBox();
    expect(checkboxBox!.x).toBeGreaterThan(logoBox!.x + logoBox!.width);
  });
});
