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
- **Durability and consistency.** Blob is the source of truth, not `/tmp`.
  A serverless page load fans a dozen requests out over several instances,
  each with its own `/tmp`, so a local copy can never be trusted for the
  instance's lifetime: **every sandboxed request first revalidates its local
  file against the blob** (`GET <blob-url>?cache=0` with `If-None-Match`; a
  304 costs no transfer, a 200 replaces the file, a 404 means nothing was
  persisted yet). Concurrent requests of one visitor share a single
  revalidation per 250 ms. Every successful mutating `/api` request
  (`POST/PUT/PATCH/DELETE`, 2xx/3xx) uploads the whole sandbox file
  (~1.3 MB) to `demo-sessions/<id>.db` and records the returned etag, so the
  writing instance does not re-download its own write. Blob failures are
  logged and degrade to the local copy, never a 500. **Without
  `BLOB_READ_WRITE_TOKEN` the feature is not usable on Vercel**: sandboxes
  are instance-local, so a write served by one instance is invisible to a
  read served by another and everything vanishes on recycle. Connecting the
  store is step 1 of the setup below, not optional.
- **Read-time writes.** The savings-goal allocation ledger is materialized
  lazily by budget GETs. It is pre-computed into the template at cold start
  (`index.py`) so a fresh sandbox reads instead of racing a dozen parallel
  inserts, and `upsert_allocation` is a single `INSERT ... ON CONFLICT DO
  UPDATE` so the race is harmless when it does happen. Read-time writes are
  not uploaded (GETs never persist); they are deterministic and get
  recomputed identically on any instance.
- **Reset.** `POST /api/testing/demo/reset` with a bound id wipes only that
  visitor's copy (local + blob) and re-clones the template; the middleware
  then persists the fresh copy. The Settings "Reset demo data" button now
  works on Vercel.
- **Pruning.** `vercel.json` declares a daily cron hitting
  `GET /api/testing/demo/prune`. The route 404s unless `CRON_SECRET` is set
  and 401s without the matching bearer (Vercel sends it automatically).
  Blobs older than `FAD_DEMO_SESSION_TTL_DAYS` (default 14) are deleted.

- **When Blob is missing.** `index.py` logs a WARNING at cold start,
  `GET /api/testing/demo_mode_status` reports `blob_configured: false`
  (that flag needs no session header, so a bare `curl` answers it), and the
  layout renders `DemoSandboxNotice` — an amber "Demo changes are not being
  saved" strip — for any browser whose sandbox is not durable. The notice
  never appears locally; `frontend/e2e/demo-sandbox-notice.spec.ts` drives
  both states by stubbing the status endpoint.
- **Fluid compute.** `vercel.json` sets `"fluid": true` so one warm
  instance serves a visitor's whole request burst instead of Vercel
  spinning a fresh instance (and a fresh `/tmp`) per concurrent request.
  That makes a single visitor's session consistent even before Blob is
  connected, but not durable: cold starts still wipe `/tmp`.

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
| get | `GET https://<store>.<access>.blob.vercel-storage.com/<p>?cache=0` with `authorization: Bearer <token>`, optional `If-None-Match` (304 on hit) |

Downloads build the blob URL from the store id (parsed from the token) and
the access mode; the first successful upload reveals the store's real mode
in the returned URL and the client corrects itself if it was configured
wrong. `cache=0` bypasses the CDN so a re-uploaded pathname is never served
stale. If Vercel bumps
the API version in a way that breaks these shapes, the symptom is silent:
sandboxes stop persisting (warnings in the function logs), nothing 500s.
`tests/backend/unit/utils/test_vercel_blob.py` pins the request shapes.

## Known limits

- Two instances writing the same sandbox at the same instant are
  last-writer-wins on the upload. Reads converge on the next revalidation.
  Acceptable for a demo; Hobby concurrency is low.
- A sandbox's dates are anchored to the day it was seeded; the prune TTL
  bounds how stale a returning visitor's data can get.
- Local dev and the e2e suite keep the single shared demo DB —
  `FAD_DEMO_SESSIONS` is only set by `index.py`. Do not enable it under
  Playwright: the specs rely on `resetDemoData()` rebuilding one shared file.
