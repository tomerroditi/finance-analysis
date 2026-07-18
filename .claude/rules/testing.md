---
paths:
  - "tests/**/*.py"
  - "pytest.ini"
  - "conftest.py"
---

# Testing Standards

**523 tests, 80% backend coverage.** Run with `poetry run pytest --cov=backend`.

```
tests/
├── conftest.py                    # Root: db_engine + db_session (in-memory SQLite)
├── backend/
│   ├── conftest.py                # Seed fixtures (transactions, budgets, tagging rules, etc.)
│   ├── unit/
│   │   ├── test_config.py         # AppConfig singleton tests
│   │   ├── models/                # Per-model ORM tests (one file per model)
│   │   ├── services/              # Service tests (real DB, mock external deps)
│   │   ├── repositories/          # Repository tests (real DB, YAML uses tmp_path)
│   │   ├── utils/                 # Utility function tests
│   │   └── scraper/               # Scraper base class + 2FA tests
│   ├── integration/               # Cross-layer pipelines (tagging, budget, splits)
│   └── routes/
│       ├── conftest.py            # Route-specific: db_engine (StaticPool) + test_client
│       └── test_*_routes.py       # API endpoint tests (happy paths + error paths)
└── frontend/                      # (Planned) Vitest for components
```

## Principles

| Rule | Details |
|------|---------|
| **Framework** | pytest + pytest-cov |
| **Grouping** | Always use test classes to group related tests |
| **Fixtures** | Shared in `conftest.py`, reduce code repetition |
| **Docstrings** | Every test class and function MUST have one |
| **Naming** | `test_<method>_<scenario>_<expected>` |
| **Independence** | Each test is self-contained; no test depends on another |

## Test Class Pattern
```python
class TestClassName:
    """Tests for ClassName functionality."""

    def test_method_does_something(self):
        """Verify method returns expected result."""
        ...
```

## Fixture Architecture

### Root conftest (`tests/conftest.py`)
Provides `db_engine` and `db_session` using in-memory SQLite. All unit/integration tests share this.

### Seed fixtures (`tests/backend/conftest.py`)
Composable, function-scoped seed data — tests pick only what they need:

| Fixture | What it seeds |
|---------|---------------|
| `seed_base_transactions` | ~30 CC/bank/cash transactions across Jan-Mar 2024 |
| `seed_split_transactions` | Parent transactions + split children |
| `seed_prior_wealth_transactions` | Cash, manual investment, bank balances |
| `seed_untagged_transactions` | Transactions with no category/tag (for tagging rule tests) |
| `seed_project_transactions` | Wedding/Renovation project transactions + budget rules |
| `seed_budget_rules` | Monthly budget rules for Jan 2024 |
| `seed_tagging_rules` | Auto-tagging rules (Supermarket, Uber, Netflix) |
| `seed_investments` | Investment records + manual investment transactions |
| `sample_categories_yaml` | Categories-to-tags mapping dict (no DB) |
| `sample_credentials_yaml` | Fake credentials dict (no DB) |

### Route conftest (`tests/backend/routes/conftest.py`)
Overrides `db_engine` with **StaticPool** (required for TestClient sharing the same in-memory DB) and provides `test_client` fixture with dependency overrides.

## Unit Test Patterns

### Service tests (real DB)
Services are tested with a real in-memory DB session + seed fixtures. Mock only external dependencies (Keyring, file I/O).

```python
class TestBudgetServiceValidation:
    """Tests for budget validation edge cases."""

    def test_validate_null_category_rejected(self, db_session, seed_budget_rules):
        """Verify null category triggers validation failure."""
        service = BudgetService(db_session)
        valid, msg = service.validate_rule(category=None, tags=["Groceries"], ...)
        assert not valid
```

