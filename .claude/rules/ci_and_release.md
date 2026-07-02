# CI & Release Pipeline

How GitHub Actions are wired up. Read this before touching anything in
`.github/workflows/`.

## Three workflows, three responsibilities

| Workflow                 | Trigger                | Purpose                                          |
|--------------------------|------------------------|--------------------------------------------------|
| `.github/workflows/ci.yml`     | `pull_request` to main, manual | Validate every PR — backend pytest + frontend lint, type-check, build, vitest. Fails the PR if anything breaks. |
| `.github/workflows/release.yml`| `push` to main         | Re-run CI checks, then `commitizen` bump, build the Windows installer + macOS DMG, attach to the GitHub release. |
| `.github/workflows/deploy.yml` | `push` to main, manual | Deploy the public demo to Cloudflare Workers — frontend as edge static assets, FastAPI backend as a Cloudflare Container (see `wrangler.jsonc` + `deploy/cloudflare/`). Needs the `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` repo secrets. |

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

## Branch & PR workflow

Feature branches must target **`dev`**, not `main`.

- Open a PR against `dev`. Let `ci.yml` run (pytest + lint + build + vitest).
- Merge with a conventional-commit subject.
- When `dev` is ready to ship, open a `dev → main` PR. That merge triggers
  `release.yml`: CI re-runs, commitizen bumps the version, and the installer
  + DMG are built and attached to the GitHub release.

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
