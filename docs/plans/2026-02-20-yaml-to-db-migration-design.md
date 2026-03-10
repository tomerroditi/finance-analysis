# YAML-to-DB Migration: Tagging & Credentials Repositories

**Date:** 2026-02-20
**Status:** Approved
**Motivation:** Architectural consistency — YAML-based repos are outliers among DB-backed repos.

## Scope

Migrate `TaggingRepository` (categories + tags + icons) and `CredentialsRepository` (provider accounts) from file-based YAML storage to SQLite via SQLAlchemy. Passwords remain in OS Keyring.

## DB Schema

### Categories Table

```sql
categories
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  name          TEXT NOT NULL UNIQUE
  tags          JSON NOT NULL DEFAULT '[]'    -- ["Groceries", "Restaurants"]
  icon          TEXT                           -- emoji, nullable
  created_at    TIMESTAMP
  updated_at    TIMESTAMP
```

Merges categories, tags, and icons into a single table. Tags stored as a JSON list of strings per category.

### Credentials Table

```sql
credentials
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  service       TEXT NOT NULL                  -- 'banks', 'credit_cards', 'insurances'
  provider      TEXT NOT NULL                  -- 'hapoalim', 'isracard'
  account_name  TEXT NOT NULL                  -- 'Main Account'
  fields        JSON NOT NULL DEFAULT '{}'     -- non-sensitive login fields
  created_at    TIMESTAMP
  updated_at    TIMESTAMP
  UNIQUE(service, provider, account_name)
```

Passwords and `otpLongTermToken` stay in OS Keyring. Key format standardized to `service:provider:account_name:field`.

## SQLAlchemy Models

```python
# backend/models/category.py
class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tags = Column(JSON, nullable=False, default=list)
    icon = Column(String, nullable=True)

# backend/models/credential.py
class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    service      = Column(String, nullable=False)
    provider     = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    fields       = Column(JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint("service", "provider", "account_name"),)
```

## Repository Changes

### TaggingRepository

Drops static methods. Standard DB repo with `db: Session`.

| Method | Behavior |
|--------|----------|
| `get_categories() -> dict[str, list[str]]` | Query all rows, return `{name: tags}` |
| `add_category(name, tags, icon=None)` | Insert row |
| `delete_category(name)` | Delete row |
| `add_tag(category, tag)` | Append to row's tags JSON list |
| `delete_tag(category, tag)` | Remove from row's tags JSON list |
| `relocate_tag(tag, old_category, new_category)` | Move between two rows' lists |
| `get_categories_icons() -> dict[str, str]` | Return `{name: icon}` for non-null icons |
| `update_category_icon(category, icon)` | Update icon column |
| `seed_from_yaml(categories_path, icons_path)` | One-time: load YAML, insert rows if table empty |

### CredentialsRepository

Drops singleton pattern. Standard DB repo with `db: Session` + Keyring.

| Method | Behavior |
|--------|----------|
| `get_credentials(service, provider, account_name) -> dict` | Query row + merge Keyring password |
| `save_credentials(service, provider, account_name, credentials)` | Pop secrets to Keyring, upsert row |
| `delete_credentials(service, provider, account_name)` | Delete row + Keyring keys |
| `list_accounts() -> list[dict]` | All rows as `[{service, provider, account_name}]` |
| `get_all_credentials() -> dict` | Nested dict with Keyring passwords filled in |
| `migrate_from_yaml(credentials_path)` | One-time: import existing YAML + Keyring refs |

Keyring key format standardized: `service:provider:account_name:field`.

## Service Layer Changes

### CategoriesTagsService
- Constructor requires `db: Session` always (no longer optional)
- Module-level cache retained
- `save_categories_and_tags()` removed — mutations commit individually
- Seeding triggered from app startup

### CredentialsService
- Constructor takes `db: Session`
- Module-level cache retained
- `generate_keyring_key()` removed — repo owns key format

### Routes
No changes. Already pass `db: Session` to services.

## Migration Strategy

No Alembic. Tables auto-create via `Base.metadata.create_all(engine)`.

**Startup hooks in `backend/main.py`:**
1. Categories table empty → seed from `default_categories.yaml` + `categories_icons.yaml` (or user's `~/.finance-analysis/categories.yaml` if it exists)
2. Credentials table empty + YAML exists → `migrate_from_yaml()`

YAML files remain on disk as rollback safety. No files auto-deleted.

## Testing

- TaggingRepository tests: `db_session` fixture replaces `tmp_path`
- CredentialsRepository tests: `db_session` fixture replaces singleton reset, mock Keyring
- New `seed_categories` fixture in `tests/backend/conftest.py`
- Existing service tests: minor fixture changes

## Deleted After Migration

- `backend/resources/default_credentials.yaml`
- `categories_path` / `credentials_path` from `AppConfig` (keep default paths for seeding)
- Singleton machinery from `CredentialsRepository`
- `CredentialsService.generate_keyring_key()`
- `CategoriesTagsService.save_categories_and_tags()`

## Implementation Order

1. Models + table constants
2. TaggingRepository (DB) + tests
3. CredentialsRepository (DB) + tests
4. CategoriesTagsService updates + tests
5. CredentialsService updates + tests
6. Startup migration hooks
7. Cleanup: dead code, old tests
