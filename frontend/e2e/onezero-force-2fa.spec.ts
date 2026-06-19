import { test, expect, request } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

const API_BASE = "http://localhost:8000/api";

// A throwaway OneZero account, seeded into the demo DB so the
// OneZero-only "Re-authenticate (force 2FA)" button has an account to
// render against. The demo DB ships with an empty credentials table, so
// without this seed the Data Sources page shows no accounts at all.
const ONEZERO_ACCOUNT = "E2E OneZero";

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
            email: "e2e@example.com",
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

test.describe("OneZero force-2FA (Re-authenticate)", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
    await setOneZeroCredential(true);
  });

  test.afterAll(async () => {
    await setOneZeroCredential(false);
    await disableDemoMode();
  });

  test("Re-authenticate button is OneZero-only and starts a forced 2FA scrape", async ({
    page,
  }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // The seeded OneZero account card must be present.
    await expect(page.getByText(ONEZERO_ACCOUNT, { exact: false })).toBeVisible();

    // The re-authenticate button is rendered only for OneZero accounts
    // (gated by acc.provider === "onezero" in DataSources.tsx). Its
    // aria-label is the dataSources.forceTfa translation.
    const reauth = page
      .getByRole("button", { name: /Re-authenticate|אימות מחדש/ })
      .first();
    await expect(reauth).toBeVisible();

    // Clicking it must POST /api/scraping/start with the force_2fa flag set
    // for the OneZero provider. Intercept the request and assert the JSON
    // body — this is the wire contract the button exists to satisfy.
    const startReq = page.waitForRequest(
      (req) =>
        req.url().includes("/api/scraping/start") && req.method() === "POST",
    );
    await reauth.click();
    const req = await startReq;
    expect(req.postDataJSON()).toMatchObject({
      provider: "onezero",
      force_2fa: true,
    });
  });
});
