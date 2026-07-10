import { test, expect } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Guards the "net refund" display invariant on the monthly budget view.
 *
 * A budget rule's period can net to a refund when refunds exceed spend
 * (e.g. the "Other Expenses" catch-all absorbing reversed/stolen-card
 * charges). Such a row must be rendered as a credit — a 0%-filled bar,
 * never a red "over budget" bar — even though its magnitude may exceed the
 * budget. The previous `Math.abs(current_amount)` logic rendered a large
 * net refund as a full red overspent bar; this spec locks that out.
 *
 * The deterministic reproduction of the bug lives in the component test
 * (`src/components/budget/BudgetRuleRow.test.tsx`), which can force a
 * negative `current`. Demo data doesn't guarantee a net-refund month, so
 * here we assert the invariant holds across every rendered rule row and
 * every recent month, catching a regression the moment such a row appears.
 */
test.describe("Budget — net refund rows", () => {
  test("a refund figure is never shown as over budget", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    let sampledRows = 0;
    // Walk back through several months so more rule rows are sampled.
    for (let i = 0; i < 6; i++) {
      const rows = await page.evaluate(() => {
        const strip = (s: string | null) =>
          (s ?? "").replace(/[⁦⁩\s]/g, "");
        // Rule rows are the bordered cards that hold a font-mono figure and a
        // progress-bar fill; scope to the monthly budget list.
        const figures = [...document.querySelectorAll("span.font-mono")];
        return figures.map((fig) => {
          const row = fig.closest("div.rounded-xl") ?? fig.parentElement;
          const text = strip(fig.textContent);
          // Leading signed amount, e.g. "-1,200 ₪ / 3,000 ₪" -> -1200.
          const m = text.match(/^(-?)([\d,]+)/);
          const amount = m ? Number(m[2].replace(/,/g, "")) * (m[1] ? -1 : 1) : 0;
          const hasRose = !!row?.querySelector(".bg-rose-500");
          const hasOver = strip(row?.textContent ?? "").includes("over");
          return { text, amount, hasRose, hasOver };
        });
      });

      sampledRows += rows.length;
      for (const row of rows) {
        if (row.amount < 0) {
          expect(
            row.hasRose,
            `net-refund row "${row.text}" must not show a red over-budget bar`,
          ).toBe(false);
          expect(
            row.hasOver,
            `net-refund row "${row.text}" must not show an "over" hint`,
          ).toBe(false);
        }
      }

      const prev = page.locator('button[aria-label="Previous"]').first();
      if (!(await prev.isVisible().catch(() => false))) break;
      await prev.click();
      await page.waitForLoadState("networkidle");
    }

    // Guard against a selector regression silently making the invariant
    // above vacuous: we must have actually parsed some rule-row figures.
    expect(sampledRows).toBeGreaterThan(0);
  });
});
