# Finance Analysis Dashboard — Architecture Context

Always-on companion to `CLAUDE.md`. **`CLAUDE.md` is canonical** for commands,
environment setup, key conventions (transaction signs, categories, budgets,
tagging, savings goals, retirement), code style, the branch/PR workflow, and
the gotcha list — this file deliberately does not repeat any of it. What lives
here is the layer contract, the security model, and the map of the tree.

## Layer contract

```
Routes (FastAPI) -> Services (Business Logic) -> Repositories (Data Access) -> SQLite
Pages (Routing)  -> Components (UI Logic)     -> services/api.ts -> Zustand / TanStack Query
```

- **Routes** own HTTP concerns only. Pydantic request/response schemas are
  declared inline in the route file, not in `models/`.
- **Services** orchestrate business logic and call repositories. All logic
  lives here — never in a route or a component.
- **Repositories** own *every* DB operation (SQLAlchemy ORM, Repository
  Pattern). Nothing outside them touches a session.
- **Models** (`backend/models/`) are SQLAlchemy ORM schemas only.

## Security model

- **Passwords** live in the OS Keyring, never in code or config. Every
  keyring access goes through `backend/utils/keyring_store.py` — service
  names, demo namespacing, get/set/delete, the field-encryption key, and
  insecure-backend validation. No other backend module imports `keyring`
  directly; the one exception is `backend/uninstall/cleanup.py`, which keeps
  a lazy import so the standalone uninstall CLI stays best-effort (a
  drift-guard test pins its constants to the store).
- **Non-sensitive credential fields** (usernames, ID numbers, card digits)
  are Fernet-encrypted at rest via `backend/utils/crypto.py`.
- **Routes must not echo exception text in 5xx bodies** — it can carry SQL
  fragments, file paths, or secrets. Let the global handler return the opaque
  body and log the detail. Never log credentials.
- **Dependency scanning:** `.github/dependabot.yml` (npm + pip + actions,
  weekly) and `.github/workflows/codeql.yml` (Python + TypeScript,
  `security-extended`). Workflows declare least-privilege `permissions:`;
  only the two release jobs opt up to `contents: write`.
- Network access model (loopback trust, bearer token, `ALLOWED_HOSTS`, CSRF
  on writes) is in `CLAUDE.md` → Gotchas.

## Adding a feature

**New API route:** define it in `backend/routes/` → logic in a service →
data via a repository → add the endpoint to `frontend/src/services/api.ts`
(paths must match the route *exactly*, trailing slash included — see
`api_paths.md`). `python .claude/scripts/scaffold_feature.py <name>`
generates the boilerplate. If the response is sensitive, real-time, or a
read-only POST, update the PWA cache lists too (`frontend_pwa.md`).

**New UI page/component:** `frontend/src/pages/` or `components/`, Tailwind
CSS 4 with logical properties, TanStack Query for fetching, `t("...")` for
every user-visible string in both locale files.

## Tree

```
backend/       constants/ routes/ services/ repositories/ models/ scraper/
               resources/ (default-category YAML) uninstall/ utils/ alembic/
               database.py demo_setup.py errors.py main.py
scraper/       Pure-Python provider framework (Playwright + httpx) — 19 providers
frontend/src/  components/ pages/ services/ hooks/ stores/ context/ utils/
               locales/ queryClient.ts
tests/backend/ unit/ routes/ integration/ migrations/
fad/           DEPRECATED legacy Streamlit package — ignore
```

Scoped rule files in `.claude/rules/` load automatically when you open a file
they cover (`paths:` frontmatter). Read one directly when you need its domain
without touching the code: `backend_services.md`, `backend_repositories.md`,
`backend_scraper.md`, `frontend_components.md`, `frontend_pages.md`,
`frontend_pitfalls.md`, `frontend_responsive.md`, `frontend_i18n.md`,
`frontend_i18n_checklist.md`, `frontend_utils.md`, `frontend_pwa.md`,
`api_paths.md`, `testing.md`, `ci_and_release.md`, `kpi_calculations.md`,
`retirement_calculations.md`, `savings_goals.md`, `split_transactions.md`,
`installation_and_updates.md`, `onezero_mtls.md`, `backend_resources.md`.
