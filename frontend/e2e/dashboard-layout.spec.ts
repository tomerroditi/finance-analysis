import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Customizable dashboard layout: the Settings → Dashboard tab lets users
 * reorder and hide cards; the KPI header stays pinned. Beta cards (forecast,
 * insights, recurring, goals) ship hidden by default. Persistence is
 * localStorage-backed.
 */
test.describe("Dashboard layout customization", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    // Start each test from a clean (default) layout.
    await page.addInitScript(() => window.localStorage.removeItem("fa.dashboard.layout"));
  });

  test("hiding a card removes it from the dashboard", async ({ page }) => {
    await page.goto("/");
    // Recent transactions is a non-beta card, visible by default.
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Hide the "Spending calendar" card (non-beta, visible by default).
    const label = page.getByText("Spending calendar", { exact: true });
    await expect(label).toBeVisible();
    await label.locator("xpath=..").getByRole("button", { name: /Hide card/i }).click();

    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByText(/Spending Calendar/i)).toHaveCount(0);
  });

  test("hidden card persists across reload and can be restored", async ({ page }) => {
    // Versioned (v:2) layout so it isn't migrated; heatmap hidden explicitly.
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          v: 2,
          order: ["budget", "recent", "charts"],
          hidden: ["heatmap"],
        }),
      );
    });
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Spending Calendar/i)).toHaveCount(0);

    // Restore it from settings.
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();
    const hiddenRow = page.getByText("Spending calendar", { exact: true }).locator("xpath=..");
    await hiddenRow.getByRole("button", { name: /Show card/i }).click();
    await page.keyboard.press("Escape");

    await expect(page.getByText(/Spending Calendar/i).first()).toBeVisible();
  });

  test("KPI header stays pinned regardless of layout", async ({ page }) => {
    await page.goto("/");
    // Net Worth KPI lives in the pinned header and is never in the card set.
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({ timeout: 45_000 });
  });

  test("beta cards are hidden by default and badged", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    // Beta dashboard sections are not rendered on a fresh layout. "Safe to
    // spend" is unique to the forecast card (avoids matching the heatmap's
    // "This month" total label).
    await expect(page.getByText(/Safe to spend/i)).toHaveCount(0);

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // The beta forecast card sits under Hidden cards with a Beta badge.
    const betaRow = page.getByText("This Month (forecast)", { exact: true }).locator("xpath=..");
    await expect(betaRow).toBeVisible();
    await expect(betaRow.getByText(/^Beta$/i)).toBeVisible();

    // Non-beta visible card carries no Beta badge.
    const visibleRow = page.getByText("Recent transactions", { exact: true }).locator("xpath=..");
    await expect(visibleRow.getByText(/^Beta$/i)).toHaveCount(0);
  });

  test("enabling a beta card shows it on the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Opt into the beta forecast card.
    const betaRow = page.getByText("This Month (forecast)", { exact: true }).locator("xpath=..");
    await betaRow.getByRole("button", { name: /Show card/i }).click();
    await page.keyboard.press("Escape");

    // "Safe to spend" is unique to the forecast card.
    await expect(page.getByText(/Safe to spend/i).first()).toBeVisible();
  });

  test("dragging a card reorders and persists", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Default visible order starts with "Budget spending"; drag it down.
    const firstRow = page.getByText("Budget spending", { exact: true }).locator("xpath=..");
    await expect(firstRow).toBeVisible();
    const box = await firstRow.boundingBox();
    if (!box) throw new Error("no drag handle box");

    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 20, box.y + 80, { steps: 8 });
    await page.mouse.move(box.x + 20, box.y + 140, { steps: 8 });
    await page.mouse.up();

    const order = await page.evaluate(() => {
      const raw = window.localStorage.getItem("fa.dashboard.layout");
      return raw ? (JSON.parse(raw).order as string[]) : [];
    });
    expect(order[0]).not.toBe("budget");
    expect(order).toContain("budget");
  });

  test("draggable rows have touch-action: none (regression guard)", async ({ page }) => {
    // @dnd-kit spreads role="button" onto each row; the global
    // `[role="button"] { touch-action: manipulation }` rule would otherwise
    // win the cascade and break dragging on touch/trackpad. The inline
    // `touch-action: none` must override it. This guards that exact bug, which
    // a synthetic-mouse drag test cannot catch.
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    const touchAction = await page
      .getByText("Budget spending", { exact: true })
      .locator("xpath=..")
      .evaluate((el) => getComputedStyle(el).touchAction);
    expect(touchAction).toBe("none");
  });

  test("X button closes the settings popup", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });
    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toBeVisible();
    await page.getByRole("button", { name: /^Close$/ }).click();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toHaveCount(0);
  });
});
