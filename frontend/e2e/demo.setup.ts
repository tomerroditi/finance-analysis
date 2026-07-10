import { test as setup } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Demo-mode setup project.
 *
 * Enables Demo Mode exactly once, before the `read-only` and `mutating`
 * projects run (they declare this as a dependency). This replaces the old
 * per-file `beforeAll(enableDemoMode)` / `afterAll(disableDemoMode)` dance,
 * which flipped the global demo toggle at every file boundary and forced a
 * full demo-DB rebuild (file copy + date-shift over every table) each time.
 *
 * Because demo mode is a process-global backend singleton, enabling it once
 * up front also makes it safe for the `read-only` project to fan its
 * (write-free) specs across multiple workers: every worker sees demo mode
 * already on, so nothing races to rebuild the DB.
 */
setup("enable demo mode", async () => {
  await enableDemoMode();
});
