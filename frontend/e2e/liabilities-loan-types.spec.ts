import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

// Mutating spec (kept out of READ_ONLY_SPECS): creates a prime-linked loan
// through the API and verifies the Liabilities page renders the new
// loan-type metadata, then cleans up.
//
// The `request` fixture is Playwright's own HTTP client — it does not run
// the app's JS, so the axios interceptor that attaches `X-FAD-Demo` from
// localStorage never runs for it. Every call below must declare the header
// itself to read/write the same database the UI (seeded via
// `enableDemoMode(page)`) is showing, instead of the real one.
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

test.describe("Liabilities loan types", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("renders a prime-linked loan with spread and effective rate", async ({
    page,
    request,
  }) => {
    const create = await request.post(`${API_BASE}/liabilities/`, {
      headers: DEMO_HEADERS,
      data: {
        name: "E2E Prime Loan",
        tag: "E2E Prime Loan",
        principal_amount: 100000,
        term_months: 120,
        start_date: "2024-01-01",
        loan_type: "prime_linked",
        rate_spread: -0.5,
        lender: "E2E Bank",
      },
    });
    expect(create.ok()).toBeTruthy();

    try {
      await navigateTo(page, "/liabilities");
      const card = page
        .locator("div.group", { has: page.getByText("E2E Prime Loan") })
        .first();
      await expect(card).toBeVisible({ timeout: 15_000 });

      // Loan-type label + spread expression + effective rate line
      await expect(card.getByText("Prime-Linked")).toBeVisible();
      await expect(card.getByText(/Prime-0\.5%/)).toBeVisible();
      await expect(card.getByText(/% interest/)).toBeVisible();
    } finally {
      const list = await request.get(`${API_BASE}/liabilities/`, {
        headers: DEMO_HEADERS,
      });
      const record = (await list.json()).find(
        (l: { name: string }) => l.name === "E2E Prime Loan",
      );
      if (record) {
        await request.delete(`${API_BASE}/liabilities/${record.id}`, {
          headers: DEMO_HEADERS,
        });
      }
    }
  });
});
