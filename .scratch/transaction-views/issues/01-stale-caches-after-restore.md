# 01 — Stale categories and credentials after a backup restore

Status: resolved

## Problem

`restore_backup` reset only the engines and `data_cache`. The categories
and credentials caches are keyed by database path, and a restore keeps the
path, so the app went on serving the pre-restore categories and credentials
until restart. Three "forget this database" paths each cleared a different
subset (restore, demo rebuild, sandbox wipe), and the scraper adapter wrote a
refreshed OTP token past `CredentialsService` without evicting its cache.

## Fix

- `backend.database.register_path_cache` — a path-keyed cache registers a
  `forget(db_path | None)` callback once; `reset_engine_for` /
  `reset_engines` call every registered callback, so an engine reset always
  forgets every cache read through it.
- `CategoriesTagsService` and `CredentialsService` register their caches;
  their `clear_cache_for` duplicates are gone, and the sandbox wipe and demo
  rebuild are just engine resets.
- `restore_backup` resets again after the copy, so a request served
  mid-restore cannot keep the old file's categories.
- The adapter evicts the credentials cache after persisting a refreshed
  token.

## Tests

- `tests/backend/unit/utils/test_backup.py::TestRestoreBackupForgetsCaches`
- `tests/backend/unit/services/test_mode_scoped_caches.py` (engine resets
  evict per path / every path)
- `tests/backend/unit/test_scraper/test_adapter_force_2fa.py::...::test_persisting_drops_the_cached_credentials`
