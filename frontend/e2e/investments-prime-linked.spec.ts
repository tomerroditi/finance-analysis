import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo } from "./helpers";

// Mutating spec (kept out of READ_ONLY_SPECS): creates a prime-linked
// investment through the API and verifies the edit modal shows the
// spread field instead of the flat-rate input, then cleans up.
test.describe("Investments prime-linked rate type", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("edit modal shows spread field for a prime-linked investment", async ({
    page,
    request,
  }) => {
    const create = await request.post(`${API_BASE}/investments/`, {
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
      const list = await request.get(`${API_BASE}/investments/`);
      const record = (await list.json()).find(
        (inv: { name: string }) => inv.name === "E2E Prime Savings",
      );
      if (record) {
        await request.delete(`${API_BASE}/investments/${record.id}`);
      }
    }
  });
});
