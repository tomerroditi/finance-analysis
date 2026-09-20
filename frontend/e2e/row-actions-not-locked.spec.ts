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
    expect(await mark.count()).toBeGreaterThan(1);

    const first = mark.nth(0);
    const second = mark.nth(1);
    await first.click();

    // The row being written is held; every other row stays usable.
    await expect(first).toBeDisabled();
    await expect(second).toBeEnabled();

    // And a click on one of them actually reaches the backend rather than
    // landing on a dead button.
    await second.click();
    await expect.poll(() => posted).toBe(2);

    release();
    await expect.poll(() => posted, { timeout: 15_000 }).toBe(2);
  });
});
