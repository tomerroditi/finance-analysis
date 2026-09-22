# Finance Analysis Dashboard

Personal finance tracking system for Israeli financial institutions. FastAPI backend + React 19 frontend.

## Commands

```bash
# Backend
poetry run uvicorn backend.main:app --reload          # Dev server (port 8000)
poetry run pytest                                      # All tests
poetry run pytest tests/backend/unit/                  # Unit tests only
poetry run pytest -k "test_budget"                     # By keyword
poetry run pytest <path> --no-cov                     # Targeted run (repo's 40% coverage gate fails small runs without --no-cov)

# Frontend (from frontend/)
npm run dev                                            # Dev server (port 5173)
npm run build                                          # Production build
npm run lint                                           # ESLint

# Both servers
./start.sh                                             # Dev: backend + frontend together (auto-bootstraps venv; BACKEND_PORT / FRONTEND_PORT env to override ports)
./start.sh prod                                        # Prod on :8080: build frontend, serve everything from backend, share it on the tailnet via `tailscale serve`, redeploy new commits (auto-pull is opt-in: `PROD_AUTO_PULL=1`) (.claude/scripts/prod_server.py)
python .claude/scripts/with_server.py -- <command>     # Start both, run command, tear down

# Scaffolding
python .claude/scripts/scaffold_feature.py <name>      # Generate route/service/repo boilerplate

# Scraper
python -m scraper --list                               # List all providers
python -m scraper <provider> --show-browser             # Run scraper with visible browser
```

## Environment Setup (New Clone / Worktree)

`npm run backend` auto-bootstraps the Python venv via `.claude/scripts/bootstrap_venv.sh` if `.venv/` is missing — the first backend start in a fresh worktree takes ~90s, subsequent starts are instant. The script also **re-syncs deps when `poetry.lock` changes**: it stamps the lock's SHA-256 in `.venv/.deps-lock-hash` after each install and runs `poetry install` on the next start if the hash differs (a `git pull` / branch switch / merge that adds a package). The warm-start check is just a single file hash, so up-to-date starts stay instant. This closes the gap where a presence-only check (`.venv/bin/uvicorn` exists) let a venv run with stale deps and crash on a missing import. Frontend deps still install manually:

```bash
cd frontend && npm install
```

**Windows:** `start.sh` and the bootstrap script run under Git Bash and use `.venv/Scripts/` (falling back to the `py -3.12` launcher for venv creation). `npm run backend` does not work there — npm runs scripts through cmd.exe — so use `./start.sh` or the VS Code tasks. Full Windows + macOS setup: `docs/development-setup.md`.

To bootstrap the backend explicitly (without starting it), run the script directly:

```bash
./.claude/scripts/bootstrap_venv.sh
```

Manual equivalent if you'd rather see each step:

```bash
python3.12 -m venv .venv && source .venv/bin/activate && pip install poetry && poetry install --no-root
```

**Why the auto-bootstrap exists:** Git worktrees only contain source files — they don't inherit the parent's `.venv/`, and a missing venv would otherwise break `npm run backend` / `./start.sh` with a cryptic "`.venv/bin/uvicorn`: No such file or directory". The bootstrap script is idempotent (exits silently when `.venv/bin/uvicorn` already exists), so the hot path stays fast.

To run backend tests in a fresh worktree without the ~90s bootstrap, use the main checkout's venv against the worktree source (from the worktree root): `../../../.venv/bin/python -m pytest <path> --no-cov`

User data lives in `~/.finance-analysis/` (SQLite DB at `data.db`). Auto-created on first run. Credentials and categories live in the DB; passwords are stored in the OS Keyring. Default categories ship bundled in `backend/resources/*.yaml` and are seeded into the DB on first run.

## Architecture

```
Routes (FastAPI) -> Services (Business Logic) -> Repositories (Data Access) -> SQLite
```

- **Backend:** `backend/` — FastAPI, SQLAlchemy ORM, Pandas DataFrames
- **Scraper:** `scraper/` — Pure-Python scraper framework (Playwright + httpx), replaces Node.js
- **Frontend:** `frontend/src/` — React 19, Vite, TanStack Query, Zustand, Tailwind CSS 4
- **Tests:** `tests/backend/unit/` — pytest with test classes, docstrings required
- **Rules:** `.claude/rules/` — detailed architecture docs covering services, repos, scraper, frontend (i18n, responsive, PWA/offline cache), testing, retirement/FIRE math (`retirement_calculations.md`), savings-goal allocation (`savings_goals.md`). Each has `paths:` frontmatter and loads automatically when you open a file it covers; `general.md` is always on and indexes the rest
- **Skills:** `.claude/skills/` — `scraper-development` (build a new provider), `demo-data-generation` (regenerate the demo DB), `israeli-salary-knowledge` (payroll/pension/KH reference), `sync-upstream-scraper` (port upstream scraper changes; user-invoked only)
- **Data Flow:** `frontend/src/components/dataflow/` — comprehensive map of all features and how data flows through the system (sources → ingestion → processing → storage → management → analytics → frontend). `dataFlowContent.en.ts` carries the prose and is the file to read for a quick overview of the entire application; `dataFlowData.ts` holds only the structure (which nodes exist, what connects to what) and `dataFlowContent.he.ts` mirrors the English. Adding a node means touching all three — `dataFlowContent.test.ts` fails if they drift, because nothing at runtime does (a node missing from a locale silently renders its raw id).

