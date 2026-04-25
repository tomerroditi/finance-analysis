# CI & Release Pipeline

How GitHub Actions are wired up. Read this before touching anything in
`.github/workflows/`.

## Two workflows, two responsibilities

| Workflow                 | Trigger                | Purpose                                          |
|--------------------------|------------------------|--------------------------------------------------|
| `.github/workflows/ci.yml`     | `pull_request` to main, manual | Validate every PR — backend pytest + frontend lint, type-check, build, vitest. Fails the PR if anything breaks. |
| `.github/workflows/release.yml`| `push` to main         | Re-run CI checks, then `commitizen` bump, build the Windows installer + macOS DMG, attach to the GitHub release. |

The split exists because:

1. **PRs need fast feedback.** `release.yml` drags installer/DMG steps that
   PRs don't care about, so PRs run the lighter `ci.yml` instead.
2. **Releases must be gated by a green test run.** The `ci-checks` job at the
   top of `release.yml` mirrors the PR validation so a flaky main commit
   can't sneak through.

Don't merge them into one workflow. The duplicate-CI-step is intentional.

## What runs on a PR (`ci.yml`)

- Backend: `poetry run pytest`
- Frontend: `npm run lint`, `npm run build` (`tsc -b && vite build`),
  `npm test` (vitest)

Add a step here when you:

- Land a new lint or static-analysis tool that should block merges.
- Add a new test layer (e.g. e2e in CI).

Do **not** add release-only steps (installer builds, DMG signing) here —
they belong in `release.yml`.

## Conventional commits & version bumping

`release.yml` uses [Commitizen](https://commitizen-tools.github.io/commitizen/)
for semver bumps based on commit messages:

| Commit prefix         | Bump  |
|-----------------------|-------|
| `fix:`, `perf:`       | patch |
| `feat:`               | minor |
| `BREAKING CHANGE:` (in body) or `!:` | major |
| `chore:`, `docs:`, `refactor:`, `test:`, `style:` | none  |

The bump commit `bump: version X.Y.Z → A.B.C [skip ci]` is excluded from CI
re-runs by the `if: !startsWith(... 'bump:')` check on the `ci-checks` job.

## Don't push directly to `main`

- Open a PR. Let `ci.yml` run.
- Merge with a conventional-commit subject.
- `release.yml` picks it up, bumps, builds, releases.

If a release fails partway (e.g. NSIS step), do not retry by force-pushing.
Push a `fix:` commit so commitizen bumps cleanly.

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