### Repository tests (YAML-based repos use tmp_path)
```python
class TestTaggingRepositoryLoad:
    """Tests for loading categories from YAML."""

    def test_load_categories(self, tmp_path):
        """Verify categories loaded from YAML file."""
        yaml_file = tmp_path / "categories.yaml"
        yaml_file.write_text("Food:\n  - Groceries\n")
        repo = TaggingRepository(categories_path=str(yaml_file))
        assert "Food" in repo.get_categories()
```

### Config tests (reset singleton between tests)
```python
@pytest.fixture(autouse=True)
def reset_config():
    """Reset AppConfig singleton state between tests."""
    AppConfig._demo_mode = False
    AppConfig._base_user_dir = None
    yield
    AppConfig._demo_mode = False
    AppConfig._base_user_dir = None
```

## Route Test Patterns

### Happy path (uses test_client + seed fixtures)
```python
class TestBudgetRoutes:
    """Tests for budget API endpoints."""

    def test_get_monthly_rules(self, test_client, seed_budget_rules):
        """Verify GET returns seeded budget rules."""
        response = test_client.get("/api/budget/rules/2024/1")
        assert response.status_code == 200
        assert len(response.json()) == 4
```

### Error path (mock service to trigger exceptions)
```python
from unittest.mock import patch, MagicMock

class TestTransactionsRoutesErrors:
    """Tests for transaction route error handling."""

    def test_create_transaction_value_error(self, test_client):
        """Verify ValueError returns 400."""
        with patch("backend.routes.transactions.TransactionsService") as mock:
            mock.return_value.create_transaction.side_effect = ValueError("bad input")
            response = test_client.post("/api/transactions/", json={...})
            assert response.status_code == 400
```

**Key:** Mock at the route module level (`backend.routes.transactions.TransactionsService`), not the service module.

## Quality Guidelines
- **High coverage, high quality** — avoid "garbage tests" that don't add value
- Every test should have a clear purpose and meaningful assertion
- Test both happy paths and error paths (400, 404, 500)
- Use seed fixtures for realistic data rather than minimal stubs
- For route error tests, use `unittest.mock.patch` to mock services at the route module level

## Running Tests
```bash
poetry run pytest                                      # all tests
poetry run pytest --cov=backend --cov-report=term-missing  # with coverage
poetry run pytest tests/backend/unit/                  # unit tests only
poetry run pytest tests/backend/routes/                # route tests only
poetry run pytest tests/backend/integration/           # integration tests only
poetry run pytest -k "test_budget"                     # by keyword
```

## Verifying UI patches with Playwright (REQUIRED)

For any UI fix — **including small, "obvious" patches** like one-line state
changes, focus tweaks, event handler edits, dropdown/modal behavior — do not
ship the change with only type-checking and reasoning. Reasoning misses cases
that a real browser surfaces immediately (stale closures, focus traps, layout
shifts from the soft keyboard, click-outside handlers eating taps, query
invalidations remounting components mid-interaction).

**Before claiming a UI fix is resolved, you MUST:**

1. Start the dev servers (`python .claude/scripts/with_server.py -- <cmd>`
   or backend + frontend manually).
2. Drive the actual user flow with the Playwright MCP — open the page,
   enable Demo Mode (Settings → Demo Mode toggle, see CLAUDE.md), and
   reproduce the exact interaction the user reported.
3. Confirm the broken behavior **and** that your patch makes it work
   end-to-end, not just that the affected component renders. Click through
   every step of the original repro.
4. Add a Playwright e2e spec under `frontend/e2e/` covering the flow so
   the regression can't return silently. The spec uses Demo Mode and the
   helpers in `frontend/e2e/helpers.ts`. Run it once locally
   (`cd frontend && npx playwright test e2e/<file>.spec.ts`).

### Running e2e specs (start both servers + sandbox browser override)

Specs need the **backend AND frontend dev servers** up. Don't start them
by hand — use the orchestrator, which boots both, waits for readiness,
runs your command, and tears them down:

