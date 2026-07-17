import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E test configuration.
 *
 * Tests run against Demo Mode, which provides pre-built sample data in an
 * isolated database. The backend and frontend dev servers must be started
 * before running tests:
 *
 *   python .claude/scripts/with_server.py -- npx playwright test
 *
 * Or start them manually:
 *   Backend: poetry run uvicorn backend.main:app --reload (port 8000)
 *   Frontend: npm run dev (port 5173)
 *
 * ## Projects & parallelism
 *
 * Demo Mode is a process-global backend singleton (one shared SQLite DB),
 * so the suite is split into two phases sequenced by a shared setup project:
 *
 *   demo-setup ─▶ read-only (parallel) ─▶ mutating (serial) ─▶ demo-teardown
 *
 * - `demo-setup` enables Demo Mode once (was: a full DB rebuild at every
 *   file boundary via per-file beforeAll/afterAll).
 * - `read-only` holds specs that perform ZERO backend writes. They share the
 *   one demo snapshot safely, so they fan out across workers (`fullyParallel`).
 * - `mutating` holds everything else. Each mutating spec still manages its own
 *   demo lifecycle (beforeAll/afterAll) for per-file DB isolation, so this
 *   project stays serial (`--workers=1`).
 *
 * `npm run test:e2e` is a bare `playwright test`: everything runs serially
 * (global `workers: 1`) and is always safe. read-only and mutating are both
 * plain, shardable projects (CI runs `playwright test --shard=X/4`); each spec
 * self-heals demo mode in its own beforeAll, so they can run in any order or
 * interleave within a shard without a spec's teardown pulling demo out from
 * under another.
 *
 * `npm run test:e2e:parallel` fans `read-only` across workers, then runs
 * `mutating` serially. This ONLY helps when the backend can sustain the
 * concurrency; on a single shared uvicorn+SQLite backend (e.g. the web sandbox)
 * even 2 workers saturate the serialized query path and the heavy cold-cache
 * dashboards time out — measured slower than serial. Real parallel speedup
 * needs per-worker isolated backends. See `.claude/rules/testing.md`.
 */

/**
 * Specs that perform ZERO backend writes — pure navigate + assert (at most
 * opening a popover, toggling a view, or switching a chart tab). Safe to run
 * concurrently against the single shared Demo Mode snapshot.
 *
 * ⚠️  AIRTIGHT RULE: a spec may ONLY live here if it never mutates backend
 * state — no POST/PUT/DELETE, no form submit, no create/edit/delete/move of
 * data. One writing spec in this list corrupts every sibling running in
 * parallel. When in doubt, leave it OUT: unlisted specs run serially in the
 * `mutating` project, which is always safe. If you add a write to a spec
 * listed here, MOVE IT OUT of this list in the same change.
 */
const READ_ONLY_SPECS = [
  "**/budget-net-refund.spec.ts",
  "**/categories.spec.ts",
  "**/chart-styling.spec.ts",
  "**/charts-render.spec.ts",
  "**/dashboard-block-sizes.spec.ts",
  "**/dashboard-insights-strip.spec.ts",
  "**/dashboard-lazy-cards.spec.ts",
  "**/dashboard-networth-monthly-change.spec.ts",
  "**/dashboard-spending-calendar.spec.ts",
  "**/data-flow.spec.ts",
  "**/income-by-source-card.spec.ts",
  "**/info-tooltip-aria-label.spec.ts",
  "**/investments.spec.ts",
  "**/liabilities.spec.ts",
  "**/route-prefetch.spec.ts",
  "**/rtl-chevrons.spec.ts",
];

const chromiumUse = {
  ...devices["Desktop Chrome"],
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } }
    : {}),
};

export default defineConfig({
  testDir: "./e2e",
  // Always reset demo mode after a run — interrupted runs otherwise leave a
  // long-lived dev backend stuck serving demo data (see global-teardown.ts).
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false, // serial by default — demo mode is shared state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Serial by default so a bare `playwright test` (or a single-spec dev run)
  // is always safe against the shared Demo Mode DB. The `test:e2e` npm script
  // overrides `--workers` per phase (parallel read-only, serial mutating).
  workers: 1,
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
      name: "demo-setup",
      testMatch: /demo\.setup\.ts$/,
      teardown: "demo-teardown",
      use: chromiumUse,
    },
    {
      name: "demo-teardown",
      testMatch: /demo\.teardown\.ts$/,
      use: chromiumUse,
    },
    {
      name: "read-only",
      testMatch: READ_ONLY_SPECS,
      dependencies: ["demo-setup"],
      fullyParallel: true,
      use: chromiumUse,
    },
    {
      name: "mutating",
      testMatch: /\.spec\.ts$/,
      testIgnore: READ_ONLY_SPECS,
      // Depend on demo-setup only — NOT read-only. Making read-only a
      // dependency would turn it into a non-shardable setup project that
      // re-runs in full in every CI shard (Playwright never shards
      // dependencies). Instead, read-only and mutating are both plain,
      // shardable projects; each spec self-heals demo mode in its own
      // beforeAll, so they can interleave within a shard safely.
      dependencies: ["demo-setup"],
      fullyParallel: false,
      use: chromiumUse,
    },
  ],
});
