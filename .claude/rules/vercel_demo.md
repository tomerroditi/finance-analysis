---
paths:
  - "index.py"
  - "vercel.json"
  - "backend/demo_sessions.py"
  - "backend/utils/vercel_blob.py"
  - "frontend/src/services/demoMode.ts"
---
# Vercel demo — per-visitor sandboxes

The live demo (`finance-analysis-fawn.vercel.app`) is a single Python
serverless function (`index.py` → `backend/main.py`) that pins demo mode
process-wide and serves SQLite out of `/tmp`. Serverless `/tmp` is
per-instance and discarded on recycle, so for a long time every visitor
shared one copy and lost their edits whenever the function went cold. That
is what `backend/demo_sessions.py` fixes.

## How it works

- **Identity.** The frontend mints a random id once per browser
  (`fad_demo_session` in localStorage, `services/demoMode.ts`) and sends it
  on every request as `X-FAD-Demo-Session`. It is sent even when the stored
  Demo Mode flag is off, because the Vercel deployment forces the mode
  server-side and never sets that flag.
- **Isolation.** With `FAD_DEMO_SESSIONS=1` (set by `index.py`) the
  `resolve_demo_mode` middleware binds a validated id into
  `AppConfig._demo_session_ctx`; `AppConfig.get_user_dir()` then resolves to
  `demo_env/sessions/<id>/`, so the visitor gets their own `demo_data.db`.
  The engine registry is keyed by path, so nothing else changes. A request
  with no id (curl, malformed header, storage-less browser) keeps the shared
  ephemeral copy exactly as before.
- **Seeding.** `index.py` prepares the shared demo DB at cold start (copy +
  date shift + hishtalmut backfill) and then `snapshot_template()` freezes
  it as `demo_env/demo_template.db`. A first-seen visitor is a `copy2` of
  that template (milliseconds). Without a template (local dev, tests) the
  store builds from the frozen snapshot straight into the sandbox dir.
- **Durability.** When `BLOB_READ_WRITE_TOKEN` is set, every successful
  mutating `/api` request (`POST/PUT/PATCH/DELETE`, 2xx/3xx) uploads the
  whole sandbox file to Vercel Blob at `demo-sessions/<id>.db`, and a
  visitor's first request on an instance that has never seen them
  downloads it back. The file is ~1.3 MB, so the whole-file approach costs
  one upload per write and keeps the backend SQLite-only. Upload/download
  failures are logged and degrade to "instance-local sandbox", never a 500.
- **Reset.** `POST /api/testing/demo/reset` with a bound id wipes only that
  visitor's copy (local + blob) and re-clones the template; the middleware
  then persists the fresh copy. The Settings "Reset demo data" button now
  works on Vercel.
- **Pruning.** `vercel.json` declares a daily cron hitting
  `GET /api/testing/demo/prune`. The route 404s unless `CRON_SECRET` is set
  and 401s without the matching bearer (Vercel sends it automatically).
  Blobs older than `FAD_DEMO_SESSION_TTL_DAYS` (default 14) are deleted.

## Vercel project setup (one-time, not in the repo)

1. Storage → create a **Blob** store, access **private**, connect it to the
   project. This injects `BLOB_READ_WRITE_TOKEN` into the function env.
   Without it sandboxes still isolate visitors but do not survive recycles.
2. Settings → Environment Variables → add `CRON_SECRET` (any long random
   string) so the prune cron can authenticate. Hobby crons run once a day
   at an imprecise time; that is fine here.
3. Optional: `FAD_DEMO_SESSION_TTL_DAYS`, `FAD_DEMO_BLOB_ACCESS`
   (`private` default; set `public` only if the store was created public).

## Blob REST contract (no Python SDK exists)

`backend/utils/vercel_blob.py` mirrors `@vercel/blob` 2.x:

| op | request |
| --- | --- |
| put | `PUT https://vercel.com/api/blob/?pathname=<p>` + `x-api-version: 12`, `x-vercel-blob-access`, `x-allow-overwrite: 1`, `x-add-random-suffix: 0` |
| list | `GET https://vercel.com/api/blob/?prefix=&limit=&cursor=` → `{blobs, cursor, hasMore}` |
| delete | `POST https://vercel.com/api/blob/delete` body `{"urls": [...]}` |
| get | `GET <blob.url>?cache=0` with `authorization: Bearer <token>` |

Downloads use the URL from a listing rather than a constructed one so the
host is right whatever access mode the store has, and `cache=0` bypasses
the CDN so a re-uploaded pathname is never served stale. If Vercel bumps
the API version in a way that breaks these shapes, the symptom is silent:
sandboxes stop persisting (warnings in the function logs), nothing 500s.
`tests/backend/unit/utils/test_vercel_blob.py` pins the request shapes.

## Known limits

- Two tabs of one visitor landing on different instances are
  last-writer-wins. Acceptable for a demo; Hobby concurrency is low.
- A sandbox's dates are anchored to the day it was seeded; the prune TTL
  bounds how stale a returning visitor's data can get.
- Local dev and the e2e suite keep the single shared demo DB —
  `FAD_DEMO_SESSIONS` is only set by `index.py`. Do not enable it under
  Playwright: the specs rely on `resetDemoData()` rebuilding one shared file.
