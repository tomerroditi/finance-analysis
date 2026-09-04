---
paths:
  - ".github/**/*"
  - "pyproject.toml"
---
# CI & Release Pipeline

How GitHub Actions are wired up. Read this before touching anything in
`.github/workflows/`.

## Three workflows, three responsibilities

| Workflow                 | Trigger                | Purpose                                          |
|--------------------------|------------------------|--------------------------------------------------|
| `.github/workflows/ci.yml`     | `pull_request` (any base), manual | Validate every PR — backend pytest + frontend lint, type-check, build, vitest on all PRs; **the full Playwright e2e suite across 4 parallel shards** additionally runs on PRs targeting `main` or `dev`; the Schemathesis API-fuzz job runs only on PRs targeting `main`. Since feature PRs now target `main`, both extra jobs run on every one of them. Fails the PR if anything breaks. |
| `.github/workflows/build-smoke.yml` | `pull_request` to main touching `build/`, `backend/`, `scraper/`, deps, or the workflow itself; manual | Build the Windows bundle on `windows-latest` and run its in-bundle smoke test + `--uninstall-cleanup` CLI + bundle-size cap. Green/red signal only — no artifacts uploaded. |
| `.github/workflows/release.yml`| `push` to main         | `commitizen` bump, build the Windows installer (**no macOS artifact** — see `installation_and_updates.md`), smoke-test it, attach to the GitHub release. |

The split exists because:

1. **PRs need fast feedback.** `release.yml` drags installer steps that
   PRs don't care about, so PRs run the lighter `ci.yml` instead.
2. **Releases must be gated by a green test run.** `release.yml` itself
   runs no tests — the gate is the PR that landed the commit on `main`
   (`ci.yml`'s e2e job runs on every PR targeting `main` or `dev`; the
   fuzz job on every PR targeting `main`).

Don't merge them into one workflow.

## What runs on a PR (`ci.yml`)

- Backend: `poetry run pytest`
- Frontend: `npm run lint`, `npm run build` (`tsc -b && vite build`),
  `npm test` (vitest)
- **E2E: `npx playwright test` sharded 4 ways** (`E2E (Playwright, shard N/4)`).
  This runs the **entire** `frontend/e2e/` suite, not just the specs you added.
  It is a required check — a red shard blocks the merge.

**All of these are required checks.** After you push, don't assume green just
because your own new spec passed locally — the e2e job runs every spec, so a
change that removes or restructures shared UI can break a spec you never
touched (e.g. removing a chart from a page breaks the merged page journey
specs — `investments.spec.ts`, `liabilities.spec.ts`, `dashboard.spec.ts` —
which look for `.recharts-wrapper` on that page).
Before pushing a change to a shared component, grep `frontend/e2e/` for the
`data-card-id` / testid / selector you're changing. After pushing, run
`gh pr checks <PR#>` and fix any red check — that's part of the task, not
optional follow-up.

Add a step here when you land a new lint or static-analysis tool that should
block merges. Do **not** add release-only steps (installer builds, DMG signing)
here — they belong in `release.yml`.

## Conventional commits & version bumping

`release.yml` uses [Commitizen](https://commitizen-tools.github.io/commitizen/)
for semver bumps based on commit messages:

| Commit prefix         | Bump  |
|-----------------------|-------|
| `fix:`, `perf:`       | patch |
| `feat:`               | minor |
| `BREAKING CHANGE:` (in body) or `!:` | major |
| `chore:`, `docs:`, `refactor:`, `test:`, `style:` | none  |

The bump commit `bump: version X.Y.Z → A.B.C [skip ci]` is excluded from
re-triggering the release pipeline by the `if: !startsWith(... 'bump:')`
check on release.yml's `get-version` job.

## Branch & PR workflow

Feature branches target **`main`**. Branch off `main`, merge back into `main`.

- Open a PR against `main`. Let `ci.yml` run the full gate — pytest + lint +
  build + vitest, the 4-shard Playwright e2e suite, and the Schemathesis
  API-fuzz job (the last two are gated on the base branch, and `main`
  triggers both).
- Merge with a conventional-commit subject. That subject drives the version
  bump, and since every feature merge lands on `main`, **every feature merge
  cuts a release**: the merge triggers `release.yml`, commitizen bumps the
  version, and the Windows installer is built and attached to the GitHub
  release. Use `chore:`/`docs:`/`refactor:`/`test:`/`style:` when a change
  should not bump the version.

If a release fails partway (e.g. the NSIS step), do not retry by
force-pushing. Open a follow-up PR with a `fix:` commit and merge that.

### `dev` is dormant

The repo used to stage feature branches on `dev` and ship via `dev → main`
release merges. That stopped being practised around 2026-07 — every PR since
targets `main` directly — and `dev` has fallen ~100 commits behind. **Don't
branch from `dev` or target it.**

`ci.yml` still gates its e2e job on `github.base_ref == 'dev'` as well as
`'main'`, so the staging flow would still be validated if someone revived it.
Revive it deliberately if you want it back; the risk is drifting into it by
accident and landing work on a branch that never ships.

One thing is genuinely stranded there: PR #220's frontend dependency
auto-bootstrap (`.claude/scripts/bootstrap_frontend.sh` plus its `start.sh`
and `frontend/package.json` wiring) was merged to `dev` on 2026-08-22 and
never reached `main`. Port it in a fresh PR against `main` rather than
resurrecting the `dev → main` merge for it.

If you do revive `dev`, note that GitHub's "Automatically delete head
branches" setting (Settings → General → Pull Requests) deletes the head
branch of every merged PR, which silently kills `dev` after each `dev → main`
merge. Protect it with a branch ruleset that restricts deletion (Settings →
Rules → Rulesets → target `dev` → "Restrict deletions"); feature branches
still get auto-cleaned. Re-create it from `main` with
`git push origin main:dev` if it disappears.

## Local pre-flight

Before opening a PR, locally run what CI runs to avoid the round-trip:

```bash
poetry run pytest
cd frontend && npm run lint && npm run build && npm test
```

For partial loops while iterating:

```bash
poetry run pytest tests/backend/unit/services/test_xyz.py
cd frontend && npm test -- --run path/to/spec.test.ts
```
