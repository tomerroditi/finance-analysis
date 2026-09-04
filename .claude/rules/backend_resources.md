---
paths:
  - "backend/resources/**/*"
---

# Resources Directory — Bundled Seed Data

Read-only data shipped **in git** and seeded into the DB on first run. Nothing
here is user state: user data lives in `~/.finance-analysis/` (SQLite at
`data.db`), and credentials live in the DB + OS Keyring, never in a file here.

| File | Purpose | Read by |
|------|---------|---------|
| `default_categories.yaml` | Default category → tags hierarchy, seeded on first run | `repositories/tagging_repository.py` |
| `categories_icons.yaml` | Emoji per category, for UI rendering | `config.py`, `tagging_repository.py`, `routes/tagging.py`, `services/tagging_service.py` |
| `boi_rates.yaml` | Bank of Israel rate history, seeded into `interest_rates` (series `boi_rate`) | `services/rates_service.py` |
| `demo_data.db` | Frozen SQLite snapshot backing Demo Mode | `demo_setup.py`, `config.py`, `routes/testing.py` |
| `test_credentials.yaml` | Fake creds for the dummy 2FA scrapers — no real accounts | `tests/.../test_scraper_base.py` |

## Things that will trip you up

- **Categories are DB-backed now.** `default_categories.yaml` is a *seed*, not
  the live source. Editing it changes what a **fresh install** gets; existing
  users are unaffected. There is no `~/.finance-analysis/categories.yaml`.
- **There is no credentials YAML.** The legacy `credentials.yaml` is deleted on
  startup after migration into the DB. Non-sensitive fields are Fernet-encrypted
  (`utils/crypto.py`); passwords are in the Keyring.
- **`boi_rates.yaml` entries are step points** — a rate holds from its `date`
  until the next entry. Prime is derived at read time as BoI + 1.5 and never
  stored. Pre-2020 points are year-end approximations (±0.25pp); 2020 onward is
  decision-level. `POST /api/rates/refresh` pulls live values.
- **`demo_data.db` is a frozen snapshot.** Toggling Demo Mode re-copies it, so
  anything hand-added inside Demo Mode is lost. Regenerating it has its own
  rules — see the `demo-data-generation` skill.
- **`test_credentials.yaml` is committed on purpose** and holds only dummy
  values for `dummy_tfa`. Never put a real credential in it.

## Adding a default category

Add it to `default_categories.yaml`, add an icon to `categories_icons.yaml`
(optional — categories render without one), and it lands on fresh installs only.
