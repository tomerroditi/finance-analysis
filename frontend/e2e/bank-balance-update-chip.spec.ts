import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

test.describe("Dashboard bank-balance update chip", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
  });
  test.afterAll(async () => {
    await disableDemoMode();
  });

  test.beforeEach(async ({ page }) => {
    const today = new Date().toISOString();
    await page.route("**/api/bank-balances/", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: [
            { id: 1, provider: "hapoalim", account_name: "Fresh Checking", balance: 1000, prior_wealth_amount: 0, last_manual_update: null, last_scrape_update: today },
            { id: 2, provider: "leumi", account_name: "Stale Savings", balance: 2000, prior_wealth_amount: 0, last_manual_update: null, last_scrape_update: null },
          ],
        });
      } else {
        await route.fulfill({
          json: { id: 1, provider: "hapoalim", account_name: "Fresh Checking", balance: 4242, prior_wealth_amount: 0, last_manual_update: today, last_scrape_update: today },
        });
      }
    });
    await page.route("**/api/scraping/last-scrapes", async (route) => {
      await route.fulfill({
        json: [
          { service: "banks", provider: "hapoalim", account_name: "Fresh Checking", last_scrape_date: today },
          { service: "banks", provider: "leumi", account_name: "Stale Savings", last_scrape_date: "2020-01-01T00:00:00" },
        ],
      });
    });
    await page.goto("/");
    await page.evaluate(() =>
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now())),
    );
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("shows an update chip per account; disabled when not scraped today", async ({ page }) => {
    await page.getByText("Bank Balance", { exact: true }).click(); // expand KPI header
    await expect(page.getByText("Fresh Checking")).toBeVisible();
    await expect(page.getByText("Stale Savings")).toBeVisible();
    const staleChip = page.getByRole("button", {
      name: /scrape first to set balance/i,
    });
    await expect(staleChip).toBeVisible();
    await expect(staleChip).toBeDisabled();
  });

  test("opens the modal, saves a balance, and keeps the card expanded", async ({ page }) => {
    await page.getByText("Bank Balance", { exact: true }).click();
    await expect(page.getByText("Fresh Checking")).toBeVisible();

    await page.getByRole("button", { name: /^Set Balance$/ }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/net worth/i)).toBeVisible();
    // stopPropagation worked — the breakdown is still expanded behind the modal
    // (the account name now appears twice: once in the breakdown row, once in
    // the modal body, so scope to .first() to avoid a strict-mode violation).
    await expect(page.getByText("Fresh Checking").first()).toBeVisible();

    const [req] = await Promise.all([
      page.waitForRequest(
        (r) => r.url().includes("/api/bank-balances/") && r.method() === "POST",
      ),
      (async () => {
        await dialog.getByRole("spinbutton").fill("4242");
        await dialog.getByRole("button", { name: /^Save$/ }).click();
      })(),
    ]);
    expect(req.postDataJSON()).toEqual({
      provider: "hapoalim",
      account_name: "Fresh Checking",
      balance: 4242,
    });
    await expect(dialog).toBeHidden();
  });
});
