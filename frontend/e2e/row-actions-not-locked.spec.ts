import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * A transactions row action must only disable its own row.
 *
 * The table renders one mutation per action and every row calls it, so
 * `isPending` is true for the whole table while a single row is being
 * written. Gating each button on that locked every row for the length of the
 * write — seconds on a real database — and a click on another row in that
 * window hit a disabled button and was dropped with no feedback.
 *
 * The write is held open here rather than raced, because on demo data it
 * finishes far too quickly for the pending state to be observable at all.
 */
test.describe("Transactions row actions during a slow write", () => {
  // Mutating spec: the refund mark writes to the shared demo DB.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("one row's write leaves the other rows' buttons clickable", async ({
    page,
  }) => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let posted = 0;

    await page.route("**/api/pending-refunds**", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      posted += 1;
      await held;
      await route.fallback();
    });

    await navigateTo(page, "/transactions");

    const mark = page.getByRole("button", { name: "Mark as Pending Refund" });
    await expect(mark.first()).toBeVisible({ timeout: 45_000 });
    const count = await mark.count();
    expect(count).toBeGreaterThan(1);

    await mark.first().click();

    // The row being written shows its pending refund at once, so its button
    // gives way to the badge; every other row stays usable.
    await expect(mark).toHaveCount(count - 1);
    await expect(mark.first()).toBeEnabled();

    // And a click on one of them actually reaches the backend rather than
    // landing on a dead button.
    await mark.first().click();
    await expect.poll(() => posted).toBe(2);
    await expect(mark).toHaveCount(count - 2);

    release();
    await expect.poll(() => posted, { timeout: 15_000 }).toBe(2);
  });
});
