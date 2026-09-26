import { test, expect } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Creating a Keren Hishtalmut investment by hand, plus the scraped-policy
 * edit-modal lock.
 *
 * Mutating spec (kept out of READ_ONLY_SPECS in playwright.config.ts — the
 * read-only project runs fully parallel against a shared demo DB, and a
 * single backend write there corrupts every parallel sibling).
 *
 * The `request` fixture is Playwright's own HTTP client — it does not run
 * the app's JS, so the axios interceptor that attaches `X-FAD-Demo` from
 * localStorage never runs for it. Every call below declares the header
 * itself to read/write the same database the UI (seeded via
 * `enableDemoMode(page)`) is showing, instead of the real one.
 *
 * Demo data ships all three of the "Investments" category's tags already
 * claimed by existing investments (two manual + a corporate bond), so
 * `filteredCategories` in Investments.tsx is empty and the "New Investment"
 * button renders disabled — confirmed by driving the real UI before writing
 * this spec. A brand-new tag is seeded via the tagging API first (exactly
 * what a user would do from the Categories page) so the button unlocks and
 * the create flow can be driven for real, matching how a fresh account with
 * an unused tag behaves.
 */
const DEMO_HEADERS = { "X-FAD-Demo": "1" };
const SEED_TAG_NAME = "E2E Manual KH Fund";
const INVESTMENT_NAME = "E2E Manual KH Investment";
const LIQUIDITY_DATE = "2029-01-15";
const DEPOSIT_FEE = "1.25";
const MANAGEMENT_FEE = "0.65";

