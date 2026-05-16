import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, request, type APIRequestContext } from "@playwright/test";
import {
  API_BASE,
  enableDemoMode,
  disableDemoMode,
  navigateTo,
} from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(HERE, "fixtures", "import-sample.csv");
const ACCOUNT_NAME = "Imported Checking";

/**
 * Remove any leftover imported account named ACCOUNT_NAME so the test starts
 * from a known state. Demo mode runs against an isolated SQLite DB, but the
 * DB persists between test runs — without this cleanup, the second run would
 * see the file's rows already loaded and dedup down to 0 inserts, breaking
 * the "imported 3 new transactions" assertion.
 */
async function cleanupImportedAccount(ctx: APIRequestContext) {
  const resp = await ctx.get(`${API_BASE}/imported-accounts/`);
  if (!resp.ok()) return;
  const accounts = (await resp.json()) as Array<{
    id: number;
    account_name: string;
  }>;
  for (const account of accounts) {
    if (account.account_name === ACCOUNT_NAME) {
      await ctx.delete(`${API_BASE}/imported-accounts/${account.id}`);
    }
  }
}

test.describe("Import from File", () => {
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

  test.beforeEach(async () => {
    const ctx = await request.newContext();
    try {
      await cleanupImportedAccount(ctx);
    } finally {
      await ctx.dispose();
    }
  });

  test("creates an imported bank account, maps columns, and shows the rows in Transactions", async ({
    page,
  }) => {
    await navigateTo(page, "/data-sources");

    // 1. Open the wizard via the "Import from File" button.
    await page.getByRole("button", { name: /import from file/i }).click();

    // 2. Step 1: pick service = Bank Account.
    await page.getByRole("button", { name: /^bank account$/i }).first().click();

    // 3. Step 2: provider + account name, then Next.
    await page
      .getByPlaceholder(/hapoalim manual/i)
      .fill("Hapoalim Manual");
    await page
      .getByPlaceholder(/checking/i)
      .fill(ACCOUNT_NAME);
    await page.getByRole("button", { name: /^next$/i }).click();

    // 4. Step 3: upload the fixture file. The <input type="file"> is hidden
    //    but setInputFiles works on hidden inputs.
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(FIXTURE);

    // 5. Pick mapping columns. The preview request runs on every mapping
    //    change; wait for the column dropdown options to be populated.
    const dateSelect = page.getByLabel(/date column/i);
    await expect(dateSelect).toBeVisible();
    await expect(dateSelect.locator("option")).toHaveCount(4); // "—" + 3 csv headers
    await dateSelect.selectOption("date");
    await page.getByLabel(/description column/i).selectOption("description");
    await page.getByLabel(/^amount column/i).selectOption("amount");

    // 6. Save mapping and import.
    await page.getByRole("button", { name: /save mapping & import/i }).click();

    // Expect the success toast confirming 3 rows were imported.
    await expect(page.getByText(/imported 3 new transactions/i)).toBeVisible({
      timeout: 15_000,
    });

    // 7. Navigate to /transactions via a same-page client-side route change.
    //    The helpers' `navigateTo` does `page.goto("about:blank")` which
    //    destroys the QueryClient that was just told to invalidate the
    //    transactions cache after the import mutation. A sidebar-link click
    //    keeps the in-memory cache around so the stale-then-refetch flow
    //    actually picks up the newly imported rows.
    await page
      .getByRole("link", { name: /transactions/i })
      .first()
      .click();
    await page.waitForURL(/\/transactions$/);
    await page.waitForLoadState("networkidle");

    // The imported dates (2026-03-*) are months behind the demo data, so use
    // the search box to surface our rows rather than scrolling through pages.

    const searchBox = page.getByPlaceholder(/search/i).first();
    await expect(searchBox).toBeVisible({ timeout: 10_000 });
    await searchBox.fill("Coffee shop");
    await expect(page.getByText("Coffee shop").first()).toBeVisible({
      timeout: 15_000,
    });

    await searchBox.fill("Salary");
    await expect(page.getByText("Salary").first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
