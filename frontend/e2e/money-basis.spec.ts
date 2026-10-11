import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Settings → "How money is counted" switches the Income & Expenses card and
 * the yearly savings figure between net cost and cash flow together. Each
 * card says which basis it is on behind an info icon, and the pending-refunds
 * chip — meaningless when money is counted as it moved — is only offered on
 * net cost. The setting lives in localStorage, so the spec writes nothing to
 * the backend.
 */

/** Open the dashboard with only the two cards that read the basis. */
async function openDashboard(page: Page) {
  await page.goto("about:blank");
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem("onboardingDismissedAt", String(Date.now()));
    localStorage.setItem(
      "fa.dashboard.layout",
      JSON.stringify({ v: 5, order: ["goals", "income_expenses"], hidden: [] }),
    );
  });
  await page.goto("/");
}

test.describe("How money is counted", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("the Settings toggle moves both cards, and each card explains it", async ({ page }) => {
    await openDashboard(page);
    const yearly = page.getByTestId("yearly-savings");
    const card = page.locator('[data-card-id="income_expenses"]');
    await expect(yearly).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();
    await expect(card.getByRole("heading", { name: "Income & Expenses" })).toBeVisible({
      timeout: 45_000,
    });

    // --- net cost by default ---
    const yearlyInfo = yearly.getByTestId("info-tooltip-panel");
    const cardInfo = card.getByTestId("income-expenses-basis-info").getByTestId("info-tooltip-panel");
    await expect(yearlyInfo).toHaveText(/^Net cost: what things really cost\..*Settings/);
    await expect(cardInfo).toHaveText(/^Net cost/);
    const pendingChip = card.getByRole("button", { name: /^Pending Refunds (In|Ex)cluded$/ });
    await expect(pendingChip).toBeVisible();

    // --- switch to cash flow in Settings ---
    const cashFlowSeries = page.waitForRequest(
      (req) => req.url().includes("expenses-by-category-over-time") && req.url().includes("basis=cash_flow"),
    );
    const cashFlowYearly = page.waitForRequest(
      (req) => req.url().includes("/savings-goals/yearly") && req.url().includes("basis=cash_flow"),
    );
    const settings = page.locator("button:has(svg.lucide-settings)").filter({ visible: true }).first();
    await settings.click();
    const cashFlow = page.getByRole("radio", { name: "Cash flow" });
    await expect(page.getByRole("radio", { name: "Net cost" })).toHaveAttribute("aria-checked", "true");
    await cashFlow.click();
    await expect(cashFlow).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("money-basis-help")).toHaveText(/^Cash flow: money as it moved\./);
    await expect(page.getByTestId("money-basis-help")).not.toContainText("Settings");
    await page.keyboard.press("Escape");

    // --- both cards re-read on the new basis and say so ---
    await cashFlowSeries;
    await cashFlowYearly;
    await expect(cardInfo).toHaveText(/^Cash flow: money as it moved\..*Settings/);
    await expect(yearlyInfo).toHaveText(/^Cash flow/);
    await expect(pendingChip).toHaveCount(0);
    await expect(card.getByRole("button", { name: /^Projects (In|Ex)cluded$/ })).toBeVisible();

    // --- the choice is remembered ---
    await page.reload();
    await settings.click();
    await expect(page.getByRole("radio", { name: "Cash flow" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("radio", { name: "Net cost" }).click();
    await page.keyboard.press("Escape");
  });
});