```bash
# from repo root
python .claude/scripts/with_server.py -- bash -c \
  "cd frontend && npx playwright test <file>.spec.ts --reporter=line"
```

The orchestrator is hardened against the failure modes that produced
silently-invalid e2e runs in the past:

- **Port-conflict fail-fast:** before starting each server it checks the
  port with `lsof -nP -iTCP:<port> -sTCP:LISTEN` and aborts with the
  owning PID/command if anything is already bound (e.g. a dev server from
  another checkout / VS Code task). It never kills the other process —
  stop it yourself and re-run. After readiness it also verifies the
  listening PID belongs to its own child's process group and aborts if a
  stale server stole the port mid-startup.
- **Process-group teardown:** servers start in their own session and are
  stopped with `killpg` (SIGTERM, then SIGKILL after 5 s), so a
  `bash -c "cd frontend && npm run dev"` wrapper can't orphan
  npm/node/vite children.
- **Server logs:** each server's stdout+stderr goes to a temp file
  (`$TMPDIR/with_server_port<port>_*.log`); the path is printed at
  startup, and on startup failure the log tail is echoed for debugging.

**Sandbox browser-version gotcha (Claude Code on the web):** this
environment ships a Playwright Chromium build that lags the
`@playwright/test` version in `package.json`, so a bare
`npx playwright test` dies with *"Executable doesn't exist at
/opt/pw-browsers/chromium_headless_shell-<NNNN>/..."* and **`npx
playwright install` does not work here** (no network for the browser
CDN). Point Playwright at the chromium that *is* installed — the config
already forwards `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` into
`launchOptions.executablePath`:

```bash
# discover the installed full-chrome binary (NOT headless_shell, which is absent)
ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome | tail -1

python .claude/scripts/with_server.py -- bash -c \
  "cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/pw-browsers/chromium-<NNNN>/chrome-linux/chrome \
   npx playwright test <file>.spec.ts --reporter=line"
```

CI and developer machines run `npx playwright install` and need none of
this; the env var is harmless when unset. **Verified green is the only
"verified"** — if the browser failed to launch, the spec did not run, no
matter what the exit summary scrolls past.

### Projects & parallelism (why the suite isn't one flat run)

Demo Mode is a **process-global backend singleton** — one shared SQLite DB
for the whole backend process. That's why the suite can't naively run at
`workers > 1`: parallel workers would race on the same rows, and any spec
that flips the global demo toggle would pull the DB out from under a
concurrently-running spec. The config (`frontend/playwright.config.ts`)
handles this with four projects sequenced by a shared setup:

```
demo-setup ─▶ read-only (parallel) ─▶ mutating (serial) ─▶ demo-teardown
```

- **`demo-setup`** enables Demo Mode once. This replaced the old per-file
  `beforeAll(enableDemoMode)` / `afterAll(disableDemoMode)` pattern, which
  toggled the global demo state at *every* file boundary and forced a full
  demo-DB rebuild (file copy + date-shift over every table) each time.
- **`read-only`** holds specs that do **zero backend writes** (the
  `READ_ONLY_SPECS` list). They share the one demo snapshot safely, so they
  fan out across workers (`fullyParallel`). This is the main speedup — it
  overlaps the slow cold-cache page loads (13–25 s each) instead of paying
  them back to back.
- **`mutating`** holds everything else and runs **serially**. Each mutating
  spec still owns its `beforeAll`/`afterAll` demo lifecycle for per-file DB
  isolation, so its writes never leak into a sibling.
- **`demo-teardown`** disables Demo Mode at the very end.

Run it with the npm script:

```bash
python .claude/scripts/with_server.py -- bash -c \
  "cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/pw-browsers/chromium-<NNNN>/chrome-linux/chrome \
   npm run test:e2e"
