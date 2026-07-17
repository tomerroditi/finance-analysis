import { test, expect, type APIRequestContext } from "@playwright/test";
import { API_BASE } from "./helpers";

/**
 * End-to-end coverage for the onboarding wizard flows.
 *
 * Complements `Onboarding.test.tsx` (vitest, mocked router/demo-mode) by
 * driving the real backend + real React Router. Each test starts from a
 * fresh empty database so the OnboardingGate's `is_first_run` redirect
 * works as designed and the wizard isn't short-circuited.
 *
 * The spec is **opt-in** — set `E2E_EMPTY_DB=1` and boot the backend
 * with `FAD_USER_DIR` pointed at a throw-away tmpdir. The
 * `.claude/scripts/run_empty_db_e2e.sh` runner does both. See the
 * sibling `empty-state.spec.ts` for the same pattern.
 *
 * Side-effect hygiene:
 *   - The demo-path test toggles Demo Mode on. The afterEach cleanup
 *     toggles it back off so subsequent tests run against the empty
 *     production DB.
 *   - Each test gets a fresh browser context (the Playwright default),
 *     so sessionStorage / localStorage / i18n persistence don't leak
 *     between tests.
 */

const SHOULD_RUN = process.env.E2E_EMPTY_DB === "1";

const DEMO_TOGGLE_URL = `${API_BASE}/testing/toggle_demo_mode`;
const DEMO_STATUS_URL = `${API_BASE}/testing/demo_mode_status`;

test.describe("Onboarding flows", () => {
  test.skip(
    !SHOULD_RUN,
    "Set E2E_EMPTY_DB=1 (and point the backend at an empty FAD_USER_DIR) to run.",
  );

  // Defensive: a previous test that crashed mid-flight could have left
  // Demo Mode on. Reset before every test so the wizard always starts
  // against an empty backend.
  test.beforeEach(async ({ request }) => {
    await ensureDemoModeOff(request);
  });

  test.afterEach(async ({ request }) => {
    await ensureDemoModeOff(request);
  });

  test("real-data path lands on /data-sources without touching demo mode", async ({
    page,
    request,
  }) => {
    await page.goto("/onboarding");
    await expect(page.getByRole("button", { name: /^English/ })).toBeVisible();

    await page.getByRole("button", { name: /^English/ }).click();
    await page.getByRole("button", { name: /Use my real data/i }).click();

    const finish = page.getByRole("button", { name: /Go to Data Sources/i });
    await expect(finish).toBeVisible();
    await finish.click();

    await page.waitForURL(/\/data-sources$/);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();

    // Side-effect check: real path must NOT have toggled Demo Mode.
    const status = await request.get(DEMO_STATUS_URL);
    expect((await status.json()).demo_mode).toBe(false);
  });

  test("demo path turns Demo Mode on and lands on the dashboard", async ({
    page,
    request,
  }) => {
    await page.goto("/onboarding");
    await page.getByRole("button", { name: /^English/ }).click();
    await page.getByRole("button", { name: /Explore with demo/i }).click();

    // Done step shows the dashboard CTA once toggleDemoMode resolves —
    // the API call hits prepare_demo_database() which can take a few
    // seconds on cold start, so we give it a generous timeout.
    const finish = page.getByRole("button", { name: /Go to dashboard/i });
    await expect(finish).toBeVisible({ timeout: 20_000 });

    // Confirm the backend actually flipped before we click through.
    const status = await request.get(DEMO_STATUS_URL);
    expect((await status.json()).demo_mode).toBe(true);

    await finish.click();
    await page.waitForURL((url) => url.pathname === "/");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  });

  test("Skip for now bails out to the dashboard at any step", async ({
    page,
  }) => {
    await page.goto("/onboarding");
    await page.getByRole("button", { name: /Skip for now/i }).click();
    await page.waitForURL((url) => url.pathname === "/");
    expect(page.url()).not.toContain("/onboarding");
  });

  test("Hebrew language pick switches direction to RTL and continues in Hebrew", async ({
    page,
  }) => {
    await page.goto("/onboarding");

    await page.getByRole("button", { name: /עברית/ }).click();

    // The next step should render in Hebrew with RTL direction.
    await expect(
      page.getByRole("heading", { name: /איך מתחילים/ }),
    ).toBeVisible();

    const dir = await page.evaluate(() => document.documentElement.dir);
    expect(dir).toBe("rtl");
  });

  test("Hebrew + real-data path renders the Hebrew Done-step CTA", async ({
    page,
  }) => {
    // Locks down the full translation chain: an English start should
    // not leak into the Done step after a language switch, and every
    // Done-step key must have a real Hebrew value (not the EN
    // fallback rendering as the key path).
    await page.goto("/onboarding");
    await page.getByRole("button", { name: /עברית/ }).click();
    await page
      .getByRole("button", { name: /להשתמש בנתונים אמיתיים/ })
      .click();
    await expect(
      page.getByRole("button", { name: /מעבר למקורות נתונים/ }),
    ).toBeVisible();
    // The English finish CTA must not be present after the language
    // switch.
    await expect(
      page.getByRole("button", { name: /Go to Data Sources/i }),
    ).toHaveCount(0);
  });

  test("step indicator advances aria-valuenow through the wizard", async ({
    page,
  }) => {
    await page.goto("/onboarding");
    const progress = page.getByRole("progressbar");
    await expect(progress).toHaveAttribute("aria-valuenow", "1");
    await expect(progress).toHaveAttribute("aria-valuemax", "3");

    await page.getByRole("button", { name: /^English/ }).click();
    await expect(progress).toHaveAttribute("aria-valuenow", "2");

    await page.getByRole("button", { name: /Use my real data/i }).click();
    await expect(progress).toHaveAttribute("aria-valuenow", "3");
  });

  test("OnboardingGate redirect fires at most once per session", async ({
    page,
  }) => {
    // First visit to "/" — gate redirects to /onboarding and stamps
    // sessionStorage so it won't bounce again this session.
    await page.goto("/");
    await page.waitForURL(/\/onboarding/, { timeout: 5_000 });

    // Second visit to "/" within the same browser context. This time
    // the gate must respect the dismissal flag and let the dashboard
    // render.
    await page.goto("/");

    // Give the gate's effect a tick to run; assert we did NOT bounce.
    expect(page.url()).toMatch(/\/$/);
    expect(page.url()).not.toContain("/onboarding");

    // Layout shell mounted — Sidebar's <nav> proves we landed on the
    // dashboard route rather than getting bounced. The Dashboard
    // page itself has no h1 (it's KPI cards + charts), so we assert
    // on the Layout chrome instead.
    await expect(page.getByRole("navigation").first()).toBeVisible({
      timeout: 10_000,
    });
  });
});

async function ensureDemoModeOff(request: APIRequestContext): Promise<void> {
  try {
    const status = await request.get(DEMO_STATUS_URL);
    if (!status.ok()) return;
    const body = await status.json();
    if (body.demo_mode) {
      await request.post(DEMO_TOGGLE_URL, { data: { enabled: false } });
    }
  } catch {
    // If the testing routes aren't mounted (production build) the
    // wizard's demo path can't run anyway, so we simply skip cleanup.
  }
}
