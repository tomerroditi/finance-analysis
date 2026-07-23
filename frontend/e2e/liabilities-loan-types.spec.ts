import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo } from "./helpers";

// Mutating spec (kept out of READ_ONLY_SPECS): creates a prime-linked loan
// through the API and verifies the Liabilities page renders the new
// loan-type metadata, then cleans up.
test.describe("Liabilities loan types", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("renders a prime-linked loan with spread and effective rate", async ({
    page,
    request,
  }) => {
    const create = await request.post(`${API_BASE}/liabilities/`, {
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
      const list = await request.get(`${API_BASE}/liabilities/`);
      const record = (await list.json()).find(
        (l: { name: string }) => l.name === "E2E Prime Loan",
      );
      if (record) {
        await request.delete(`${API_BASE}/liabilities/${record.id}`);
      }
    }
  });
});
