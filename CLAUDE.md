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
./start.sh prod                                        # Prod: build frontend, serve everything from backend on :8080 (won't clash with a running dev backend)
./start.sh remote                                      # Tailscale: binds 0.0.0.0 with tailnet CORS (:8001 / :5174)
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
- **Data Flow:** `frontend/src/components/dataflow/dataFlowData.ts` — comprehensive map of all features and how data flows through the system (sources → ingestion → processing → storage → management → analytics → frontend). Read this for a quick overview of the entire application.

## Key Conventions

- **Transaction amounts:** negative = expense, positive = income or refund
- **Non-expense categories:** Ignore, Salary, Other Income, Investments, Liabilities
- **Service names:** frontend/API use plural (`banks`, `credit_cards`, `cash`, `manual_investments`) — the `Services` enum in `backend/constants/providers.py` is canonical; table names may differ (`credit_card_transactions` table vs `credit_cards` service)
- **Tags stored in budgets:** semicolon-separated (`"tag1;tag2;tag3"`)
- **Budget kinds:** three kinds — monthly, yearly, project — discriminated by `budget_rules.period_type` (explicit column, not inferred from nulls). Yearly rules are per-year category/tag envelopes, mutually exclusive with monthly rules on the same (category, tag) within a year. Demo DB backfills `period_type` in `backend/demo_setup.py`.
- **Project ↔ monthly/yearly category exclusion:** a category can't be both project-owned and used by a monthly/yearly rule — the new-project category picker (`GET /budget/projects/available`) filters out any category already claimed by a monthly/yearly rule, and monthly/yearly rule creation blocks categories already claimed by a project. Existing overlaps (e.g. from data predating this rule) surface via `GET /budget/category-conflicts` as a chip in the Budget page's `BudgetNoticeLine` — non-blocking, dismissible.
- **Tagging rules:** priority DESC, first match wins
- **Split transactions:** original stays in main table, splits in `split_transactions`, merged in service layer
- **Savings goals:** a goal is a **virtual earmark** over money already in tracked accounts — never added to net worth. Progress is derived, not typed: each month's realized surplus (`income - expenses - investments`, CC-deduped) flows down goals by `priority`, each taking up to `min(remaining need, monthly_cap)`. Linked transactions are pulled out of the surplus and reintroduced explicitly (a *contribution* consumes the pool; a *utilization* draws the goal down without ever reducing its target), so no shekel counts twice. Allocations persist per `(goal, month)`; priority changes apply forward and rewriting history is an explicit previewed `rebuild`. Closed goals are frozen — their allocations can never be reclaimed. Full rules: `.claude/rules/savings_goals.md`
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

- **Service worker:** generated by `vite-plugin-pwa` (`generateSW` mode — config in `frontend/vite.config.ts`, there is no `src/sw.ts`). Runtime-caches `/api` GETs (NetworkFirst, 4 s timeout); excludes `/api/credentials/*`, `/api/scraping/*`, `/api/backups` and more (see the `urlPattern` filter).
- **Query persistence:** `frontend/src/queryClient.ts` — `idb-keyval` async persister + global `MutationCache.onSuccess` debounced invalidator (200 ms). Bump `PERSIST_BUSTER` when API response shapes change.
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
- **API access control** (`backend/utils/auth.py` + middlewares in `main.py`): every request needs an allowlisted `Host` header (DNS-rebinding guard; extend via `ALLOWED_HOSTS` env, `*` disables); non-loopback clients need `Authorization: Bearer <token>` on `/api/*` (token from `FAD_API_TOKEN` or `~/.finance-analysis/api_token`; frontend picks it up once via `?apiToken=` URL param). `./start.sh prod` now binds 127.0.0.1 — expose with `BIND_HOST=0.0.0.0`, which auto-generates the token and prints the tokenized URL
- **CSRF guard** (`auth.origin_allowed` + `enforce_same_origin_for_writes` in `main.py`): loopback trust means any site the user visits can reach the API from their browser, and CORS only blocks *reading* the reply — a cross-origin `POST` still executes, and a body sent with **no `Content-Type`** (a `Blob` with an empty type) is parsed by FastAPI as JSON, dodging the preflight `application/json` would have forced. So `POST/PUT/PATCH/DELETE` on `/api/*` require a same-site `Origin`, or none at all (curl / the desktop app / Playwright's request context send none). Adding a route needs no extra work; just don't reintroduce a browser-reachable write that bypasses `/api/`
- SQLite uses `NullPool` and `check_same_thread=False` for FastAPI compatibility
- SQLite stores booleans as `0`/`1` integers — in React JSX, `{0 && <Component />}` renders "0". Always use `!!value &&` or `value > 0 &&` for SQLite boolean fields in JSX conditionals
- Frontend `TransactionsTable.tsx` changes require updating all consumers: `Transactions.tsx` and `TransactionCollapsibleList.tsx`
- Scraping has 5-minute timeout and daily rate limit (one scrape per account per day)
- CORS only allows localhost:5173 by default (configurable via `CORS_ORIGINS` env var)
- Closing an investment auto-creates a balance snapshot of 0 on the last transaction date (not the closure date)
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
- **Demo data is no longer rebuilt on every toggle.** `POST
  /api/testing/demo/prepare` is idempotent (builds only when the demo DB is
  absent); `POST /api/testing/demo/reset` forces a rebuild and discards every
  demo-mode change for every client.
- **Vercel serverless (`index.py` → `backend/main.py` lifespan):** the `if os.environ.get("VERCEL"): yield; return` guard MUST stay at the very top of `lifespan`, before any import that transitively pulls in `keyring` (`scraping_service` → `credentials_repository` → `import keyring`). `keyring` is intentionally absent from the Vercel `requirements.txt` (no OS keyring in the sandbox; demo mode never scrapes), so any keyring-backed import placed above the guard crashes cold start with `ModuleNotFoundError: No module named 'keyring'` → the whole function 500s with `FUNCTION_INVOCATION_FAILED` on every route (it fails in lifespan, so it takes down all routes). Regression guard: `tests/backend/unit/test_vercel_lifespan.py`
- **OneZero requires a Cloudflare mTLS client certificate** (since ~2026-08): its API hosts 403 with an "Attention Required" block page before login unless the request presents a client cert. The cert is bundled+shared in the OneZero app (not per-account — generic `O=One Zero` subject, no personal identifiers), so we vendor the extracted PEMs at `scraper/providers/banks/onezero_mtls/` and `OneZeroScraper.initialize()` builds an mTLS httpx client from them. If OneZero scraping starts 403ing, the cert likely rotated or expired (current one valid until 2027-08-05) — re-extract per `.claude/rules/onezero_mtls.md`. The cert is public-by-construction (extractable from the free app), so committing it exposes nothing about any account.
