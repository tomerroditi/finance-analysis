import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * The hosted demo hands every browser a private sandbox. When that sandbox
 * is not mirrored to durable storage (no Blob store connected), edits live
 * only on the serverless instance that served them and disappear on
 * recycle — visitors must be told, not left to conclude the app is broken.
 * The local backend never reports an ephemeral sandbox, so the two states
 * are driven by stubbing the status endpoint before boot.
 */
test.describe("Demo sandbox notice", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("warns when the sandbox is not durable", async ({ page }) => {
    await page.route("**/api/testing/demo_mode_status", (route) =>
      route.fulfill({
        json: {
          demo_mode: true,
          forced: true,
          sandboxed: true,
          durable: false,
          blob_configured: false,
        },
      }),
    );

    await navigateTo(page, "/");

    const notice = page.getByTestId("demo-sandbox-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText(/not being saved/i);
  });

  test("stays silent when the sandbox is durable or absent", async ({ page }) => {
    await page.route("**/api/testing/demo_mode_status", (route) =>
      route.fulfill({
        json: {
          demo_mode: true,
          forced: true,
          sandboxed: true,
          durable: true,
          blob_configured: true,
        },
      }),
    );

    await navigateTo(page, "/");

    await expect(page.getByRole("navigation").first()).toBeVisible();
    await expect(page.getByTestId("demo-sandbox-notice")).toHaveCount(0);
  });
});
