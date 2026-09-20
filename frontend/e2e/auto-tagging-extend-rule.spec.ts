import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * The rule quick action must GROW the rule that already owns a transaction's
 * category/tag instead of offering to create a second one for the same pair.
 *
 * Only one rule per (category, tag) is allowed — the editor filters a claimed
 * tag out of its dropdown, so the "Create Rule" it used to open could not even
 * be saved: it came up with the tag select stuck on its placeholder.
 *
 * The action is shared — the dashboard's recent-transactions card, the
 * transactions table's bulk actions bar and the single-transaction editor all
 * render the same `RuleQuickAction` — so this covers the card and the table.
 *
 * Demo fixtures used here:
 *  - the "Rides" rule (Transportation / Taxi) matches `UBER` / `GETT`, while
 *    "RIDE REFUND - REMAINING" carries that category/tag without matching it;
 *  - the "Food Delivery" rule (Food / Delivery) is a bare
 *    `description starts_with WOLT` — not an OR — while "TENBIS" carries that
 *    category/tag without matching it.
 */
const RIDE_REFUND = "RIDE REFUND - REMAINING";

test.describe("Auto-tagging quick action — extend an existing rule", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("adds the description to the owning rule instead of creating a second one", async ({
    page,
  }) => {
    const before = await (await page.request.get(`${API_BASE}/tagging-rules/rules`, {
      headers: { "X-FAD-Demo": "1" },
    })).json();
    const owner = before.find(
      (rule: { category: string; tag: string }) =>
        rule.category === "Transportation" && rule.tag === "Taxi",
    );
    expect(owner, "demo data must ship a Transportation / Taxi rule").toBeTruthy();

    await navigateTo(page, "/");

    const card = page.locator('[data-card-id="recent"]');
    const row = card
      .getByTestId("recent-tx-row")
      .filter({ hasText: RIDE_REFUND })
      .first();
    await expect(row).toBeVisible({ timeout: 45_000 });
    await row.getByRole("button", { name: "More actions" }).click();

    // The action reads "Add to Rule", not "Add Rule" — the pair is claimed.
    const ruleButton = card.getByRole("button", { name: "Add to Rule" });
    await expect(ruleButton).toBeVisible();
    await expect(ruleButton).toHaveAttribute("title", /Rides/);
    await ruleButton.click();

    // The editor opens on the existing rule, with its category/tag filled in
    // (a claimed tag used to be filtered out of the dropdown and render blank)
    // and the transaction's description appended as a new OR branch.
    const modal = page.locator(".modal-overlay").last();
    await expect(modal.getByRole("heading", { name: "Edit Rule" })).toBeVisible();
    // The modal renders its form twice (a mobile tab and a desktop pane), so
    // scope these to the copy this viewport actually shows.
    const form = modal.getByText("Rule Details").filter({ visible: true })
      .locator("xpath=ancestor::div[contains(@class,'space-y-6')][1]");
    await expect(form.getByRole("button", { name: "Transportation" })).toBeVisible();
    await expect(form.getByRole("button", { name: "Taxi" })).toBeVisible();
    await expect(form.getByRole("button", { name: "Select..." })).toHaveCount(0);

    const values = modal.locator('input[placeholder="Value"]:visible');
    await expect(values).toHaveCount(3);
    expect(
      await values.evaluateAll((els) =>
        els.map((el) => (el as HTMLInputElement).value),
      ),
    ).toEqual(["UBER", "GETT", RIDE_REFUND]);

    await modal.getByRole("button", { name: "Save Rule" }).click();
    await expect(modal).toHaveCount(0, { timeout: 20_000 });

    // No new rule: the owning one grew a branch.
    const after = await (await page.request.get(`${API_BASE}/tagging-rules/rules`, {
      headers: { "X-FAD-Demo": "1" },
    })).json();
    expect(after).toHaveLength(before.length);
    const grown = after.find((rule: { id: number }) => rule.id === owner.id);
    expect(
      JSON.stringify(grown.conditions),
    ).toContain(RIDE_REFUND);
  });

  // The bulk bar opens with empty category/tag dropdowns, so nothing is
  // staged: the action has to read the pair off the selection itself. This
  // also drives the non-OR root — the Food / Delivery rule is a bare
  // `starts_with` condition, which must be WRAPPED in an OR rather than
  // appended into, or the rule would stop matching plain WOLT charges.
  test("reads the pair off the selection in the transactions table's bulk bar", async ({
    page,
  }) => {
    await navigateTo(page, "/transactions");
    await expect(page.locator("table tbody tr").first()).toBeVisible({
      timeout: 45_000,
    });

    const search = page.getByRole("textbox", { name: /search/i }).first();
    await search.fill("TENBIS");
    const row = page.locator("table tbody tr").filter({ hasText: "TENBIS" }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.locator('input[type="checkbox"]').check();

    const bulkBar = page
      .locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8")
      .last();
    const ruleButton = bulkBar.getByRole("button", { name: "Add to Rule" });
    await expect(ruleButton).toBeVisible({ timeout: 10_000 });
    await ruleButton.click();

    const modal = page.locator(".modal-overlay").last();
    await expect(modal.getByRole("heading", { name: "Edit Rule" })).toBeVisible();

    const values = modal.locator('input[placeholder="Value"]:visible');
    await expect(values).toHaveCount(2);
    expect(
      await values.evaluateAll((els) =>
        els.map((el) => (el as HTMLInputElement).value),
      ),
    ).toEqual(["WOLT", "TENBIS"]);

    // The original `starts_with WOLT` survives as a branch of the new OR, so
    // the preview still carries the plain WOLT charges it always matched.
    const operators = modal.locator("select:visible, button:visible");
    await expect(operators.filter({ hasText: "Starts with" }).first()).toBeVisible();
    await expect(
      modal.locator("tbody tr").filter({ hasText: "WOLT" }).first(),
    ).toBeVisible();
  });
});
