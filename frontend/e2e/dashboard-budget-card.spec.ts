import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * The dashboard's budget card, driven the way a phone user drives it.
 *
 * Four behaviours that only show up in a real browser: the tab strip has to
 * scroll on its own (the card sits in an `overflow-y-auto` grid cell, which
 * makes any horizontal overflow drag the whole card — figures and all —
 * sideways), the one-line envelope rows have to survive a phone-width card
 * without wrapping or overflowing, "open budget" has to land on the tab the
 * card was showing, and closing a project from the card has to reach the
 * backend.
 *
 * Its own file rather than a block in `dashboard.spec.ts`: it needs a mobile
 * viewport (set before the page boots), it navigates off the dashboard, and
 * the closing test writes.
 */
test.describe("dashboard budget card", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  const budgetCard = (page: Page) => page.locator('[data-card-id="budget"]');

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("the tabs scroll inside the card, and the card itself does not", async ({
      page,
    }) => {
      await navigateTo(page, "/");
      const card = budgetCard(page);
      await card.scrollIntoViewIfNeeded();
      const strip = card.getByTestId("dashboard-budget-tabs");
      await expect(strip).toBeVisible({ timeout: 30_000 });

      const geometry = await card.evaluate((el) => {
        const tabs = el.querySelector<HTMLElement>(
          '[data-testid="dashboard-budget-tabs"]',
        )!;
        return {
          cardOverflow: el.scrollWidth - el.clientWidth,
          stripOverflow: tabs.scrollWidth - tabs.clientWidth,
          stripWidth: tabs.clientWidth,
          cardWidth: el.clientWidth,
        };
      });

      // The four tabs don't fit a 390px card — that's the whole point of the
      // strip. They overflow it, not the card.
      expect(geometry.stripOverflow).toBeGreaterThan(0);
      expect(geometry.cardOverflow).toBe(0);
      expect(geometry.stripWidth).toBeLessThanOrEqual(geometry.cardWidth);

      // And the strip is genuinely scrollable: the last tab can be reached.
      const projectsTab = card.getByRole("button", {
        name: /Project Budgets/i,
      });
      await projectsTab.scrollIntoViewIfNeeded();
      await projectsTab.click();
      await expect(projectsTab).toHaveAttribute("aria-pressed", "true");

      // Envelope rows: one line each, even at 390px. The row packs a name, a
      // bar and two figures onto a single line, so a phone is exactly where it
      // would wrap to two lines or push the card sideways.
      const monthlyTab = card.getByRole("button", { name: /Monthly Budget/i });
      await monthlyTab.scrollIntoViewIfNeeded();
      await monthlyTab.click();
      const rows = card.getByTestId("budget-rule-row");
      await expect(rows.first()).toBeVisible({ timeout: 30_000 });

      const rowGeometry = await card.evaluate((el) => {
        const list = [
          ...el.querySelectorAll<HTMLElement>(
            '[data-testid="budget-rule-row"]',
          ),
        ];
        return {
          count: list.length,
          maxHeight: Math.max(
            ...list.map((r) => r.getBoundingClientRect().height),
          ),
          maxOverflow: Math.max(
            ...list.map((r) => r.scrollWidth - r.clientWidth),
          ),
          cardOverflow: el.scrollWidth - el.clientWidth,
        };
      });

      // A phone's budget card shows a month's envelopes, not a handful: the
      // single-column line replaced a four-row tile precisely to fit them.
      expect(rowGeometry.count).toBeGreaterThanOrEqual(5);
      // Two lines of 10-12px text plus padding clears 44px; one does not.
      expect(rowGeometry.maxHeight).toBeLessThan(44);
      expect(rowGeometry.maxOverflow).toBe(0);
      expect(rowGeometry.cardOverflow).toBe(0);

      // The trailing figure keeps its word at every width — an unlabelled
      // number beside "spent / budget" is a guess. The percentage is what the
      // phone drops, since the bar already draws it.
      const firstRow = await rows.first().innerText();
      expect(firstRow).toMatch(/left|over/);
      expect(firstRow).not.toContain("%");
    });
  });

  test("'open budget' lands on the tab the card was showing", async ({
    page,
  }) => {
    await navigateTo(page, "/");
    const card = budgetCard(page);
    await card.scrollIntoViewIfNeeded();

    await card.getByRole("button", { name: /Monthly Budget/i }).click();
    await expect(card.getByTestId("budget-total-bar")).toBeVisible({
      timeout: 30_000,
    });

    // Desktop keeps the percentage the phone drops, as a muted suffix on the
    // remainder rather than the pill the four-row tile used to carry.
    const firstRow = card.getByTestId("budget-rule-row").first();
    await expect(firstRow).toBeVisible({ timeout: 30_000 });
    await expect(firstRow).toContainText("%");
    await expect(firstRow).toContainText(/left|over/);

    await card.getByRole("link", { name: /View All Budget Rules/i }).click();

    await expect(page).toHaveURL(/\/budget\?tab=monthly/);
    // The page's own tab group: the Monthly tab is the pressed one, not the
    // Overview it used to fall back to.
    const pageTabs = page.getByRole("button", { name: /Monthly Budget/i });
    await expect(pageTabs.first()).toHaveAttribute("aria-pressed", "true", {
      timeout: 30_000,
    });

    // Yearly takes the same route, and carries its own year cursor.
    await page.goBack();
    await card.scrollIntoViewIfNeeded();
    await card.getByRole("button", { name: /^Yearly$/i }).click();
    const yearlyLink = card.getByRole("link").last();
    await expect(yearlyLink).toBeVisible({ timeout: 30_000 });
    await yearlyLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/budget\\?tab=yearly&year=${new Date().getFullYear()}`),
    );
    await expect(
      page.getByRole("button", { name: /^Yearly$/i }).first(),
    ).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
  });

  test("closes and reopens a project without leaving the dashboard", async ({
    page,
  }) => {
    await navigateTo(page, "/");
    const card = budgetCard(page);
    await card.scrollIntoViewIfNeeded();

    await card.getByRole("button", { name: /Project Budgets/i }).click();
    const toggle = card.getByTestId("card-project-closed-toggle");
    await expect(toggle).toBeVisible({ timeout: 30_000 });
    await expect(toggle).toHaveAttribute("aria-label", /close project/i);

    await toggle.click();
    const dialog = page.locator("div.modal-overlay", {
      hasText: /stops appearing in the budget overview/i,
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Close project$/i }).click();

    // The card keeps the project — closing is not a delete — and says why it
    // left the Overview.
    await expect(card.getByTestId("card-project-closed-notice")).toBeVisible({
      timeout: 15_000,
    });
    await expect(toggle).toHaveAttribute("aria-label", /reopen project/i);

    // Reopening is a plain undo, with no confirmation step.
    await toggle.click();
    await expect(card.getByTestId("card-project-closed-notice")).toBeHidden({
      timeout: 15_000,
    });
    await expect(toggle).toHaveAttribute("aria-label", /close project/i);
  });
});
