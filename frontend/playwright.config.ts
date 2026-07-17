import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E test configuration.
 *
 * Tests run against Demo Mode, which provides pre-built sample data
 * in an isolated database. The backend and frontend dev servers must
 * be started before running tests:
 *
 *   python .claude/scripts/with_server.py -- npx playwright test
 *
 * Or start them manually:
 *   Backend: poetry run uvicorn backend.main:app --reload (port 8000)
 *   Frontend: npm run dev (port 5173)
 */
export default defineConfig({
  testDir: "./e2e",
  // Always reset demo mode after a run — interrupted runs otherwise leave a
  // long-lived dev backend stuck serving demo data (see global-teardown.ts).
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false, // serial by default — demo mode is shared state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // single worker — demo mode is shared state
  reporter: "html",
  timeout: 120_000,
  expect: {
    // The dashboard fires ~30 React Query requests in parallel on cold
    // load. The browser caps HTTP/1.1 to 6 concurrent connections to one
    // origin, so the slowest endpoints (net-worth-over-time, portfolio
    // analysis, monthly-expenses) end up waiting 13–25s in the queue.
    // KPI labels render only after their query resolves, so the default
    // 5s expect timeout times out before the data lands. 45s is safe
    // for cold-cache navigations on a saturated dev server; the right
    // long-term fix is HTTP/2 on the backend (or batched query
    // endpoints), not bumping the timeout further.
    timeout: 45_000,
  },
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } }
          : {}),
      },
    },
  ],
});
