import {
  test,
  expect,
  request,
  type APIRequestContext,
  type Browser,
} from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

interface TrendPoint {
  limits: Record<string, number>;
}

interface AnalysisItem {
  rule: { id: number; name: string; amount: number };
}

/**
 * The monthly sparkline's dashed reference follows each month's own limit.
 *
 * A monthly rule is a fresh, separately editable row per month, so a
 * single flat line across the whole series measured every month against
 * today's cap: raise the rule and a month that overspent went quietly
 * green, cut it and a month that came in on budget turned red. The line now
 * steps with the limit, and each bar takes its colour from the cap that was
 * actually in force.
 */
test.describe("Budget sparkline stepped limit", () => {
  // Restore pristine demo data before this file runs — this spec edits a
  // rule's amount, and the demo database is process-global.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  /** Every y the reference path visits, in order. */
  const heights = (d: string) =>
    Array.from(d.matchAll(/[ML] [\d.]+,([\d.]+)/g)).map((m) => Number(m[1]));

  /**
   * A fresh browser context on the monthly ledger, with the sparkline
   * reference for `ruleName` located.
   *
   * Deliberately a new context per read rather than `page.reload()`: the
   * trend query has a 60 s `staleTime` and the React Query cache is
   * persisted to IndexedDB, so a reload re-serves the limits fetched before
   * the edit. A new context starts with an empty store and refetches.
   */
  async function openLedger(browser: Browser, ruleName: string) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await enableDemoMode(page);
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });
    const reference = page
      .locator("button[aria-expanded]")
      .filter({ hasText: ruleName })
      .first()
      .getByTestId("rule-sparkline")
      .first()
      .locator('[data-testid="budget-reference"]');
    await expect(reference).toHaveCount(1);
    return { context, reference };
  }

  test("steps the dashed reference when a month's limit differs", async ({
    browser,
  }) => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;

    const ctx: APIRequestContext = await request.newContext({
      extraHTTPHeaders: { "X-FAD-Demo": "1" },
    });

    let target: AnalysisItem["rule"] | undefined;

    try {
      // The analysis auto-fills the current month from its predecessor; the
      // trend never does, so ask for the analysis first or the current
      // month's limits come back empty.
      const analysis = await (
        await ctx.get(`${API_BASE}/budget/analysis/${year}/${month}`)
      ).json();
      const trend: TrendPoint[] = await (
        await ctx.get(`${API_BASE}/budget/trend/${year}/${month}?months=3`)
      ).json();

      // Rules the whole window shares, so the "before" line is genuinely
      // flat and the step below can only have come from the edit.
      const spanning = Object.keys(trend.at(-1)?.limits ?? {}).filter(
        (name) =>
          name !== "Total Budget" &&
          trend.every((point) => (point.limits?.[name] ?? 0) > 0),
      );

      // Not every rule accepts an edit — an `all_tags` rule sharing its
      // category with specific-tag rules is rejected whatever the amount.
      // Probe with the value this test actually wants to write (an unchanged
      // amount short-circuits validation, so it proves nothing), then put it
      // straight back so the page still loads on a flat reference.
      for (const name of spanning) {
        const item: AnalysisItem | undefined = analysis.rules.find(
          (entry: AnalysisItem) => entry.rule.name === name,
        );
        if (!item) continue;
        const probe = await ctx.put(`${API_BASE}/budget/rules/${item.rule.id}`, {
          data: { amount: item.rule.amount / 2 },
        });
        if (probe.ok()) {
          target = item.rule;
          await ctx.put(`${API_BASE}/budget/rules/${target.id}`, {
            data: { amount: target.amount },
          });
          break;
        }
      }
      test.skip(!target, "Demo data has no editable rule spanning the window");

      const flat = await openLedger(browser, target!.name);
      // One limit all along → one flat run, edge to edge.
      expect(new Set(heights((await flat.reference.getAttribute("d")) ?? "")).size).toBe(
        1,
      );
      await flat.context.close();

      // Halve this month's rule — downwards, so no total-budget cap is
      // at stake. Only this month's row changes, so the reference must drop
      // for the last bar alone.
      const put = await ctx.put(`${API_BASE}/budget/rules/${target!.id}`, {
        data: { amount: target!.amount / 2 },
      });
      expect(put.ok()).toBeTruthy();

      const stepped = await openLedger(browser, target!.name);
      const after = (await stepped.reference.getAttribute("d")) ?? "";
      const levels = heights(after);
      expect(new Set(levels).size).toBe(2);
      // Still one run — the step is a riser inside the path, not a second
      // line floating beside it.
      expect(after.match(/M /g)).toHaveLength(1);
      // A smaller rule sits lower, and y grows downwards.
      expect(levels.at(-1)!).toBeGreaterThan(levels[0]);
      await stepped.context.close();
    } finally {
      if (target) {
        await ctx.put(`${API_BASE}/budget/rules/${target.id}`, {
          data: { amount: target.amount },
        });
      }
      await ctx.dispose();
    }
  });
});
