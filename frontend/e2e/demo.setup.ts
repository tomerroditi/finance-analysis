import { test as setup } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Demo-mode setup project.
 *
 * Demo Mode is now per-client (a localStorage flag carried to the backend
 * via the `X-FAD-Demo` header), so this project no longer "enables"
 * anything globally — there is no backend flag left to flip, and every spec
 * seeds its own browser context via `enableDemoMode(page)` in its own
 * `beforeEach`.
 *
 * What this project still buys: `enableDemoMode`'s `demo/prepare` call
 * builds the demo database file once, before the `read-only` project fans
 * its (write-free) specs across multiple workers. Without running it here
 * first as a declared dependency, several workers could race to build the
 * demo DB file on their own first spec at once.
 */
setup("prepare the demo database", async ({ page }) => {
  await enableDemoMode(page);
});
