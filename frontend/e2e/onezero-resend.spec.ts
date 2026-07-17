import { test, expect, request } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, API_BASE } from "./helpers";

const PROCESS_ID = 4242;

// A throwaway OneZero account, seeded into the demo DB so the 2FA resend UI
// (OneZero-only "Re-authenticate (force 2FA)" button, then the inline 2FA
// block) has an account to render against. Mirrors onezero-force-2fa.spec.ts.
const ONEZERO_ACCOUNT = "E2E OneZero Resend";

/**
 * Seed (or remove) a OneZero bank credential through the credentials API,
 * the same path the Data Sources "add account" form uses. Demo mode must
 * be enabled first so the write lands in the isolated demo DB.
 */
async function setOneZeroCredential(create: boolean) {
  const ctx = await request.newContext();
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
    await enableDemoMode();
    await setOneZeroCredential(true);
  });

  test.afterAll(async () => {
    await setOneZeroCredential(false);
    await disableDemoMode();
  });

  test("Resend calls resend-2fa (not abort), keeps the process id, and starts a cooldown", async ({
    page,
  }) => {
    // Demo Mode uses non-TFA dummy scrapers (DummyRegularScraper), so a
    // real 2FA prompt never fires under demo mode. Stub the whole
    // /api/scraping/* surface so we can drive the UI into
    // "waiting_for_2fa" deterministically and never touch a real scraper
    // or a real 2FA/otp channel. Also guards against the same leak
    // documented in onezero-force-2fa.spec.ts: Demo Mode is a
    // process-global flag, so a live scrape here could leak fake
    // transactions into the user's real data.db.
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

    const reauth = card.getByRole("button", { name: /Re-authenticate|אימות מחדש/ });
    await expect(reauth).toBeVisible();
    await reauth.click();

    // Wait for the forced-2FA start to land, then for the status poll
    // (stubbed to "waiting_for_2fa") to flip the card into the inline 2FA
    // section where Verify/Resend live.
    await expect.poll(() => startBody).toMatchObject({
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
