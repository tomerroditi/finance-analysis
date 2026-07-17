import { test as teardown } from "@playwright/test";
import { disableDemoMode } from "./helpers";

/**
 * Demo-mode teardown project.
 *
 * Runs once, after every dependent project has finished, to switch the
 * backend back out of Demo Mode. Wired up via `teardown: "demo-teardown"`
 * on the `demo-setup` project in `playwright.config.ts`.
 */
teardown("disable demo mode", async () => {
  await disableDemoMode();
});