```

`npm run test:e2e` is a bare `playwright test` — it runs every project
**serially** and is always safe. read-only and mutating are both plain,
shardable projects (CI runs `playwright test --shard=X/4` across 4 jobs); each
spec self-heals Demo Mode in its own `beforeAll` (a no-op once `demo-setup` has
enabled it), so they can run in any order or interleave within a shard without
one spec's teardown pulling demo out from under another. The `demo-setup`
project enables Demo Mode once up front, which also lets the `read-only` project
fan out across workers safely (no worker races to rebuild the demo DB).

**Do not make `read-only` a dependency of `mutating`.** Playwright never shards
dependency projects — they run in full in every shard — so a `mutating ->
read-only` dependency makes CI run the entire (slow, chart-heavy) read-only
project 4× (once per shard) instead of sharding it. Self-healing `beforeAll`s
are what keep interleaving safe, not a project dependency.

**Why not parallel by default?** `npm run test:e2e:parallel` runs
`--project=read-only --workers=50%` then `--project=mutating --workers=1
--no-deps`. Profiling (from the Plotly era — charts are now much lighter
Recharts SVG, so these numbers are stale and worth re-measuring) showed the
suite was **CPU-bound on browser-side chart rendering**, not the servers —
the backend answers even the heaviest analytics endpoint in <1 s, and a
demo-DB rebuild is ~0.08 s. On the web sandbox (4 cores) two concurrent
Chromium instances each rendering Plotly saturated the CPU, so the parallel
read-only phase came in **slower** than serial (measured 7.3–8.4 m vs
~6.0 m) with flaky timeouts. Client-side parallelism can't beat a
per-test render cost when the box is already CPU-bound, *and* even 2 workers
against one backend saturate the serialized SQLite path. Use
`test:e2e:parallel` only where the CPU can sustain the concurrency.

**Real across-the-board parallel speedup — `npm run test:e2e:isolated`.** The
fix for the shared-backend ceiling is to remove the sharing:
`.claude/scripts/e2e_parallel_isolated.py` starts **N fully isolated
(backend + frontend) pairs**, each with its own port and its own
`FAD_USER_DIR` (hence its own demo SQLite), then runs Playwright `--shard=i/N`
once per pair — each shard pinned to its backend via `BASE_URL` (browser
origin) and `E2E_API_BASE` (the env var `frontend/e2e/helpers.ts` reads for
Node-side API calls). With no shared DB there are **zero cross-shard races**,
so every shard runs concurrently and the only ceiling is real CPU cores. It
auto-picks a shard count (~1 per 3 cores, clamped 2–6); override with
`--shards N`, and forward Playwright args after `--`
(`… e2e_parallel_isolated.py --shards 4 -- categories`). This is an **opt-in
local tool** — it does not touch CI, which keeps its proven single-backend
`--shard=X/4` matrix. It needs the worktree's `.venv` (auto-detected) and
`npm`; each pair costs a uvicorn + a Vite dev server, so it's for multi-core
dev boxes, not the 4-core sandbox.

**Prefer auto-waiting assertions over `waitForLoadState("networkidle")`.** A
bare `networkidle` after navigation waits for *every* straggler request plus a
500 ms quiet window — measured ~2 s of dead wait on a warm dashboard, far more
cold. Playwright's `expect(...).toBeVisible()`, `.click()`, `.fill()`, and
`.waitFor()` already auto-wait for the specific element the test needs, so a
following `networkidle` is usually redundant. Drop it — **unless** the test
then does a *genuinely non-waiting* read, which can race the render.

Know which reads auto-wait, because it's narrower than it looks. A `locator`'s
`.textContent()`, `.getAttribute()`, `.inputValue()`, `.boundingBox()`, and
`.evaluate()` **do** auto-wait for the element to attach — so a `networkidle`
guarding one of those is already redundant and safe to drop. The reads that do
**not** wait are `.count()`, `.all()`, `.isVisible()`/`.isEnabled()`,
`locator.evaluateAll()`, and `page.evaluate()` — plus **negative** auto-retrying
assertions (`toHaveCount(0)`, `not.toBeVisible()`), which pass *vacuously*
against a page that hasn't rendered yet. Before one of those, keep an explicit
wait — best as a positive anchor (`await expect(target.first()).toBeVisible()`,
or `await expect(target).toHaveCount(n)`) rather than `networkidle`. The one
case with no safe substitute is a `.count()`/`.isVisible()` where **zero is a
legitimate answer** (a loop walking months until one has no rows, an
"if this optional banner is present" guard) — those must keep `networkidle`.
Two sweeps have trimmed 60 redundant waits this way (read-only phase ~6.8 m →
~6.0 m); the survivors are the zero-is-valid guards.

**Adding a spec to `READ_ONLY_SPECS`:** only if it performs *no* backend
writes — no POST/PUT/DELETE, no form submit, no create/edit/delete/move of
data. Opening a popover, toggling a view, switching a chart tab, and
navigation are all fine. One writing spec in that list corrupts every
sibling running in parallel, so when in doubt leave it out (unlisted specs
run serially, which is always safe). If you add a write to a spec that's
already in the list, move it out in the same change.

**Authoring gotchas that cost a debugging loop here:**
- The **Auto Tagging "New Rule" / "Apply Rules" buttons live inside a
  collapsed side panel** — click `getByRole("button", { name: /^Auto
  Tagging$/ })` to open it *before* the buttons exist. See
  `rule-editor-preview.spec.ts` for the pattern.
- Helper is `navigateTo(page, path)` (not `gotoPage`); demo toggles are
  `enableDemoMode` / `disableDemoMode` from `frontend/e2e/helpers.ts`.
- Specs go **directly in `frontend/e2e/`**, not a `specs/` subdir.
- The rule editor renders mobile + desktop layout variants at once;
  filter option/button locators with `.filter({ visible: true })`.

**Never** mark a UI patch resolved on the strength of a one-line code change
plus `tsc -b`. The bug, by definition, was something static analysis missed.

**E2E test conventions:**
- Place specs under `frontend/e2e/<feature>.spec.ts`.
- Wrap related cases in `test.describe(...)`. Toggle Demo Mode in
  `beforeAll` / `afterAll` using `enableDemoMode` / `disableDemoMode`.
- Prefer role-based locators (`getByRole("button", { name: ... })`,
  `getByRole("option")`) over CSS selectors — they survive markup churn.
- For inline editors / popovers / dropdowns, assert that the panel stays
  open across mutations when it should, and that the displayed value
  updates after each selection.

## Verifying RTL & responsive — full coverage matrix

A "single pass at desktop English" is **not** enough. Most of our
production bugs (ellipsis chopping the wrong end, signed-number bidi
flips, layout overflows) only show up under one combination of
`(viewport, language)`. Before claiming an audit is complete, drive the
patched flow under **all four**:

|             | English (LTR)    | Hebrew (RTL)   |
|-------------|------------------|----------------|
| Desktop     | 1440 × 900       | 1440 × 900     |
| Mobile      | 375 × 812        | 375 × 812      |

Workflow:

1. Enable Demo Mode (so test data is consistent).
2. For each page in the app: drive the user flow at desktop EN, switch
   to Hebrew via Settings → Language → עברית, repeat. Resize to
   375 × 812, repeat both languages.
3. Run `audit/audit-script.js` (the programmatic auditor) on each
   matrix cell. It catches:
   - SVG paths with `NaN` (broken charts)
   - Translation-key leaks like `transactions.envelopeNamePlaceholder`
   - Signed numbers without `dir="ltr"`
   - Duplicate currency symbols
   - Document-level horizontal overflow
4. For RTL specifically, look at every element with `truncate` or
   `line-clamp` that holds dynamic data — the auditor flags ellipsis
   landing at the wrong end.

If any of the four cells surfaces an issue that the others didn't,
that's the bug class to add a regression test for.

> When changing test structure, naming conventions, or global fixtures, update this rule file.
