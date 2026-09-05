import { test, expect, request } from "@playwright/test";
import { enableDemoMode, navigateTo, API_BASE } from "./helpers";

const PROCESS_ID = 4242;

// A throwaway OneZero account, seeded into the demo DB so the 2FA resend UI
// (OneZero-only "Re-authenticate (force 2FA)" button, then the inline 2FA
// block) has an account to render against. This spec also owns the forced-2FA
// wire-contract coverage (the start request must carry force_2fa: true) that
// used to live in a separate onezero-force-2fa.spec.ts.
const ONEZERO_ACCOUNT = "E2E OneZero Resend";

// Mirrors INITIAL_2FA_COOLDOWN_SECONDS in src/hooks/useScraping.ts. Not
// imported: e2e specs run outside the Vite graph and must not pull app modules.
const INITIAL_2FA_COOLDOWN_SECONDS = 30;

/**
 * Seed (or remove) a OneZero bank credential through the credentials API,
 * the same path the Data Sources "add account" form uses.
 *
 * This bypasses the browser (Node-side `request` fixture), so it must
 * declare the `X-FAD-Demo` header itself — Demo Mode is per-client now, and
 * a header-less request would land this throwaway account in the real
 * database instead of the demo one.
 */
async function setOneZeroCredential(create: boolean) {
  const ctx = await request.newContext({
    extraHTTPHeaders: { "X-FAD-Demo": "1" },
  });
  try {
    if (create) {
      await ctx.post(`${API_BASE}/credentials/`, {
        data: {
          service: "banks",
          provider: "onezero",
          account_name: ONEZERO_ACCOUNT,
          credentials: {
            email: "e2e-resend@example.com",
            password: "e2e-password",
            phoneNumber: "+15551234567",
          },
        },
      });
    } else {
      await ctx.delete(
        `${API_BASE}/credentials/banks/onezero/${encodeURIComponent(ONEZERO_ACCOUNT)}`,
      );
    }
  } finally {
    await ctx.dispose();
  }
}

