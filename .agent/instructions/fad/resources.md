# Resources Directory - Configuration & Static Data

## Purpose
Contains YAML configuration files for default settings, user credentials, and UI customization. These files provide templates and static data used throughout the application.

## Files Overview

### 1. `default_credentials.yaml`
**Purpose:** Empty template structure for credential configuration.

**Structure:**
```yaml
banks: {}
credit_cards: {}
insurances: {}
```

**Usage:**
- Read by `CredentialsRepository.read_default_credentials()`
- Provides empty template for first-time setup
- User's actual credentials stored in `~/.finance-analysis/credentials.yaml` (NOT in git)
- Only stores non-sensitive fields (usernames, account numbers, provider names)
- **Passwords stored in Windows Keyring for security**

**Adding New Provider Type:**
1. Add new top-level key (e.g., `brokerages: {}`)
2. Update `CredentialsRepository` to handle new service type
3. Update `naming_conventions.py` Services enum

### 2. `default_categories.yaml`
**Purpose:** Default category and tag hierarchy for expense classification.

**Structure:**
```yaml
CategoryName:
  - Tag1
  - Tag2
  - Tag3
```

**Usage:**
- Loaded once during first-time initialization
- Copied to user's `~/.finance-analysis/categories.yaml`
- Used by `TaggingService.load_default_categories()`
- Users can modify their copy without affecting defaults

**Category Types:**
- **Regular Expense Categories:** Food, Transportation, Health, Household, etc.
- **Income Categories:** Salary, Other Income
- **Non-Expense Categories:** Ignore, Savings, Investments, Liabilities
- **Project Categories:** User-defined (e.g., "Wedding", "New Apartment")

**Guidelines:**
- Keep tags descriptive and unambiguous
- Use title case for readability
- Organize by logical grouping
- Include "Ignore" category for internal transfers and credit card bills

### 3. `categories_icons.yaml`
**Purpose:** Unicode emoji icons mapped to category names for UI display.

**Structure:**
```yaml
CategoryName: "🔰"
AnotherCategory: "📊"
```

**Usage:**
- Loaded by `TaggingRepository.get_categories_icons()`
- Used in `TaggingComponents` to render category names with icons
- Updated via UI when users add/modify categories

**Guidelines:**
- Use single Unicode emoji (avoid multi-character sequences if possible)
- Choose intuitive, recognizable icons
- Maintain consistency (e.g., all finance-related categories use money-related icons)
- Automatically updated when users create new categories via UI

### 4. `test_credentials.yaml`
**Purpose:** Credentials for test accounts used in integration tests.

**Structure:** Same as `credentials.yaml`

**Usage:**
- Used only in tests marked with `@pytest.mark.sensitive`
- NOT committed to git (in `.gitignore`)
- Allows testing scraper functionality without using real user accounts

---

## File Location & Access

**Base Path:** `fad/resources/`

**Accessing in Code:**
```python
import os
from fad import SRC_PATH

# Default credentials template
default_creds_path = os.path.join(SRC_PATH, 'resources', 'default_credentials.yaml')

# Default categories
default_cats_path = os.path.join(SRC_PATH, 'resources', 'default_categories.yaml')

# Category icons
icons_path = os.path.join(SRC_PATH, 'resources', 'categories_icons.yaml')
```

---

## Security Considerations

### What IS stored in YAML:
- ✅ Provider names (e.g., "hapoalim", "max")
- ✅ Usernames
- ✅ Account numbers
- ✅ User codes
- ✅ Email addresses
- ✅ Phone numbers

### What is NOT stored in YAML:
- ❌ **Passwords** - stored in Windows Keyring
- ❌ **2FA codes** - generated/intercepted at runtime
- ❌ **Session tokens** - ephemeral, not persisted

---

## User Data vs. Default Data

| File | Location | Purpose | Modifiable |
|------|----------|---------|-----------|
| `default_credentials.yaml` | `fad/resources/` | Empty template | ❌ No (in git) |
| `credentials.yaml` | `~/.finance-analysis/` | User's actual config | ✅ Yes (via UI) |
| `default_categories.yaml` | `fad/resources/` | Default categories | ❌ No (in git) |
| `categories.yaml` | `~/.finance-analysis/` | User's categories | ✅ Yes (via UI) |
| `categories_icons.yaml` | `fad/resources/` | Icon mappings | ✅ Yes (via UI) |
| `test_credentials.yaml` | `fad/resources/` | Test account creds | ❌ No (gitignored) |

**Note:** `~/.finance-analysis/` refers to the `.finance-analysis` directory in the user's home directory.

---

## Common Tasks

### Adding a New Default Category
1. Edit `fad/resources/default_categories.yaml`
2. Add category and its tags in YAML format
3. Add icon mapping to `categories_icons.yaml`
4. Users will see new category on next fresh install

### Adding Support for New Provider
1. Add provider to `naming_conventions.py` enums (CreditCards/Banks/Insurances)
2. Add login fields to `LoginFields.providers_fields` dict
3. User adds credentials via "My Accounts" UI page
4. Credentials saved to `~/.finance-analysis/credentials.yaml` + Windows Keyring

### Adding/Changing Category Icons
- Done automatically via UI when users create/edit categories
- Updates `fad/resources/categories_icons.yaml`
- Icons are loaded dynamically

---

## Data Flow

### First-Time Setup:
1. User launches app
2. App checks for `~/.finance-analysis/credentials.yaml`
3. If not found, copies `default_credentials.yaml` structure
4. App checks for `~/.finance-analysis/categories.yaml`
5. If not found, copies `default_categories.yaml`
6. User fills in credentials via UI → saved to `credentials.yaml` + Windows Keyring

### Regular Usage:
1. App loads `~/.finance-analysis/credentials.yaml` + retrieves passwords from Windows Keyring
2. App loads `~/.finance-analysis/categories.yaml` (or defaults if not modified)
3. App loads `categories_icons.yaml` for UI rendering
4. User interactions update YAML files as needed

---

## Notes
- All resource files use YAML format (human-readable, easy to edit)
- Always validate YAML structure after manual edits
- Icons are optional - categories work without them
- Test credentials structure must mirror production credentials structure
- User data directory (`~/.finance-analysis/`) is created automatically on first run