## Key Conventions

- **Transaction amounts:** negative = expense, positive = income or refund
- **Non-expense categories:** Ignore, Salary, Other Income, Investments, Liabilities
- **Service names:** frontend/API use plural (`banks`, `credit_cards`, `cash`, `manual_investments`) — the `Services` enum in `backend/constants/providers.py` is canonical; table names may differ (`credit_card_transactions` table vs `credit_cards` service)
- **Tags stored in budgets:** semicolon-separated (`"tag1;tag2;tag3"`)
- **Budget kinds:** three kinds — monthly, yearly, project — discriminated by `budget_rules.period_type` (explicit column, not inferred from nulls). Yearly rules are per-year category/tag envelopes, mutually exclusive with monthly rules on the same (category, tag) within a year. Demo DB backfills `period_type` in `backend/demo_setup.py`.
- **Closed projects:** a finished project is *closed*, not deleted — `PUT /budget/projects/{name}/closed` flags every one of its rules (`budget_rules.is_closed`, project rules only; any flagged rule closes the project, so a tag rule minted later can't reopen it). It keeps its rules, its transactions and its own tab, and `GET /budget/projects` still lists it (so its category stays claimed — deleting is what frees a category). What it loses is the Overview: `get_overview` drops it from `long_envelopes`, which is what both the project-envelope list and the needs-attention rows are built from. Its spend still counts in `projects_month_spent` / `total_out` — that money did leave the accounts. `GET /budget/projects/status` pairs every project with its flag in one read.
- **Closed yearly envelopes:** a settled annual commitment is *closed*, not deleted — `PUT /budget/yearly/rules/{id}/closed` flags that one rule (`budget_rules.is_closed`, scoped to `period_type='yearly'` so a monthly/project id is 404 there). It keeps its limit, its spend and its row in the Yearly tab, and it goes on claiming its `(category, tag)` against monthly rules — a closed envelope's spend must never fall back into the monthly pool. What it loses is the Overview (`get_overview` drops it from `long_envelopes`, and with it the needs-attention rows) and its yearly alerts; its spend still counts in `yearly_month_spent` / `total_out`. The year's `summary` keeps closed rules in `total_allocated`/`total_spent` but counts them apart in `closed`, out of `on_track`/`over`/`biggest_overspend`. Carrying rules into the next year always copies them open.
- **Project ↔ monthly/yearly category exclusion:** a category can't be both project-owned and used by a monthly/yearly rule — the new-project category picker (`GET /budget/projects/available`) filters out any category already claimed by a monthly/yearly rule, and monthly/yearly rule creation blocks categories already claimed by a project. Existing overlaps (e.g. from data predating this rule) surface via `GET /budget/category-conflicts` as a chip in the Budget page's `BudgetNoticeLine` — non-blocking, dismissible.
- **Tagging rules:** no priority column — rules run in creation order (`id` ASC), first match wins; overlapping rules that would assign different category/tag pairs are rejected at creation by conflict detection. `apply?overwrite=true` resets every matching transaction (hand-tagged included — the tables don't record who set a tag)
- **Split transactions:** original stays in main table, splits in `split_transactions`, merged in service layer
- **Savings goals:** a goal is a **virtual earmark** over money already in tracked accounts — never added to net worth. Progress is derived, not typed: each month's realized surplus (`income - expenses - investments`, CC-deduped) flows down goals by `priority`, each taking up to `min(remaining need, monthly_cap)`. Linked transactions are pulled out of the surplus and reintroduced explicitly (a *contribution* consumes the pool; a *utilization* draws the goal down without ever reducing its target), so no shekel counts twice. What no goal claims stays in the **free-cash pool** (`GET /savings-goals/free-cash`) — the tracked liquid money that is not earmarked. A month that spends more than it earns drains that pool first; only once it is empty does the shortfall come back out of the goals, **lowest priority first**, each giving back at most `funded - utilized` (money already spent can never be reclaimed) as a negative allocation row. A goal can also be **backed by an investment** the user means to liquidate (`savings_goal_investments`, valued live off the holding): it counts toward `funded` and shrinks what the goal needs from surplus, but it is not cash — never in the free-cash pool, never clawed back, and reported separately as `investment_backed`. Allocations persist per `(goal, month)`; priority changes apply forward and rewriting history is an explicit previewed `rebuild`. Closed goals are frozen — their allocations can never be reclaimed or clawed back. The dashboard card left beta and is default-visible as of dashboard layout `v5`, whose migration un-hides it for layouts that only hid it under the beta policy (`useDashboardLayout.ts`); it reads its month-by-month panel from `GET /savings-goals/timeline`. That panel is **collapsed by default** (and fetches nothing until opened), its bars stack the free-cash pool on top of each month's per-goal funding, and its **legend is clickable** — click to hide a series, double-click to isolate one, with the y-axis refitting to what is left. The goal list itself **scrolls in place** past ~26rem, but only once the cap hides about a row: an always-on cap swallows the page's scroll on a phone (`useScrollCap`; `.claude/rules/frontend_pitfalls.md` → "Capped Scroll Regions"). Full rules: `.claude/rules/savings_goals.md`
- **Recurring-charge classification:** a candidate must land in one of five non-overlapping cadence bands (monthly / bimonthly / quarterly / semiannual / annual — each with its own tight tolerance, so a gap between two bands is *not* a cadence; **nothing below a month is a cadence** — weekly and fortnightly rhythms only ever matched habits, not billing), clear the interval-regularity gate (`_MAX_INTERVAL_MAD_CV = 0.15`, a robust median-absolute-deviation spread measured against the demo history: every genuine commitment scores ≤ 0.133, the tightest ordinary shopping 0.208), and qualify on one of two amount paths — `fixed` (≥75% of charges within ±15%) or `metered` (a consumption bill: ±50%, but needing a tighter schedule and ≥6 sightings, because a varying amount is no evidence). Day-of-month anchoring only scores a candidate, never rejects one (real bills slip 5–6 days around weekends and month ends). Every candidate carries a `confidence` (0..1 over regularity, interval shape, day anchoring, amount stability and evidence count) that ranks the review list, and an `amount_kind`.
- **Recurring charges are confirmed, not assumed:** `RecurringService` only *detects* candidates. Each candidate carries a `confirmation` of `pending` / `confirmed` / `dismissed`, stored per normalized merchant key in `recurring_decisions`. Only **confirmed** items are acted on — the budget Overview's fixed/variable split and `committed_remaining`, the forecast's safe-to-spend, and the `newRecurring` / `priceIncrease` insight cards all read `get_confirmed_items()`. `get_recurring()` returns everything (dismissed only with `include_dismissed=True`) so the dashboard can ask. Verdicts are set through `POST /analytics/recurring/decisions`; `pending` undoes one. A verdict survives new charges, re-detection and amount drift because it is keyed by the same normalized label detection groups on. **Writing a verdict runs no detection at all.** `set_decisions` is a pure write: it validates the decision value and the key, then applies the whole batch in one commit. It deliberately does *not* check the key against a fresh detection — that cost a full pass per verdict, on a cache its own previous commit had just discarded, and was wrong on its own terms: a verdict is keyed by the normalized label precisely so it can outlive detection, so a key detection does not produce *today* is the case the design is for, not an error. Rejecting it turned a slightly stale list in the browser into a 404, which the card showed as the verdict springing back to "needs review". `label` / `amount` / `cadence` are stored for audit, read by nothing, and sent by the client that already has them on screen. The card patches its own cached summary from the verdict (`recurringOptimistic.ts`) so the row moves on click instead of after the dashboard-wide refetch, and **ended charges are hidden behind a "show ended" toggle** — they are already out of `total_monthly` and committed spend, so they are history rather than commitments. No verdict is final: "show dismissed" lists what was ruled out with its amount and cadence and restores it to review, and a confirmed charge can be sent back to review or dismissed outright. The card left beta and is default-visible as of dashboard layout `v4`, whose migration un-hides it for layouts that only hid it under the beta policy (`useDashboardLayout.ts`).
- **Insight cards are unexplained *and* material:** the dashboard strip (`InsightsService`) only surfaces what the budget does not already account for. Spend in a **project** category (planned lumpy spending) or a **yearly** envelope (lumpy by design) never becomes a `categorySpike` or a `largeTransaction`, a category still inside its **monthly** budget is not a spike either, and a **confirmed recurring** charge is never a large-charge surprise (rent is big every month). A spike's baseline is the **median** of the last 3 months and the category must appear in at least 2 of them — no trend, no deviation. A large charge must also be a record for **its own category** over the trailing 6 months, and is dropped when a spike already covers that category (one event, one card). Every floor scales with the household: shekel minimums are `max(absolute, share of typical monthly outflow)`, and the pace card ignores a gap under 5% of expected income or one a running project accounts for. Cards sort by severity, then by the size of the money involved, capped at 6. Each card carries a stable `key` and can be **dismissed** (`POST /analytics/insights/dismiss`, stored in `insight_dismissals`, undone by `.../restore`). The key encodes what the card is *about* — a month for the running-month cards, a `source`+`unique_id` for a large charge, a merchant and price for a repriced subscription — so a dismissal lapses exactly when that changes, and filtering happens *before* each rule's cap so a dismissal frees its slot for the runner-up. Finally, the strip carries only what no other card says: `InsightsStrip` drops the pace cards while the `forecast` card is visible and the recurring cards while the `recurring` card is, since which cards are on screen is a browser-local layout preference the backend cannot see.
- **Retirement calculator:** all-real-terms model (today's shekels; nominal return converted via inflation). Scraped Keren Hishtalmut policies are auto-synced into `type='hishtalmut'` investments (with scraped snapshots) and are therefore **already inside tracked net worth** — retirement math swaps them out via `status["tracked_kh_value"]` before adding the goal's KH bucket, so KH counts exactly once for both scraped and typed-only users. Full rules: `.claude/rules/retirement_calculations.md`

## Code Style

- Python: type hints, NumPy-style docstrings
- TypeScript: strict mode, no unused locals/parameters
- Tests: always use test classes, every test needs a docstring
- No business logic in routes or components — services handle all logic
- No direct DB access outside repositories
- No raw axios calls in components — go through `frontend/src/services/api.ts`
- No obvious comments, no dead code
- Commits: Conventional Commits (Commitizen)

## Branch & PR Workflow

- **PRs target `main`.** Feature branches branch off `main` and merge back into `main`. CI on a PR to `main` runs backend pytest, frontend lint/build/vitest, **the full 4-shard Playwright e2e suite**, and the Schemathesis API-fuzz job. The merge triggers `release.yml`: commitizen bumps the version and builds the Windows installer + GitHub release. macOS bundles are no longer built in CI — see `.claude/rules/installation_and_updates.md`.
- Use a Conventional Commits subject on the merge — it drives the Commitizen version bump, and every feature merge now cuts a release.
- **`dev` is dormant, not the default target.** The repo used to stage feature branches on `dev` and ship via `dev → main` release merges; that stopped being practised around 2026-07 and `dev` has since fallen far behind `main`. Don't branch from it or target it. `ci.yml` still gates the e2e job on `dev` as well as `main`, so the old flow would work if revived — but revive it deliberately, don't drift back into it. See `.claude/rules/ci_and_release.md`.

## Pre-PR Checklist

Run these locally and get them **all green before opening a PR** — CI runs the same checks and a red PR wastes a round-trip. Run from the repo root unless noted. See `.claude/rules/ci_and_release.md` (CI parity) and `.claude/rules/testing.md` (e2e details).

```bash
# 1. Backend tests (full suite — matches CI's `poetry run pytest`)
poetry run pytest

# 2. Frontend lint + type-check/build + unit tests (matches CI). NOTE: this
#    does not type-check frontend/e2e/ — tsconfig.app.json includes only
#    `src` and tsconfig.node.json only `vite.config.ts`, and ESLint here
#    isn't type-aware. e2e type errors surface only when Playwright runs
#    the spec (step 3).
cd frontend && npm run lint && npm run build && npm test && cd ..

# 3. Frontend e2e (Playwright). Prefer the isolated runner on a multi-core box:
#    it starts its own servers, so no with_server.py wrapper.
cd frontend && npm run test:e2e:isolated && cd ..

# Serial fallback (single core, or debugging a cross-spec ordering problem).
# Needs BOTH servers up, hence the orchestrator.
python .claude/scripts/with_server.py -- bash -c \
  "cd frontend && npm run test:e2e"
```

**e2e projects & parallelism.** Demo Mode itself is per-client (declared via
the `X-FAD-Demo` header, sourced from each browser's `fad_demo_mode`
localStorage flag) — but the demo **database file** is still process-global:
every client that sends the header reads and writes the same on-disk demo DB.
That's why the suite is still organized into Playwright projects sequenced by
a shared setup: `demo-setup` builds the demo DB file **once** (via
`enableDemoMode`'s idempotent `POST /api/testing/demo/prepare` call),
`read-only` holds write-free specs, `mutating` holds the rest — **and every
mutating spec must call `resetDemoData()` in its own `beforeAll`** to get
pristine data for the file. That reset is load-bearing and easy to forget:
`enableDemoMode(page)` only seeds a browser's localStorage flag, and
`demo/prepare` is idempotent, so nothing else rebuilds the shared demo DB
between files. Omit it and a predecessor's writes leak into your assertions
(this is exactly how `transactions.spec.ts`'s bulk-eraser test started
failing only when run after its siblings). A rebuild is ~22 ms — under a
second across the whole project. Finally,
`demo-teardown` rebuilds the demo DB from its frozen snapshot at the end
(`POST /api/testing/demo/reset`) so it's pristine for the next run. read-only
and mutating are both plain, shardable projects (CI runs `playwright test
--shard=X/4`); each spec self-heals its own browser's Demo Mode flag in its
own `beforeAll`, so any order or per-shard interleaving is safe.

**`playwright.config.ts` is serial (`workers: 1`, `fullyParallel: false`)** —
that is a correctness constraint (the shared demo DB), not a tuning choice, and
it is why a plain `npm run test:e2e` takes **~4 min for ~99 tests on a 12-core
Mac**: the average test is only ~2.4 s, but nothing overlaps. Reach for
`npm run test:e2e:isolated` (below) rather than raising `workers`.

The `read-only` project *can* fan
out across workers (`npm run test:e2e:parallel`), but profiling (in the Plotly
era — charts are now lightweight Recharts SVG, so re-profile before relying on
these numbers) showed the suite is **CPU-bound on browser-side chart
rendering** (the backend answers in <1 s; a demo-DB rebuild is ~0.08 s). On a
resource-constrained box (e.g. the web sandbox, 4 cores) two concurrent
Chromium instances rendering charts saturated the CPU, so parallel came in
*slower* than serial (~7.3–8.4 m vs ~6.0 m) with flaky timeouts. Parallel
helps only where the CPU has spare cores; broad speedup needs per-worker
isolated backends. Keep the default serial. **A spec
may only join the `READ_ONLY_SPECS` list in `playwright.config.ts` if it
performs zero backend writes** — one writing spec there corrupts every parallel
sibling. Add a write to a listed spec? Move it out of the list in the same
change.

**True parallel speedup on multi-core dev boxes: `npm run test:e2e:isolated`**
(`.claude/scripts/e2e_parallel_isolated.py`). It starts N isolated
(backend + frontend) pairs — each its own port + `FAD_USER_DIR` demo DB — and
runs `--shard=i/N` once per pair, pinned via `BASE_URL` + `E2E_API_BASE`. No
shared DB → no cross-shard races → every shard runs concurrently.

**Measured 2026-09-05 on a 12-core M-series Mac (8P+4E): 72 s for 4 shards vs
~240 s serial — 3.3×.** This is the local default in the checklist above; CI
keeps its single-backend `--shard=X/4` matrix.

**The runner only ever drives servers it started.** A shard pinned to a
leftover server from a previous run silently tests *that* checkout's source —
specs fail here and pass in isolation, which is exactly how a stale frontend on
:5273 once broke a `toHaveCount(0)` assertion for a DOM node the current source
no longer renders. Four guards keep ownership honest: children run in their own
process group (`start_new_session`) and are torn down with `killpg`, so
`npm run dev`'s `vite` child cannot survive its npm parent; **ports are
allocated, not assumed** — 8100/5273 are only where the search starts
(`--backend-port-base` / `--frontend-port-base`, or `E2E_BACKEND_PORT_BASE` /
`E2E_FRONTEND_PORT_BASE`), and the allocator walks up to the first port it can
*bind*, naming who held the one it skipped, so **several worktrees can run the
suite at once**; Vite is launched with `--strictPort`, so a taken port is a
hard exit rather than a silent fall-forward to 5277+, and a server that loses
the probe-to-bind race is retried on fresh ports; and readiness means *our*
server answered — the backend must have created `data.db` inside that shard's
`FAD_USER_DIR`, which a squatter cannot fake. Server stdout/stderr go to
`$TMPDIR/e2e-isolated-<worktree>-<hash>/{backend,frontend}-N.log`, never
`/dev/null`, so a bind failure is readable — that directory is keyed per
checkout so concurrent runs cannot clobber each other's JSON reports, which
feed the committed timings file. If a run is `kill -9`'d, its orphans survive
and later runs simply allocate around them; `--reclaim-ports` kills the
holders of the preferred ports, so use it only when you know they are yours
and not a neighbouring worktree's live run.

The runner does **not** use Playwright's `--shard`, which splits by test count
and left one shard at 31 s beside another at 1.5 m — the slowest sets the wall
clock, so a third of the parallelism was idle. It packs spec files by recorded
duration instead (longest-first greedy), passing each shard an explicit file
list; every shard now lands within a few seconds of the others. Each run
rewrites `.claude/scripts/e2e_shard_timings.json`, which is **committed on
purpose**: absolute times are machine-specific but the ratios are not, so a
fresh clone gets balanced shards on its first run. A new spec with no recorded
time is assumed to take the median. The timings are only rewritten when a run
measured ≥80 % of the suite, so a `--grep` cannot shrink the table; forwarding
a positional filter falls back to `--shard`. Because each shard is given
explicit files, `demo.setup.ts` and `demo.teardown.ts` must be in every
shard's list — their projects match nothing otherwise and Demo Mode is never
enabled. Every direct-to-backend
API call in a spec must go through the env-driven `API_BASE` exported from
`frontend/e2e/helpers.ts` (never hardcode `http://localhost:8000`) or that call
will hit the wrong shard's backend.

**Avoid redundant `waitForLoadState("networkidle")`.** It waits for every
straggler request + 500 ms quiet (~2 s of dead time warm, more cold), but
Playwright's `expect().toBeVisible()`/`.click()`/`.fill()`/`.waitFor()` already
auto-wait for the element the test needs. Drop the `networkidle` — *unless* the
test then does a genuinely non-waiting read (`.count()`, `.all()`,
`.isVisible()`, `evaluateAll()`, `page.evaluate()`) or a *negative* assertion
(`toHaveCount(0)`), which can race or pass vacuously against an unrendered page.
A locator's `.textContent()`/`.getAttribute()`/`.inputValue()`/`.evaluate()`
*do* auto-wait, so a `networkidle` guarding those is already redundant. Where a
wait is genuinely needed, prefer a positive anchor
(`await expect(target.first()).toBeVisible()`) over `networkidle`; keep
`networkidle` only when zero is a legitimate result. See
`.claude/rules/testing.md`.

- **Run the whole suite, not just the one test you touched.** Backend `pytest` has a 40 % coverage gate — a targeted run needs `--no-cov` (see Commands), but the pre-PR run is the full suite with coverage on.
- **e2e is required, not optional** — `npm test` (vitest) and e2e (`playwright test`) are different layers. e2e specs live in `frontend/e2e/` and drive the real UI in Demo Mode; type-checking and unit tests miss the focus-trap / click-outside / query-invalidation bugs UI patches introduce. Every UI patch must add or update an e2e spec (see the CLAUDE.md "UI Testing" section).
- **Adding e2e coverage? Extend the page's journey test, don't add a new `test()`.** Cold page navigations dominate suite runtime (each `test()` pays a fresh ~30 s dashboard/budget boot), so new read-only checks go into the existing single-load journey test as a labeled block. A separate `test()` is only for backend writes, a different pre-boot env (localStorage seed, `page.route()` stubs, `language=he`), or when the journey hits the size cap (~100 lines — don't build mega-tests either). Full decision checklist: `.claude/rules/testing.md` → "Adding a new e2e test".
- **Sandbox (Claude Code on the web) gotcha:** a bare `npx playwright test` fails because the bundled Chromium lags `package.json`. Point Playwright at the installed full-chrome binary via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` — full procedure in `.claude/rules/testing.md` → "Running e2e specs". **Verified green is the only "verified"** — a browser that failed to launch means the spec did not run.
- **Fresh worktree:** the first backend command auto-bootstraps `.venv/` (~90 s); frontend deps need a manual `cd frontend && npm install`. See "Environment Setup" above.
- Use a Conventional Commits subject on the PR merge (drives the Commitizen version bump).

## API

- Base URL: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Frontend proxies `/api/*` to backend via Vite config
- Custom exceptions (`backend/errors.py`, all inherit `AppException`): `EntityNotFoundException` (404), `EntityAlreadyExistsException` (409), `ValidationException` (400), `BadRequestException` (400). Raise them in repositories/services — routes stay free of try/except for domain errors.

## UI Testing

When smoke-testing UI changes in the browser, **enable Demo Mode first** (toggle in Settings — click Settings in the sidebar). Demo Mode is per-client: the toggle only affects the current browser profile (it sets a localStorage flag sent as the `X-FAD-Demo` header), so it switches that browser to a separate demo database with pre-built sample data without touching real financial data or any other client on the same backend. Remember to disable it when done.

**REQUIRED for every UI patch (including small ones):** Drive the actual user
flow with the Playwright MCP before marking the fix resolved, and add an e2e
spec under `frontend/e2e/`. Type-checking and reasoning miss the bugs UI
patches usually contain (focus traps, click-outside handlers, keyboard-induced
reposition, query invalidation remounting). Full procedure in
`.claude/rules/testing.md` → "Verifying UI patches with Playwright" (includes
how to run e2e via `with_server.py` and the Claude-Code-on-the-web Chromium
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` override needed when `npx playwright
install` can't fetch a browser).

## Scraper Framework

The `scraper/` package at the project root is a pure-Python scraper framework using Playwright and httpx, replacing the old Node.js integration. It provides:

- **19 provider scrapers** (12 banks + 6 credit cards + 1 insurance) in `scraper/providers/`
- **Base classes:** `BrowserScraper` (Playwright lifecycle + form login; its `fetch_get`/`fetch_post` run inside the page context so they carry session cookies), `ApiScraper` (httpx only, no browser)
- **Backend integration:** `backend/scraper/adapter.py` bridges async scrapers to the sync pipeline
- **Demo mode:** Automatically redirects to dummy scrapers that generate fake data
- **Adding a new provider:** use the `scraper-development` skill (read-only live-site exploration, then codegen). Manually: create a class in `scraper/providers/banks/` or `credit_cards/`, register in `scraper/models/credentials.py` PROVIDER_CONFIGS, and export in the `__init__.py`
- **Import caveat:** `backend/scraper/` and root `scraper/` share a name. Backend code uses `_import_scraper_module()` helper (in `adapter.py`) to resolve root package. Test dirs use `test_scraper/` prefix to avoid pytest collision.

## PWA / Offline Cache

The frontend ships as a PWA — service worker precaches the build, persists the React Query cache to IndexedDB, and shows toasts for SW lifecycle events.

- **Service worker:** generated by `vite-plugin-pwa` (`generateSW` mode — config in `frontend/vite.config.ts`, there is no `src/sw.ts`). Runtime-caches `/api` GETs (NetworkFirst, 30 s network timeout); excludes `/api/credentials/*`, `/api/scraping/*`, `/api/backups` and more (see the `urlPattern` filter). **The timeout is not what makes offline work** — NetworkFirst falls back the moment a request *errors*; it only bounds a connection that is up and silent, so it must sit above any plausible backend recompute. At its old 4 s it read "the server is still computing" as "the network is down": every derived analytics read passes 4 s on a real database, and *always* does right after a write (the commit discards `data_cache`, so the next read pays the full recompute), so the refetch following a write was answered with the body from *before* it — confirming a recurring charge put it back in "needs review" seconds later, permanently. Guard: `frontend/src/serviceWorkerCaching.test.ts`.
- **Query persistence:** `frontend/src/queryClient.ts` — `idb-keyval` async persister + the app-wide mutation cache from `queryInvalidation.ts`. Bump `PERSIST_BUSTER` when API response shapes change.
- **Every write cancels the reads that predate it.** The mutation cache's `onMutate` drops any query already fetching *and already holding data*, then sweeps 200 ms after the write settles. A read in flight when a write starts was computed against the pre-write state, and React Query only supersedes an older fetch with a newer *fetch* — a `setQueryData` patch is not a fetch, so without this the older response lands on top and restores what the user just changed. A query with no data yet is left alone (nothing to overwrite, and cancelling it would restart a page's first load). The sweep is on `onSettled`, not `onSuccess`, so a failed write still re-issues what it cancelled. Guard: `frontend/src/queryInvalidation.test.ts`.
- **When adding endpoints:** decide if the response is sensitive / real-time / normal and update both the SW URL filter AND the persister `shouldDehydrateQuery` rule. Never one without the other.
- **Detailed rules:** `.claude/rules/frontend_pwa.md`

## Internationalization (Hebrew/English)

- **Bilingual UI:** Full Hebrew + English support via `i18next` / `react-i18next`
- **RTL:** Automatic direction switching. Use Tailwind CSS 4 logical properties (`ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start`, etc.) instead of physical `left`/`right`
- **All user-visible strings** must use `t("section.key")` — no hardcoded text. Add keys to both `en.json` and `he.json`
- **Numbers in RTL:** Wrap with `dir="ltr"` inside translated text
- **Detailed rules:** `.claude/rules/frontend_i18n.md`

## Gotchas

- **Provider policy IDs are display strings, not stable keys** — HaPhoenix restyled the parenthesised internal ID it appends to Keren Hishtalmut policy numbers (`007-916-407357 (8296857)` → `(08296857)`) in 2026-09 without any account changing. That string is the identity key for `insurance_accounts.policy_id`, `investments.insurance_policy_id`, the investment tag and the `"<policy>_<date>_<amount>"` transaction dedup key, so exact-string matching forked a duplicate account, a duplicate investment (double-counting KH in net worth) and the whole deposit history. Run any incoming policy ID through `scraper/utils/policy_ids.py`: `normalize_policy_id` for what you persist, `policy_id_key` for matching. Never rewrite a stored policy ID after creation — other tables join on that exact string
- **`unique_id` is a per-table auto-increment** — bank #5 and credit-card #5 are different transactions. Never key merged/cross-table data by bare `unique_id`; always pair it with the table (`source` / `source_table`). See `.claude/rules/backend_repositories.md` → "unique_id Is Per-Table"
- Passwords stored in OS Keyring, never in YAML or code. Non-sensitive credential fields (usernames, ID numbers, card digits) are Fernet-encrypted in the DB (`backend/utils/crypto.py`, key in the OS Keyring); the legacy `credentials.yaml` is deleted on startup after migration. All keyring access goes through `backend/utils/keyring_store.py` — never import `keyring` directly elsewhere
- Insecure keyring backends (null/plaintext) are rejected on credential writes — CI/sandboxes opt in via `PYTHON_KEYRING_BACKEND` or `FAD_ALLOW_INSECURE_KEYRING=1`
- **API access control** (`backend/utils/auth.py` + middlewares in `main.py`): every request needs an allowlisted `Host` header (DNS-rebinding guard; extend via `ALLOWED_HOSTS` env, `*` disables the Host check only — never the CSRF Origin check); non-loopback clients — and loopback requests a local reverse proxy relayed (any `X-Forwarded-*` / `Forwarded` / `X-Real-IP` / `Via` / `CF-Connecting-IP` / `True-Client-IP` / `Tailscale-User-Login` header; raw TCP forwarders like `ssh -L` are undetectable, so never use one) — need `Authorization: Bearer <token>` on `/api/*`, except a `tailscale serve`-relayed request whose `Tailscale-User-Login` is in `TAILNET_ALLOWED_USERS` **and that arrived on the `TAILNET_INGRESS_PORT` listener** (`./start.sh prod` sets both — the owner's login, and a second loopback port that `.claude/scripts/serve_app.py` opens and only `tailscale serve` targets, so another local proxy can't relay a forged identity — and runs uvicorn with proxy headers off so the peer stays loopback) (token from `FAD_API_TOKEN` or `~/.finance-analysis/api_token`; frontend picks it up once via `?apiToken=` URL param). `./start.sh prod` now binds 127.0.0.1 — expose with `BIND_HOST=0.0.0.0`, which auto-generates the token and prints the tokenized URL
- **CSRF guard** (`auth.origin_allowed` + `enforce_same_origin_for_writes` in `main.py`): loopback trust means any site the user visits can reach the API from their browser, and CORS only blocks *reading* the reply — a cross-origin `POST` still executes, and a body sent with **no `Content-Type`** (a `Blob` with an empty type) is parsed by FastAPI as JSON, dodging the preflight `application/json` would have forced. So `POST/PUT/PATCH/DELETE` on `/api/*` require a same-site `Origin`, or none at all (curl / the desktop app / Playwright's request context send none). Adding a route needs no extra work; just don't reintroduce a browser-reachable write that bypasses `/api/`
- **Dev server loop on Windows (`--loop backend.utils.event_loop:reload_loop_factory`):** under `--reload`, uvicorn runs the server on a `select()`-based `SelectorEventLoop`, and a burst of sockets (several scrapes plus status polling) used to kill the worker with `WinError 10055` or `too many file descriptors in select()`. The factory keeps the Selector loop but swaps in a selector that backs off on buffer exhaustion and polls above 512 fds. Don't switch it to a `ProactorEventLoop`: the reloader shares one listening socket across workers, a socket can join only one IOCP, and the first reload's worker then fails every accept with `WinError 87`. `./start.sh` (dev), `npm run backend` and the VS Code Backend task pass the flag; `./start.sh prod` (`prod_server.py`) and the packaged app run without `--reload`, so uvicorn already gives them a Proactor loop. Proactor has its own failure mode: one failed accept (same `WinError 10055`) makes asyncio close the listening socket for good, leaving a live process that serves nothing — so `prod_server.py` probes `/health` every 10 s and restarts uvicorn after 3 consecutive misses, not only when the process exits
- SQLite uses `NullPool` and `check_same_thread=False` for FastAPI compatibility
- SQLite stores booleans as `0`/`1` integers — in React JSX, `{0 && <Component />}` renders "0". Always use `!!value &&` or `value > 0 &&` for SQLite boolean fields in JSX conditionals
- Frontend `TransactionsTable.tsx` changes require updating all consumers: `Transactions.tsx` and `TransactionCollapsibleList.tsx`
- Scraping has a 5-minute timeout per run and no automatic retry; there is no daily rate limit (the `scraping_history` watermark only shapes the next window)
- CORS only allows localhost:5173 by default, and nothing at all under `ENVIRONMENT=production` (prod serves its SPA same-origin; configurable via `CORS_ORIGINS` env var). `npm run dev -- --host` exposes the whole API to the LAN without a token (the Vite proxy relays from loopback with no proxy headers) — don't
- Closing an investment auto-creates a balance snapshot of 0 (`source="closed"`) on the last transaction date (not the closure date), and that zero **follows later transactions**: every write path that can add, re-date or retag transactions must call `TransactionsService.realign_closed_investments()`, or a withdrawal landing after the close is carried past the zero and values the closed fund below zero in net worth. See `.claude/rules/kpi_calculations.md` → "The closing zero follows later transactions"
- Investment balance snapshots override transaction-based balance when present (snapshot-first, transaction fallback)
- Alembic migrations run on startup (`backend/main.py` → `alembic upgrade head`) AFTER `Base.metadata.create_all` — they must be idempotent (fresh DBs already have current-model tables), set `down_revision` to the current head, and use `op.batch_alter_table(..., recreate="always")` to drop SQLite constraints/columns
- **Demo Mode is per-client, not per-process.** A client declares it with the
  `X-FAD-Demo: 1` request header; the frontend stores the flag in
  localStorage (`fad_demo_mode`) and sends it from the axios interceptor. The
  backend keeps zero per-client state — a middleware in `main.py` binds the
  header to a `ContextVar`, and `AppConfig.is_demo_mode` reads it. Two
  clients on one backend can therefore browse different databases at once.
  Absent or malformed header means real mode.
- **Two demo clients still share one demo database.** Per-client *mode*
  isolation is not per-client *data* isolation; shared-backend Playwright
  shards still need `e2e_parallel_isolated.py`.
- **`ContextVar` does not cross the TestClient portal thread.** In a backend
  test, put a request into demo mode with the header
  (`headers={"X-FAD-Demo": "1"}`), or pin the whole process with
  `AppConfig._forced_mode = True` and restore it in teardown. Calling
  `set_demo_mode()` and then issuing a `test_client` request does nothing.
- **A demo DB built by an older version keeps that version's schema.** Startup migrations (`create_all` + `alembic upgrade`) only ever run against the database the process opened — the real one — and `POST /api/testing/demo/prepare` deliberately does not rebuild an existing demo DB. So a table or column added since a user last rebuilt their demo database would otherwise never appear there, and every read of it answers 500 in demo mode only. `prepare` now runs `Base.metadata.create_all` + `sync_missing_columns` against the demo engine on every call; it is additive, so the demo data survives.
- **Demo data is no longer rebuilt on every toggle.** `POST
  /api/testing/demo/prepare` is idempotent (builds only when the demo DB is
  absent); `POST /api/testing/demo/reset` forces a rebuild and discards every
  demo-mode change for every client.
- **Vercel serverless (`index.py` → `backend/main.py` lifespan):** the `if os.environ.get("VERCEL"): yield; return` guard MUST stay at the very top of `lifespan`, before any import that transitively pulls in `keyring` (`scraping_service` → `credentials_repository` → `import keyring`). `keyring` is intentionally absent from the Vercel `requirements.txt` (no OS keyring in the sandbox; demo mode never scrapes), so any keyring-backed import placed above the guard crashes cold start with `ModuleNotFoundError: No module named 'keyring'` → the whole function 500s with `FUNCTION_INVOCATION_FAILED` on every route (it fails in lifespan, so it takes down all routes). Regression guard: `tests/backend/unit/test_vercel_lifespan.py`
- **Vercel demo sandboxes are per-visitor and Blob-backed.** `index.py` sets `FAD_DEMO_SESSIONS=1`; the frontend sends a per-browser `X-FAD-Demo-Session` id on every request and the middleware routes demo requests to `demo_env/sessions/<id>/demo_data.db`, revalidating against Vercel Blob on every request and mirroring the whole file back after each successful write. **`BLOB_READ_WRITE_TOKEN` is required on Vercel**: without it sandboxes are instance-local, a write on one instance is invisible to reads on another, and the layout shows the amber "Demo changes are not being saved" notice (`DemoSandboxNotice`). `GET /api/testing/demo_mode_status` → `blob_configured` tells you with one curl whether the token reached the function. `vercel.json` sets `"fluid": true` so one warm instance serves a visitor's whole burst. Never enable `FAD_DEMO_SESSIONS` locally or under Playwright — the e2e suite depends on one shared demo file. Full rules: `.claude/rules/vercel_demo.md`
- **OneZero requires a Cloudflare mTLS client certificate** (since ~2026-08): its API hosts 403 with an "Attention Required" block page before login unless the request presents a client cert. The cert is bundled+shared in the OneZero app (not per-account — generic `O=One Zero` subject, no personal identifiers), so we vendor the extracted PEMs at `scraper/providers/banks/onezero_mtls/` and `OneZeroScraper.initialize()` builds an mTLS httpx client from them. If OneZero scraping starts 403ing, the cert likely rotated or expired (current one valid until 2027-08-05) — re-extract per `.claude/rules/onezero_mtls.md`. The cert is public-by-construction (extractable from the free app), so committing it exposes nothing about any account.