test.describe("OneZero resend-in-place 2FA", () => {
  test.beforeAll(async () => {
    // Build the demo DB before writing the throwaway credential into it —
    // this doesn't go through a `page`, so it carries the demo header
    // itself rather than relying on `enableDemoMode`'s localStorage seeding
    // (which needs a browser context).
    const ctx = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });
    try {
      await ctx.post(`${API_BASE}/testing/demo/reset`);
    } finally {
      await ctx.dispose();
    }
    await setOneZeroCredential(true);
  });

  test.afterAll(async () => {
    await setOneZeroCredential(false);
  });

  // Demo Mode itself is per-page (localStorage), so it's seeded per-test
  // here rather than alongside the beforeAll credential setup above.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("Resend calls resend-2fa (not abort), keeps the process id, and starts a cooldown", async ({
    page,
  }) => {
    // Demo Mode uses non-TFA dummy scrapers (DummyRegularScraper), so a
    // real 2FA prompt never fires under demo mode. Stub the whole
    // /api/scraping/* surface so we can drive the UI into
    // "waiting_for_2fa" deterministically and never touch a real scraper
    // or a real 2FA/otp channel. This also guards a real data-leak: Demo
    // Mode used to be a process-global flag (backend/config.py), so a live
    // scrape here plus afterAll's cleanup racing it back to production once
    // leaked 6 fake transactions into the user's real data.db. Demo Mode is
    // per-client now (no shared flag left to race), but a live scrape would
    // still hit a real provider's site from a test — do NOT "simplify" this
    // to waitForRequest + a live click.
    let startBody: unknown;
    let abortCalled = false;
    let resendBody: unknown;
    let resendCallCount = 0;
    // Every scraping_process_id the frontend has polled /status for, in
    // order. Used below to prove the poller never switched to tracking a
    // different process across the resend — the strongest available
    // signal that "the process id is unchanged", since the UI itself
    // doesn't render the numeric id anywhere.
    const polledProcessIds: string[] = [];

    // Install a controllable clock so the cooldown windows can be skipped
    // instead of slept through. `resume()` right after install puts time back
    // on a real tick, so polling, React and TanStack Query all behave normally.
    await page.clock.install();
    await page.clock.resume();

    await page.route("**/api/scraping/start", async (route) => {
      startBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PROCESS_ID),
      });
    });

    await page.route("**/api/scraping/status*", async (route) => {
      const url = new URL(route.request().url());
      const polledId = url.searchParams.get("scraping_process_id");
      if (polledId) polledProcessIds.push(polledId);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "waiting_for_2fa" }),
      });
    });

    await page.route("**/api/scraping/abort", async (route) => {
      abortCalled = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "aborted" }),
      });
    });

    await page.route("**/api/scraping/resend-2fa", async (route) => {
      resendCallCount += 1;
      resendBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "resent", process_id: PROCESS_ID }),
      });
    });

    await navigateTo(page, "/data-sources");

    // The seeded OneZero account card must be present.
    await expect(
      page.getByText(ONEZERO_ACCOUNT, { exact: false }),
    ).toBeVisible();

    // Find the account card so we can scope locators to it — the page can
    // render multiple accounts (the demo dataset ships several), and
    // role-based locators like "Resend" could otherwise match another
    // card's button. Each card's outermost wrapper carries the "group"
    // class (see DataSources.tsx); walk up from the account-name heading
    // to that wrapper via XPath ancestor traversal — `.locator("div")
    // .filter({ hasText }).last()` looked appealing but actually resolves
    // to the *innermost* nested div (DOM order puts deeper nodes later),
    // which excludes the sibling 2FA section entirely.
    const card = page
      .getByRole("heading", { name: ONEZERO_ACCOUNT, exact: true })
      .locator("xpath=ancestor::div[contains(@class, 'group')][1]");

    const reauth = card.getByRole("button", {
      name: /Re-authenticate|אימות מחדש/,
    });
    await expect(reauth).toBeVisible();
    await reauth.click();

    // Wait for the forced-2FA start to land, then for the status poll
    // (stubbed to "waiting_for_2fa") to flip the card into the inline 2FA
    // section where Verify/Resend live.
    await expect
      .poll(() => startBody)
      .toMatchObject({
        provider: "onezero",
        force_2fa: true,
      });

    // Locate Resend structurally (last button in the 2FA action row: input,
    // then Verify, then Resend) rather than by its current label text.
    // getByRole's `name` filter is a *live* query re-evaluated on every
    // check — once the click below changes the label to the "Resend in
    // {{seconds}}s" countdown, a name-based locator for "Resend" stops
    // matching anything, and `.toBeDisabled()` fails with "element(s) not
    // found" instead of asserting the disabled state.
    const codeInput = card.getByPlaceholder(/Code|קוד/);
    const actionRow = codeInput.locator("xpath=..");
    const verifyButton = card.getByRole("button", {
      name: /^Verify$|^אמת$/,
    });
    const resendButton = actionRow.locator("button").last();

    await expect(verifyButton).toBeVisible({ timeout: 10_000 });
    await expect(resendButton).toBeVisible();

    // Reaching waiting_for_2fa means the provider just sent a code, so Resend
    // starts inside an initial cooldown (INITIAL_2FA_COOLDOWN_SECONDS) rather
    // than live. Before that existed, "Re-authenticate" followed immediately by
    // "Resend" fired a second OTP seconds after the first.
    await expect(resendButton).toBeDisabled();
    await expect(resendButton).toHaveText(/\d/);

    // Jump past the initial window instead of sleeping through it — the clock
    // is installed with `time` at the current instant and immediately resumed,
    // so the app runs normally and only this fast-forward skips ahead.
    await page.clock.fastForward(INITIAL_2FA_COOLDOWN_SECONDS * 1000);

    await expect(resendButton).toBeEnabled();
    const resendLabelBefore = await resendButton.innerText();
    expect(resendLabelBefore).toMatch(/^Resend$|^שלח שוב$/);

    await resendButton.click();

    // The resend must hit /api/scraping/resend-2fa with the account
    // identity, and must NOT fall back to the old abort + restart flow.
    await expect.poll(() => resendCallCount).toBe(1);
    expect(resendBody).toMatchObject({
      service: "banks",
      provider: "onezero",
      account: ONEZERO_ACCOUNT,
    });
    expect(abortCalled).toBe(false);

    // The process id must be unchanged after a "resent" response — the
    // 2FA block should still be showing (same card, still waiting for a
    // code), not have disappeared or reset.
    await expect(codeInput).toBeVisible();

    // Wait for at least one more status poll to land after the resend so
    // we can compare pre- and post-resend polled ids.
    const polledCountAtResend = polledProcessIds.length;
    await expect
      .poll(() => polledProcessIds.length)
      .toBeGreaterThan(polledCountAtResend);

    // Every poll — before AND after the resend — must target the exact
    // same scraping_process_id. If resendTfa had swapped in a different
    // id (or dropped the old one without a "restarted" response), this
    // list would contain more than one distinct value.
    const distinctPolledIds = new Set(polledProcessIds);
    expect(distinctPolledIds.size).toBe(1);
    expect(distinctPolledIds.has(String(PROCESS_ID))).toBe(true);

    // The Resend button must now show a cooldown countdown and be
    // disabled — the countdown text embeds the remaining seconds
    // (dataSources.resendIn), distinct from the plain "Resend" label.
    await expect(resendButton).toBeDisabled();
    await expect(resendButton).toHaveText(/\d/);
    const resendLabelAfter = await resendButton.innerText();
    expect(resendLabelAfter).not.toMatch(/^Resend$|^שלח שוב$/);
  });
});
