---
paths:
  - "scraper/**/*.py"
  - "backend/scraper/**/*.py"
  - "backend/services/scraping_service.py"
---

# Scraper Framework — Pure-Python Provider Scrapers

Two packages, one name. Keep them straight:

| Package | Role |
|---------|------|
| `scraper/` (repo root) | The framework: base classes, 20 providers, models, exceptions. No backend imports. |
| `backend/scraper/` | Just `adapter.py` — bridges the async framework into the sync FastAPI pipeline. |

```
ScrapingService -> ScraperAdapter (async->sync, OTP) -> BaseScraper subclass
                                                        |
                                       Playwright / httpx -> provider site
                        AccountResult[] -> DataFrame -> TransactionsRepository -> SQLite
```

**Building a new provider?** Use the `scraper-development` skill — it drives
read-only browser exploration of the live site, then generates the class. This
file is the framework reference, not the authoring guide.

## Import caveat (bites every time)

`backend/scraper/` shadows the root `scraper/` package. Backend code must
resolve the root package through `_import_scraper_module()` in `adapter.py` —
never a bare `import scraper`. Test dirs use a `test_scraper/` prefix so pytest
doesn't collide on the name.

## Base classes (`scraper/base/`)

- **`BaseScraper`** — abstract lifecycle. `scrape()` runs
  `initialize -> login -> fetch_data -> terminate`, emitting progress
  (`"initializing"`, `"logging in"`, `"fetching data"`, `"done"`) and converting
  every phase failure into a `ScrapingResult` via `_phase_failure`. Subclasses
  implement the four phase methods, never `scrape()` itself.
- **`BrowserScraper`** — Playwright lifecycle + form login. Provides
  `get_login_options()`, `navigate_to()`, and `fetch_get`/`fetch_post` that run
  inside the page context (so they carry the session cookies).
- **`ApiScraper`** — httpx client, no browser. Use when login and data both
  work over plain HTTP.

**Phase failures name the exception class.** `_phase_failure` formats
`"<phase> failed: <detail>"` with the exception type included — a bare `str(e)`
on an argument-less exception recorded an empty message and hid the phase.
Don't "simplify" that back.

## Models (`scraper/models/`)

`Transaction`, `InstallmentInfo`, `AccountResult`, `ScrapingResult`,
`LoginResult`, `ProviderConfig`. `PROVIDER_CONFIGS` in `credentials.py` is the
registry — 20 entries, and a provider that isn't there doesn't exist as far as
the app is concerned.

## Errors (`scraper/exceptions.py`)

All inherit `ScraperError` and carry an `ErrorType` matching the upstream
`israeli-bank-scrapers` vocabulary (`INVALID_PASSWORD`, `CHANGE_PASSWORD`,
`ACCOUNT_BLOCKED`, `TWO_FACTOR_RETRIEVER_MISSING`, `INVALID_OTP`, `TIMEOUT`,
`AUTOMATION_BLOCKED`, `GENERIC`, `GENERAL_ERROR`): `CredentialsError`,
`PasswordChangeError`, `AccountBlockedError`, `TwoFactorError`,
`InvalidOtpError` (the bank rejected the typed code), `TimeoutError`,
`AutomationBlockedError`, `ConnectionError`.

## 2FA / OTP

`ScraperAdapter` owns the whole dance. The scraper parks in
`on_otp_request`; the adapter awaits an `asyncio.Event` that a **synchronous**
route sets from a threadpool via `set_otp_code()` — hence the captured event
loop and `call_soon_threadsafe`. Cancel by passing the `OTP_CANCEL_SENTINEL`,
which must stay in sync with `scraper.base.base_scraper`.

Two things that look redundant and aren't:
- **Live-adapter registry** — keyed so a second launch for a 2FA provider
  doesn't fire a second `/otp/prepare` and a duplicate SMS.
- **`_persist_refreshed_otp_token`** — providers issuing a rotated long-term
  token need it written back after a successful run; the credential form has no
  field for it, so nothing else can.

## Demo mode

`adapter.py` redirects to dummy scrapers when `AppConfig().is_demo_mode` and the
provider name lacks `test_`. Demo mode never touches a real site.

## Single-flight per account

`_active_scrapers` (in `adapter.py`, keyed by
`scraper_registry_key(demo, service, provider, account)`) makes
`start_scraping_single` a no-op for an account that is already scraping — it
returns the running `process_id` instead of opening a second history row,
building a second adapter, or firing a second OTP SMS.

Two ordering rules keep that guarantee, both enforced in
`scraping_service._launch_lock`:

- **Take the lock.** `start_scraping_single` is a *synchronous* route handler,
  so FastAPI runs it in a threadpool worker and two requests for one account
  run on two real OS threads. Reasoning about `await` points does not apply.
  The registry re-check, the history insert, the registration and the launch
  all sit inside the lock; the slow preparation (keyring reads, start-date
  lookup) stays outside it so one account's launch never queues behind
  another's keyring round trip.
- **Register before launching.** `run()` executes on the scraper loop's own
  thread and pops both registries *by identity* in its `finally`. Launch
  first and a scrape that fails immediately reaches that cleanup before the
  key exists: the pop no-ops, the finished adapter gets registered afterwards,
  and the account stays locked until the process restarts. If the launch
  itself raises there is no `run()` to clean up, so the start path undoes its
  own registration and closes out the history row.

## Limits

5-minute timeout per run, no automatic retry, no daily cap — a user can
re-scrape an account as often as they like (the OTP prepare limiter is the
only throttle). History in `scraping_history` (`success` / `failed` /
`canceled`); the latest `success` row is the watermark the next window
starts 7 days before.

## CLI

```bash
python -m scraper --list                      # all providers
python -m scraper <provider> --show-browser   # run one with a visible browser
```
