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

  // One dashboard load covers every settings-popup scenario that starts from
  // the clean default layout: the pinned KPI header, hiding a card, beta
  // badges, enabling a beta card, and closing the popup with the X button.
  // Hiding "Spending calendar" and enabling "forecast" touch independent
  // cards, so both post-conditions can be asserted on the same dashboard.
  test("settings popup: hide card, beta badges, enable beta, X-close (KPI header stays pinned)", async ({
    page,
  }) => {
    await page.goto("/");
    // Net Worth KPI lives in the pinned header and is never in the card set.
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({ timeout: 45_000 });
    // Recent transactions is a non-beta card, visible by default.
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    // Beta dashboard sections are not rendered on a fresh layout. "Safe to
    // spend" is unique to the forecast card (avoids matching the heatmap's
    // "This month" total label).
    await expect(page.getByText(/Safe to spend/i)).toHaveCount(0);

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toBeVisible();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // The beta forecast card sits under Hidden cards with a Beta badge.
    const betaRow = page.getByText("This Month (forecast)", { exact: true }).locator("xpath=..");
    await expect(betaRow).toBeVisible();
    await expect(betaRow.getByText(/^Beta$/i)).toBeVisible();

    // Non-beta visible card carries no Beta badge.
    const visibleRow = page.getByText("Recent transactions", { exact: true }).locator("xpath=..");
    await expect(visibleRow.getByText(/^Beta$/i)).toHaveCount(0);

    // Hide the "Spending calendar" card (non-beta, visible by default).
    const label = page.getByText("Spending calendar", { exact: true });
    await expect(label).toBeVisible();
    await label.locator("xpath=..").getByRole("button", { name: /Hide card/i }).click();
    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();

    // Opt into the beta forecast card.
    await betaRow.getByRole("button", { name: /Show card/i }).click();

    // The X button closes the settings popup.
    await page.getByRole("button", { name: /^Close$/ }).click();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toHaveCount(0);

    // The hidden card is gone from the dashboard.
    await expect(page.getByText(/Spending Calendar/i)).toHaveCount(0);

    // The newly enabled card is appended below the fold, where cards defer
    // their mount until scrolled near. Scroll to it, then its content renders.
    await page.locator('[data-card-id="forecast"]').scrollIntoViewIfNeeded();
    // "Safe to spend" is unique to the forecast card.
    await expect(page.getByText(/Safe to spend/i).first()).toBeVisible();
  });

  test("hidden card persists across reload and can be restored", async ({ page }) => {
    // Current (v:3) layout so it isn't migrated; heatmap hidden explicitly.
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "fa.dashboard.layout",
        JSON.stringify({
          v: 3,
          order: ["budget", "recent", "income_expenses", "net_worth"],
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

    // A restored card is appended to the end of the order — below the fold,
    // where cards defer their mount until scrolled near. Scroll to it, then
    // its content renders.
    await page.locator('[data-card-id="heatmap"]').scrollIntoViewIfNeeded();
    await expect(page.getByText(/Spending Calendar/i).first()).toBeVisible();
  });

  test("draggable rows have touch-action none; dragging reorders and persists", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i).first()).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Default visible order starts with "Budget spending"; drag it down.
    const firstRow = page.getByText("Budget spending", { exact: true }).locator("xpath=..");
    await expect(firstRow).toBeVisible();

    // Regression guard before dragging: @dnd-kit spreads role="button" onto
    // each row; the global `[role="button"] { touch-action: manipulation }`
    // rule would otherwise win the cascade and break dragging on
    // touch/trackpad. The inline `touch-action: none` must override it —
    // a synthetic-mouse drag alone cannot catch that bug.
    const touchAction = await firstRow.evaluate((el) => getComputedStyle(el).touchAction);
    expect(touchAction).toBe("none");

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
});
