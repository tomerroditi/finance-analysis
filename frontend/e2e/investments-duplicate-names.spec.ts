import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Regression: same-named investments must stay separate chart series.
 *
 * Three real Keren Hishtalmut accounts share the display name "קרן השתלמות".
 * The Balance Over Time chart used to key its series by `name`, so all three
 * collapsed into one column whose value at each date came from whichever
 * account happened to have a sample there — the line zig-zagged between
 * account balances. Series are now keyed by investment id, and a repeated
 * name is disambiguated in the legend with the account tag.
 *
 * Mutating spec (kept out of READ_ONLY_SPECS): seeds two same-named
 * investments plus a balance snapshot each, then cleans up.
 *
 * The `request` fixture is Playwright's own HTTP client — it does not run
 * the app's JS, so the axios interceptor that attaches `X-FAD-Demo` from
 * localStorage never runs for it. Every call below must declare the header
 * itself to read/write the same database the UI (seeded via
 * `enableDemoMode(page)`) is showing, instead of the real one.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };
const NAME = "E2E Duplicate Fund";
const ACCOUNTS = [
  { tag: "E2E Dup A", date: "2026-05-15", balance: 1000 },
  { tag: "E2E Dup B", date: "2026-06-20", balance: 90000 },
];

test.describe("Investments duplicate names", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("same-named investments render as separate, labelled series", async ({
    page,
    request,
  }) => {
    const created: number[] = [];
    try {
      for (const account of ACCOUNTS) {
        const create = await request.post(`${API_BASE}/investments/`, {
          headers: DEMO_HEADERS,
          data: {
            category: "Investments",
            tag: account.tag,
            type: "keren_hishtalmut",
            name: NAME,
            interest_rate_type: "variable",
          },
        });
        expect(create.ok()).toBeTruthy();

        const list = await request.get(`${API_BASE}/investments/`, {
          headers: DEMO_HEADERS,
        });
        const record = (await list.json()).find(
          (inv: { tag: string }) => inv.tag === account.tag,
        );
        expect(record).toBeTruthy();
        created.push(record.id);

        // A snapshot each, on different dates and at very different levels:
        // the old name-keyed merge alternated between these two levels.
        const snapshot = await request.post(
          `${API_BASE}/investments/${record.id}/balances`,
          {
            headers: DEMO_HEADERS,
            data: { date: account.date, balance: account.balance },
          },
        );
        expect(snapshot.ok()).toBeTruthy();
      }

      await navigateTo(page, "/investments");
      const legend = page.locator(".recharts-legend-wrapper").first();
      await expect(legend).toBeVisible({ timeout: 30_000 });

      // Each duplicate is disambiguated by its account tag, so the two
      // series are individually identifiable instead of both reading
      // "E2E Duplicate Fund".
      for (const account of ACCOUNTS) {
        await expect(
          legend.getByText(`${NAME} · ${account.tag}`),
        ).toBeVisible();
      }

      // No two legend entries share a label — a repeated label is the
      // visible symptom of two series collapsing onto one dataKey.
      const labels = await legend.locator("li").allInnerTexts();
      expect(labels.length).toBeGreaterThan(0);
      expect(new Set(labels).size).toBe(labels.length);
    } finally {
      for (const id of created) {
        await request.delete(`${API_BASE}/investments/${id}`, {
          headers: DEMO_HEADERS,
        });
      }
    }
  });
});
