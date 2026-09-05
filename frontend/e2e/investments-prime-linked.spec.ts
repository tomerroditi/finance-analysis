import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

// Mutating spec (kept out of READ_ONLY_SPECS): creates a prime-linked
// investment through the API and verifies the edit modal shows the
// spread field instead of the flat-rate input, then cleans up.
//
// The `request` fixture is Playwright's own HTTP client — it does not run
// the app's JS, so the axios interceptor that attaches `X-FAD-Demo` from
// localStorage never runs for it. Every call below must declare the header
// itself to read/write the same database the UI (seeded via
// `enableDemoMode(page)`) is showing, instead of the real one.
const DEMO_HEADERS = { "X-FAD-Demo": "1" };

test.describe("Investments prime-linked rate type", () => {
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

  test("edit modal shows spread field for a prime-linked investment", async ({
    page,
    request,
  }) => {
    const create = await request.post(`${API_BASE}/investments/`, {
      headers: DEMO_HEADERS,
      data: {
        category: "Investments",
        tag: "E2E Prime Savings",
        type: "bonds",
        name: "E2E Prime Savings",
        interest_rate_type: "prime_linked",
        rate_spread: -1.5,
      },
    });
    expect(create.ok()).toBeTruthy();

    try {
      await navigateTo(page, "/investments");
      const card = page
        .locator("div.group", { has: page.getByText("E2E Prime Savings") })
        .first();
      await expect(card).toBeVisible({ timeout: 15_000 });

      await card.getByTitle("Edit").click();

      // Prime-linked selected → spread input (with the stored -1.5) and
      // no flat interest-rate input.
      const modal = page.getByRole("dialog");
      await expect(modal.getByText("Spread vs Prime (%)")).toBeVisible();
      await expect(modal.locator('input[type="number"]')).toHaveValue("-1.5");
      await expect(modal.getByText("Interest Rate (%)")).toHaveCount(0);
    } finally {
      const list = await request.get(`${API_BASE}/investments/`, {
        headers: DEMO_HEADERS,
      });
      const record = (await list.json()).find(
        (inv: { name: string }) => inv.name === "E2E Prime Savings",
      );
      if (record) {
        await request.delete(`${API_BASE}/investments/${record.id}`, {
          headers: DEMO_HEADERS,
        });
      }
    }
  });
});