test.describe("Investments — Keren Hishtalmut", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("creates a manual KH investment with its policy metadata", async ({
    page,
    request,
  }) => {
    // Seed a fresh, unused tag under "Investments" — see the file-level
    // comment on why this is required before the create modal can even
    // open. The backend title-cases tag names, so the stored value isn't
    // necessarily verbatim; read it back instead of assuming the exact
    // casing.
    const tagCreate = await request.post(`${API_BASE}/tagging/tags`, {
      headers: DEMO_HEADERS,
      data: { category: "Investments", name: SEED_TAG_NAME },
    });
    expect(tagCreate.ok()).toBeTruthy();

    const categoriesRes = await request.get(`${API_BASE}/tagging/categories`, {
      headers: DEMO_HEADERS,
    });
    const categories = await categoriesRes.json();
    const seededTag: string | undefined = (categories["Investments"] ?? []).find(
      (tag: string) => tag.toLowerCase().includes("manual"),
    );
    expect(seededTag).toBeTruthy();

    let createdId: number | null = null;
    try {
      await navigateTo(page, "/investments");

      await page.getByRole("button", { name: "New Investment" }).click();

      const modal = page.getByRole("dialog");
      await expect(modal).toBeVisible();

      await modal.getByPlaceholder("e.g. S&P 500 Index Fund").fill(INVESTMENT_NAME);

      // Category and Tag are custom SelectDropdown components whose option
      // lists render through a React portal onto document.body, so the
      // trigger button is scoped to the modal but the option itself is not.
      await modal.getByRole("button", { name: "Select Category" }).click();
      await page.getByRole("option", { name: "Investments" }).click();

      await modal.getByRole("button", { name: "Select Tag" }).click();
      await page.getByRole("option", { name: seededTag! }).click();

      // Type defaults to "Stocks". Switching it to Keren Hishtalmut reveals
      // the KH-only fields (liquidity date, deposit fee, management fee)
      // and must NOT reveal the interest-rate fields — hishtalmut is
      // deliberately excluded from RATE_TYPES.
      await modal.getByRole("button", { name: "Stocks" }).click();
      await page.getByRole("option", { name: "Keren Hishtalmut" }).click();

      await expect(modal.getByText(/Deposit fee/i)).toBeVisible();
      await expect(modal.getByText(/Management fee/i)).toBeVisible();
      await expect(modal.getByText(/Rate Type/i)).toHaveCount(0);

      // The KH field labels aren't wired to their inputs via htmlFor/id, so
      // they carry no accessible name — select by input type/order instead
      // (confirmed against the real DOM: liquidity date, then deposit fee,
      // then management fee, and no other type="number" inputs render for
      // a KH-typed investment).
      await modal.locator('input[type="date"]').fill(LIQUIDITY_DATE);
      const feeInputs = modal.locator('input[type="number"]');
      await feeInputs.nth(0).fill(DEPOSIT_FEE);
      await feeInputs.nth(1).fill(MANAGEMENT_FEE);

      await modal.getByRole("button", { name: "Create Investment" }).click();
      await expect(modal).not.toBeVisible();

      const card = page
        .locator("div.group", {
          has: page.getByRole("heading", { name: INVESTMENT_NAME }),
        })
        .first();
      await expect(card).toBeVisible({ timeout: 15_000 });

      await expect(card.getByText("Keren Hishtalmut", { exact: true })).toBeVisible();
      await expect(card.getByText(`Liquid ${LIQUIDITY_DATE}`)).toBeVisible();
      await expect(card.getByText(`${DEPOSIT_FEE}%`)).toBeVisible();
      await expect(card.getByText(`${MANAGEMENT_FEE}%`)).toBeVisible();

      const list = await request.get(`${API_BASE}/investments/`, {
        headers: DEMO_HEADERS,
      });
      const record = (await list.json()).find(
        (inv: { name: string }) => inv.name === INVESTMENT_NAME,
      );
      expect(record).toBeTruthy();
      createdId = record.id;
    } finally {
      if (createdId != null) {
        await request.delete(`${API_BASE}/investments/${createdId}`, {
          headers: DEMO_HEADERS,
        });
      }
      if (seededTag) {
        await request.delete(
          `${API_BASE}/tagging/tags/${encodeURIComponent("Investments")}/${encodeURIComponent(seededTag)}`,
          { headers: DEMO_HEADERS },
        );
      }
    }
  });

  test("edit modal locks the type dropdown for a scraped KH policy", async ({
    page,
    request,
  }) => {
    const list = await request.get(`${API_BASE}/investments/`, {
      headers: DEMO_HEADERS,
    });
    const scraped = (await list.json()).find(
      (inv: { type: string; insurance_policy_id: string | null }) =>
        inv.type === "hishtalmut" && inv.insurance_policy_id != null,
    );
    expect(scraped).toBeTruthy();

    await navigateTo(page, "/investments");
    const card = page
      .locator("div.group", {
        has: page.getByRole("heading", { name: scraped.name, exact: true }),
      })
      .first();
    await expect(card).toBeVisible({ timeout: 15_000 });

    await card.getByTitle("Edit").click();

    const modal = page.getByRole("dialog");
    const typeButton = modal.getByRole("button", { name: "Keren Hishtalmut" });
    await expect(typeButton).toBeVisible();
    await expect(modal.getByText("Set by the scraped policy")).toBeVisible();

    // Clicking the locked trigger must not open the option list — the
    // component disables it via a JS guard rather than the HTML `disabled`
    // attribute, so behavior (not the attribute) is what to verify.
    await typeButton.click();
    await expect(page.getByRole("option", { name: "Stocks" })).toHaveCount(0);

    // The KH-only fields (liquidity date, both fee inputs) are plain native
    // <input> elements, not the SelectDropdown's JS-guarded trigger — a
    // real `disabled` attribute is what the DOM exposes here, so assert on
    // that directly rather than on click-behavior.
    const liquidityDateInput = modal
      .getByText("Liquid", { exact: true })
      .locator("xpath=following-sibling::input");
    const depositFeeInput = modal
      .getByText("Deposit fee", { exact: true })
      .locator("xpath=following-sibling::input");
    const managementFeeInput = modal
      .getByText("Management fee", { exact: true })
      .locator("xpath=following-sibling::input");
    await expect(liquidityDateInput).toBeDisabled();
    await expect(depositFeeInput).toBeDisabled();
    await expect(managementFeeInput).toBeDisabled();

    // Demo KH policies are seeded with a genuine 0% deposit fee
    // (scripts/generate_demo_data.py) — a disabled input still exposes its
    // value, so this pins the "0" vs "" distinction from seedEditForm
    // (Investments.tsx) even while the field is locked.
    await expect(depositFeeInput).toHaveValue("0");
  });
});
