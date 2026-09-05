/**
 * Global teardown — leave the shared demo database in a pristine state.
 *
 * Demo Mode is now per-client (a localStorage flag + the `X-FAD-Demo`
 * header), so there is no backend-side flag left to leak between runs —
 * each Playwright browser context is torn down with the test that used it,
 * taking its Demo Mode choice with it. What *does* persist across runs is
 * the demo database file on disk, which the `mutating` project's specs
 * write to. This hook runs after every Playwright run, pass or fail, and
 * rebuilds it from the frozen snapshot so an interrupted run (Ctrl-C, crash,
 * timeout kill — which skips `demo.teardown.ts`) doesn't leave a dirtied
 * demo DB for the next run or for anyone browsing Demo Mode by hand.
 *
 * Errors are swallowed: if the backend is already gone there is nothing to
 * clean up.
 */
import { request } from "@playwright/test";
import { API_BASE } from "./helpers";

export default async function globalTeardown() {
  const ctx = await request.newContext();
  try {
    await ctx.post(`${API_BASE}/testing/demo/reset`);
  } catch {
    // Backend not running — nothing to reset.
  } finally {
    await ctx.dispose();
  }
}
