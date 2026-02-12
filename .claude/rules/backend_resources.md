---
globs: backend/resources/**/*
---

# Resources Directory - Configuration & Static Data

YAML configuration files for defaults, credentials, and UI customization.

## Files Overview

| File | Location | Purpose | Modifiable |
|------|----------|---------|------------|
| `default_credentials.yaml` | `backend/resources/` | Empty template for credentials | No (in git) |
| `credentials.yaml` | `~/.finance-analysis/` | User's actual credentials | Yes (via UI) |
| `default_categories.yaml` | `backend/resources/` | Default category/tag hierarchy | No (in git) |
| `categories.yaml` | `~/.finance-analysis/` | User's categories | Yes (via UI) |
| `categories_icons.yaml` | `backend/resources/` | Emoji icons for categories | Yes (via UI) |
| `test_credentials.yaml` | `backend/resources/` | Test account creds | No (gitignored) |

## Security

| Stored in YAML | NOT in YAML |
|-------------------|----------------|
| Provider names, usernames | Passwords (-> OS Keyring) |
| Account numbers, user codes | 2FA codes (ephemeral) |
| Email addresses, phone numbers | Session tokens |

## Data Flow

### First-Time Setup
1. App checks for `~/.finance-analysis/credentials.yaml`
2. If missing, creates from `default_credentials.yaml` structure
3. Same for `categories.yaml` from `default_categories.yaml`
4. User fills credentials via UI -> saved to YAML + Keyring

### Regular Usage
1. Load `~/.finance-analysis/credentials.yaml` + passwords from Keyring
2. Load `~/.finance-analysis/categories.yaml`
3. Load `categories_icons.yaml` for UI rendering

## Common Tasks

### Adding New Default Category
1. Edit `backend/resources/default_categories.yaml`
2. Add icon to `categories_icons.yaml`
3. Users see new category on fresh install

### Adding Support for New Provider
1. Add to `backend/constants/providers.py` enums
2. Add login fields to `LoginFields.providers_fields` in `backend/constants/providers.py`
3. Users add credentials via UI

## Notes
- `~/.finance-analysis/` is user data directory (auto-created on first run)
- Icons are optional - categories work without them
- Always validate YAML structure after manual edits
