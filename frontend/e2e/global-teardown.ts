/**
 * Global teardown — always leave the backend in production mode.
 *
 * Demo mode is process-global, in-memory backend state. Specs enable it in
 * `beforeAll` and disable it in `afterAll`, but `afterAll` never runs when a
 * run is interrupted (Ctrl-C, crash, timeout kill). Because e2e runs often
 * drive a long-lived dev backend (with_server.py reuses an already-listening
 * port 8000), a leaked toggle leaves that backend serving demo data until the
 * process restarts — the "why is my app in demo mode?" bug.
 *
 * This hook runs after every Playwright run, pass or fail, and force-disables
 * demo mode. Errors are swallowed: if the backend is already gone there is
 * nothing to clean up.
 */
import { request } from "@playwright/test";

const API_BASE = "http://localhost:8000/api";

export default async function globalTeardown() {
  const ctx = await request.newContext();
  try {
    await ctx.post(`${API_BASE}/testing/toggle_demo_mode`, {
      data: { enabled: false },
    });
  } catch {
    // Backend not running — nothing to reset.
  } finally {
    await ctx.dispose();
  }
}
