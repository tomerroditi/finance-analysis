# CI & Release Pipeline

How GitHub Actions are wired up. Read this before touching anything in
`.github/workflows/`.

## Three workflows, three responsibilities

| Workflow                 | Trigger                | Purpose                                          |
|--------------------------|------------------------|--------------------------------------------------|
| `.github/workflows/ci.yml`     | `pull_request` (any base), manual | Validate every PR — backend pytest + frontend lint, type-check, build, vitest on all PRs; **the full Playwright e2e suite across 4 parallel shards** additionally runs on PRs targeting `dev` or `main`; the Schemathesis API-fuzz job runs only on PRs targeting `main`. Fails the PR if anything breaks. |
| `.github/workflows/build-smoke.yml` | `pull_request` to main touching `build/`, `backend/`, `scraper/`, deps, or the workflow itself; manual | Build the Windows bundle on `windows-latest` and run its in-bundle smoke test + `--uninstall-cleanup` CLI + bundle-size cap. Green/red signal only — no artifacts uploaded. |
| `.github/workflows/release.yml`| `push` to main         | `commitizen` bump, build the Windows installer (**no macOS artifact** — see `installation_and_updates.md`), smoke-test it, attach to the GitHub release. |

The split exists because:

1. **PRs need fast feedback.** `release.yml` drags installer steps that
   PRs don't care about, so PRs run the lighter `ci.yml` instead.
2. **Releases must be gated by a green test run.** `release.yml` itself
   runs no tests — the gate is the PR that landed the commit on `main`
   (`ci.yml`'s e2e job runs on every PR targeting `dev` or `main`; the
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

Feature branches must target **`dev`**, not `main`.

- Open a PR against `dev`. Let `ci.yml` run (pytest + lint + build + vitest
  + the 4-shard Playwright e2e suite).
- Merge with a conventional-commit subject.
- When `dev` is ready to ship, open a `dev → main` PR. The PR runs the full
  `ci.yml` gate (including e2e + fuzz); the merge then triggers `release.yml`:
  commitizen bumps the version, and the Windows installer is built and
  attached to the GitHub release.

**`dev` is a long-lived branch — never delete it.** GitHub's "Automatically
delete head branches" setting (Settings → General → Pull Requests) deletes
the head branch of every merged PR, which silently kills `dev` after each
`dev → main` release merge. Either keep that setting off, or (better) protect
`dev` with a branch ruleset that restricts deletion (Settings → Rules →
Rulesets → target `dev` → "Restrict deletions") — protected branches survive
auto-delete, so feature branches still get cleaned up. If `dev` ever
disappears again, re-create it from `main` (`git push origin main:dev` or the
GitHub UI) — losing it only loses the pointer, not history, as long as it was
fully merged.

Never open a feature PR directly to `main`. The only PRs that should target
`main` are `dev → main` release merges.

If a release fails partway (e.g. NSIS step), do not retry by force-pushing.
Push a `fix:` commit to `dev`, then re-open the `dev → main` PR.

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
