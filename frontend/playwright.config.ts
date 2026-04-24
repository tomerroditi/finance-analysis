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
  fullyParallel: false, // serial by default — demo mode is shared state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // single worker — demo mode is shared state
  reporter: "html",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
