import { test as teardown } from "@playwright/test";
import { resetDemoData } from "./helpers";

/**
 * Demo-mode teardown project.
 *
 * Runs once, after every dependent project has finished. Demo Mode is now
 * per-client, so there is no backend flag to switch back off — instead this
 * rebuilds the demo database from its frozen snapshot, discarding whatever
 * the `mutating` project's specs wrote, so the demo DB is pristine again for
 * the next run (or for anyone browsing Demo Mode by hand right after a
 * suite run). Wired up via `teardown: "demo-teardown"` on the `demo-setup`
 * project in `playwright.config.ts`.
 */
teardown("reset the demo database", async () => {
  await resetDemoData();
});
